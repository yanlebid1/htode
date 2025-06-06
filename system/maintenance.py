# system/maintenance.py

import time
import os
from datetime import datetime, timedelta
from typing import Dict, Any

from sqlalchemy import or_, func

from common.celery_app import celery_app
from common.db.operations import batch_get_full_ad_data, batch_get_user_filters
from common.db.session import db_session
from common.db.models.favorite import FavoriteAd
from common.db.models.verification import VerificationCode
from common.db.models.user import User
from common.db.models.subscription import UserFilter
from common.db.repositories.ad_repository import AdRepository
from common.utils.s3_utils import delete_s3_image
from common.utils.cache import redis_client, CacheTTL
from common.config import GEO_ID_MAPPING
from common.utils.cache_managers import BaseCacheManager, AdCacheManager, UserCacheManager
from common.utils.logging_config import setup_logging, log_operation, log_context, LogAggregator
from common.utils.log_management import setup_file_logging

# Initialize system logger
logger = setup_logging('system_maintenance', log_level='INFO', log_format='text')

# Add file logging if we're in production
if os.getenv('ENVIRONMENT', 'development') == 'production':
    setup_file_logging(
        logger,
        log_dir="/app/logs/system",
        max_bytes=10 * 1024 * 1024,  # 10MB
        backup_count=5,
        when='d',
        interval=1
    )


@celery_app.task(name='system.maintenance.check_expiring_subscriptions')
@log_operation("check_expiring_subscriptions")
def check_expiring_subscriptions() -> Dict[str, Any]:
    """
    Check for expiring subscriptions and send reminders.
    """
    start_time = time.time()
    aggregator = LogAggregator(logger, "check_expiring_subscriptions")

    with log_context(logger, task="check_expiring_subscriptions"):
        try:
            with db_session() as db:
                # Get users with subscriptions expiring in the next few days
                reminders_sent = 0

                # Check for subscriptions expiring in 3, 2, and 1 days
                for days in [3, 2, 1]:
                    with log_context(logger, days_until_expiry=days):
                        future_date = datetime.now() + timedelta(days=days, hours=1)
                        past_date = datetime.now() + timedelta(days=days - 1)

                        # Get users whose subscription expires in the specified time window
                        users = db.query(User).filter(
                            User.subscription_until.isnot(None),
                            User.subscription_until > datetime.now(),
                            User.subscription_until < future_date,
                            User.subscription_until > past_date
                        ).all()

                        logger.info(f"Found users with expiring subscriptions", extra={
                            'days_until_expiry': days,
                            'user_count': len(users)
                        })

                        for user in users:
                            # Determine template based on days remaining
                            days_word = "день" if days == 1 else "дні" if days < 5 else "днів"
                            end_date = user.subscription_until.strftime("%d.%m.%Y")

                            # Build the appropriate template
                            if days == 1:
                                template = (
                                    "⚠️ Ваша підписка закінчується завтра!\n\n"
                                    "Дата закінчення: {end_date}\n\n"
                                    "Щоб не втратити доступ до сервісу, оновіть підписку зараз."
                                )
                            else:
                                template = (
                                    "⚠️ Нагадування про підписку\n\n"
                                    "Ваша підписка закінчується через {days} "
                                    "{days_word}.\n"
                                    "Дата закінчення: {end_date}\n\n"
                                    "Щоб продовжити користуватися сервісом, оновіть підписку."
                                )

                            # Send notification
                            from common.messaging.tasks import send_notification
                            send_notification.delay(
                                user_id=user.id,
                                template=template,
                                data={
                                    "days": days,
                                    "days_word": days_word,
                                    "end_date": end_date
                                }
                            )
                            reminders_sent += 1
                            aggregator.add_item({'user_id': user.id, 'days': days}, success=True)

                # Also notify on the day of expiration
                today = datetime.now().date()
                users_today = db.query(User).filter(
                    User.subscription_until.isnot(None),
                    func.date(User.subscription_until) == today
                ).all()

                logger.info(f"Found users with subscriptions expiring today", extra={
                    'user_count': len(users_today)
                })

                for user in users_today:
                    end_date = user.subscription_until.strftime("%d.%m.%Y %H:%M")

                    # Send notification
                    from common.messaging.tasks import send_notification
                    send_notification.delay(
                        user_id=user.id,
                        template=(
                            "⚠️ Ваша підписка закінчується сьогодні!\n\n"
                            "Час закінчення: {end_date}\n\n"
                            "Щоб не втратити доступ до сервісу, оновіть підписку зараз."
                        ),
                        data={"end_date": end_date}
                    )
                    reminders_sent += 1
                    aggregator.add_item({'user_id': user.id, 'days': 0}, success=True)

            execution_time = time.time() - start_time
            aggregator.log_summary()

            logger.info(f"Checked expiring subscriptions", extra={
                'reminders_sent': reminders_sent,
                'execution_time': execution_time
            })

            return {
                "status": "success",
                "reminders_sent": reminders_sent,
                "execution_time_seconds": execution_time
            }
        except Exception as e:
            logger.error("Error checking expiring subscriptions", exc_info=True, extra={
                'error_type': type(e).__name__
            })
            aggregator.add_error(str(e), {})
            aggregator.log_summary()
            return {
                "status": "error",
                "error": str(e),
                "execution_time_seconds": time.time() - start_time
            }


@celery_app.task(name='system.maintenance.cleanup_old_ads')
@log_operation("cleanup_old_ads")
def cleanup_old_ads(days_old: int = 30, check_activity: bool = True) -> Dict[str, Any]:
    """
    Cleans up ads that are older than the specified number of days,
    and optionally checks if they are still active (not 404).

    Args:
        days_old: Number of days after which ads are considered old
        check_activity: Whether to check if the ad is still active (not 404)

    Returns:
        Summary of cleanup operations with counts of deleted ads and images
    """
    start_time = time.time()
    deleted_count = 0
    images_deleted_count = 0
    aggregator = LogAggregator(logger, f"cleanup_old_ads_{days_old}days")

    with log_context(logger, days_old=days_old, check_activity=check_activity):
        logger.info(f"Starting cleanup of ads older than {days_old} days", extra={
            'check_activity': check_activity
        })

        try:
            with db_session() as db:
                # Calculate cutoff date
                cutoff_date = datetime.now() - timedelta(days=days_old)

                # Get old ads
                old_ads = AdRepository.get_older_than(db, cutoff_date)
                logger.info(f"Found old ads for cleanup", extra={
                    'ad_count': len(old_ads),
                    'cutoff_date': cutoff_date.isoformat()
                })

                for ad in old_ads:
                    should_delete = True

                    # Check if ad is still active if requested
                    if check_activity:
                        from common.services.ad_service import AdService
                        if not AdService.is_ad_inactive(ad.resource_url):
                            should_delete = False
                            logger.debug(f"Ad is still active, skipping", extra={
                                'ad_id': ad.id,
                                'resource_url': ad.resource_url
                            })

                    if should_delete:
                        # Get ad images before deleting
                        images = AdRepository.get_ad_images(db, ad.id)

                        # Delete the ad and related data
                        if AdRepository.delete_with_related(db, ad.id):
                            deleted_count += 1
                            aggregator.add_item({'ad_id': ad.id}, success=True)

                            # Delete images from S3
                            for image_url in images:
                                if delete_s3_image(image_url):
                                    images_deleted_count += 1

                            # Clear cache
                            clear_ad_cache(ad.id, ad.resource_url)
                        else:
                            aggregator.add_error("Failed to delete ad", {'ad_id': ad.id})

            execution_time = time.time() - start_time
            aggregator.log_summary()

            logger.info(f"Cleanup completed", extra={
                'execution_time': execution_time,
                'ads_deleted': deleted_count,
                'images_deleted': images_deleted_count
            })

            return {
                "status": "completed",
                "ads_deleted": deleted_count,
                "images_deleted": images_deleted_count,
                "execution_time_seconds": execution_time
            }
        except Exception as e:
            logger.error("Error in cleanup_old_ads", exc_info=True, extra={
                'error_type': type(e).__name__
            })
            aggregator.add_error(str(e), {})
            aggregator.log_summary()
            return {
                "status": "error",
                "error": str(e),
                "execution_time_seconds": time.time() - start_time
            }


@log_operation("clear_ad_cache")
def clear_ad_cache(ad_id: int, resource_url: str = None):
    """
    Clear all cache entries related to a specific ad

    Args:
        ad_id: ID of the ad
        resource_url: Optional resource URL for additional cache keys
    """
    from common.utils.cache_managers import AdCacheManager

    with log_context(logger, ad_id=ad_id, resource_url=resource_url):
        # Use the cache manager to handle invalidation
        deleted_count = AdCacheManager.invalidate_all(ad_id, resource_url)
        logger.debug(f"Cleared cache for ad", extra={
            'ad_id': ad_id,
            'deleted_count': deleted_count
        })


@celery_app.task(name='system.maintenance.cleanup_expired_verification_codes')
@log_operation("cleanup_expired_verification_codes")
def cleanup_expired_verification_codes() -> Dict[str, int]:
    """
    Clean up expired verification codes and tokens.

    Returns:
        Dictionary with counts of deleted items
    """
    with log_context(logger, task="cleanup_expired_verification_codes"):
        try:
            with db_session() as db:
                # Cleanup verification codes
                verification_codes_deleted = db.query(VerificationCode).filter(
                    VerificationCode.expires_at < datetime.now()
                ).delete()

                # Cleanup email verification tokens
                # Using raw SQL because the EmailVerificationToken model appears to be missing
                from sqlalchemy import text
                result = db.execute(
                    text("DELETE FROM email_verification_tokens WHERE expires_at < CURRENT_TIMESTAMP")
                )
                email_tokens_deleted = result.rowcount

                db.commit()

                logger.info(f"Cleaned up verification codes and tokens", extra={
                    'verification_codes_deleted': verification_codes_deleted,
                    'email_tokens_deleted': email_tokens_deleted
                })

                return {
                    "verification_codes_deleted": verification_codes_deleted,
                    "email_tokens_deleted": email_tokens_deleted
                }
        except Exception as e:
            logger.error("Error cleaning up expired verification codes", exc_info=True, extra={
                'error_type': type(e).__name__
            })
            return {
                "verification_codes_deleted": 0,
                "email_tokens_deleted": 0,
                "error": str(e)
            }


@celery_app.task(name='system.maintenance.cleanup_redis_cache')
@log_operation("cleanup_redis_cache")
def cleanup_redis_cache(pattern: str = None, older_than_days: int = None) -> Dict[str, int]:
    """
    Clean up Redis cache entries matching a pattern and/or older than specified days

    Args:
        pattern: Optional Redis key pattern to match (e.g., "user_filters:*")
        older_than_days: Optional age threshold in days

    Returns:
        Dictionary with count of deleted cache entries
    """
    start_time = time.time()
    aggregator = LogAggregator(logger, "cleanup_redis_cache")

    with log_context(logger, pattern=pattern, older_than_days=older_than_days):
        if not pattern:
            # Use a generic pattern to match all cache keys
            pattern = "*"

        deleted_count = 0

        if older_than_days is not None:
            # Only delete keys older than the specified threshold
            # Using a custom ttl-based approach since Redis doesn't track key age directly
            max_ttl = CacheTTL.EXTENDED  # 7 days

            # Get all keys matching the pattern
            matching_keys = redis_client.keys(pattern)
            logger.info(f"Found keys matching pattern", extra={
                'pattern': pattern,
                'key_count': len(matching_keys)
            })

            if matching_keys:
                # Check TTL for each key
                keys_to_delete = []

                for key in matching_keys:
                    ttl = redis_client.ttl(key)

                    # If TTL is -1 (no expiration) or -2 (key doesn't exist), skip
                    if ttl < 0:
                        continue

                    # Calculate age in the past days
                    age_seconds = max_ttl - ttl
                    age_days = age_seconds / 86400  # Convert to days

                    if age_days > older_than_days:
                        keys_to_delete.append(key)
                        aggregator.add_item({'key': str(key), 'age_days': age_days}, success=True)

                # Delete the filtered keys
                if keys_to_delete:
                    deleted_count = BaseCacheManager.delete_keys(keys_to_delete)
        else:
            # Delete all matching keys
            deleted_count = BaseCacheManager.delete_pattern(pattern)
            aggregator.add_item({'pattern': pattern, 'deleted': deleted_count}, success=True)

        execution_time = time.time() - start_time
        aggregator.log_summary()

        logger.info(f"Cache cleanup completed", extra={
            'deleted_count': deleted_count,
            'execution_time': execution_time
        })

        return {
            "deleted_count": deleted_count,
            "execution_time_seconds": execution_time
        }


@celery_app.task(name='system.maintenance.optimize_database')
@log_operation("optimize_database")
def optimize_database() -> Dict[str, Any]:
    """
    Perform database maintenance tasks like VACUUM and ANALYZE to optimize performance

    Returns:
        Dictionary with operation status
    """
    start_time = time.time()
    operations = []
    aggregator = LogAggregator(logger, "optimize_database")

    with log_context(logger, task="optimize_database"):
        try:
            # List of tables to optimize
            tables = [
                "ads", "ad_images", "ad_phones", "users",
                "user_filters", "favorite_ads", "verification_codes",
                "email_verification_tokens", "payment_orders", "payment_history"
            ]

            with db_session() as db:
                # For database operations like VACUUM, we need to use raw SQL
                # and manage the connection manually since these operations
                # can't run inside a transaction

                # Get the raw connection from the SQLAlchemy session
                connection = db.connection()

                # These operations need to run outside a transaction
                old_isolation_level = connection.connection.isolation_level
                connection.connection.set_isolation_level(0)  # AUTOCOMMIT mode

                try:
                    # VACUUM ANALYZE on each table
                    for table in tables:
                        logger.info(f"Running VACUUM ANALYZE", extra={'table': table})
                        db.execute(f"VACUUM ANALYZE {table}")
                        operations.append(f"VACUUM ANALYZE {table}")
                        aggregator.add_item({'operation': f"VACUUM ANALYZE {table}"}, success=True)

                    # Update table statistics
                    for table in tables:
                        logger.info(f"Running ANALYZE", extra={'table': table})
                        db.execute(f"ANALYZE {table}")
                        operations.append(f"ANALYZE {table}")
                        aggregator.add_item({'operation': f"ANALYZE {table}"}, success=True)

                    # Optimize indexes
                    logger.info("Reindexing database")
                    db.execute("REINDEX DATABASE current_database()")
                    operations.append("REINDEX DATABASE")
                    aggregator.add_item({'operation': "REINDEX DATABASE"}, success=True)
                finally:
                    # Restore previous isolation level
                    connection.connection.set_isolation_level(old_isolation_level)

        except Exception as e:
            logger.error("Error during database optimization", exc_info=True, extra={
                'error_type': type(e).__name__
            })
            aggregator.add_error(str(e), {})
            aggregator.log_summary()
            return {
                "status": "error",
                "error": str(e),
                "execution_time_seconds": time.time() - start_time
            }

        execution_time = time.time() - start_time
        aggregator.log_summary()

        logger.info(f"Database optimization completed", extra={
            'execution_time': execution_time,
            'operations_count': len(operations)
        })

        return {
            "status": "success",
            "operations": operations,
            "execution_time_seconds": execution_time
        }


@celery_app.task(name='system.maintenance.cache_warming')
@log_operation("cache_warming")
def cache_warming() -> Dict[str, int]:
    """
    Warm up cache for frequently accessed data
    """
    start_time = time.time()
    cached_items = 0
    aggregator = LogAggregator(logger, "cache_warming")

    with log_context(logger, task="cache_warming"):
        try:
            with db_session() as db:
                # 1. Warm up cache for active cities
                active_cities = db.query(UserFilter.city).join(
                    User, UserFilter.user_id == User.id
                ).filter(
                    UserFilter.city.isnot(None),
                    or_(User.subscription_until > datetime.now(), User.free_until > datetime.now())
                ).distinct().all()

                logger.info(f"Found active cities", extra={
                    'city_count': len(active_cities)
                })

                # Cache city data using BaseCacheManager
                for city_row in active_cities:
                    city_id = city_row[0]  # Extract the city ID from the row
                    city_key = f"city:{city_id}"
                    city_data = {
                        "id": city_id,
                        "name": GEO_ID_MAPPING.get(city_id, "Unknown")
                    }
                    BaseCacheManager.set(city_key, city_data, CacheTTL.LONG)
                    cached_items += 1
                    aggregator.add_item({'city_id': city_id}, success=True)

                # 2. Warm up cache for most viewed ads
                top_ads_subquery = db.query(
                    FavoriteAd.ad_id,
                    func.count(FavoriteAd.ad_id).label('view_count')
                ).group_by(
                    FavoriteAd.ad_id
                ).order_by(
                    func.count(FavoriteAd.ad_id).desc()
                ).limit(50).subquery()

                top_ads = db.query(top_ads_subquery.c.ad_id).all()

                logger.info(f"Found top viewed ads", extra={
                    'ad_count': len(top_ads)
                })

                if top_ads:
                    ad_ids = [row[0] for row in top_ads]

                    # Batch fetch ad data
                    ad_data_dict = batch_get_full_ad_data(ad_ids)

                    # Cache individually using AdCacheManager
                    for ad_id, ad_data in ad_data_dict.items():
                        if ad_data:
                            AdCacheManager.set_full_ad_data(ad_id, ad_data)
                            cached_items += 1
                            aggregator.add_item({'ad_id': ad_id}, success=True)

                # 3. Warm up cache for active users
                active_users = db.query(User.id).filter(
                    User.last_active > datetime.now() - timedelta(days=7)
                ).limit(100).all()

                logger.info(f"Found active users", extra={
                    'user_count': len(active_users)
                })

                if active_users:
                    user_ids = [row[0] for row in active_users]

                    # Batch fetch user filters
                    user_filters = batch_get_user_filters(user_ids)

                    # Cache individually using UserCacheManager
                    for user_id, filters in user_filters.items():
                        UserCacheManager.set_filters(user_id, filters)
                        cached_items += 1
                        aggregator.add_item({'user_id': user_id}, success=True)

        except Exception as e:
            logger.error("Error during cache warming", exc_info=True, extra={
                'error_type': type(e).__name__
            })
            aggregator.add_error(str(e), {})
            aggregator.log_summary()
            return {
                "status": "error",
                "error": str(e),
                "cached_items": cached_items,
                "execution_time_seconds": time.time() - start_time
            }

        execution_time = time.time() - start_time
        aggregator.log_summary()

        logger.info(f"Cache warming completed", extra={
            'cached_items': cached_items,
            'execution_time': execution_time
        })

        return {
            "status": "success",
            "cached_items": cached_items,
            "execution_time_seconds": execution_time
        }


@celery_app.task(name='system.maintenance.check_database_connections')
@log_operation("check_database_connections")
def check_database_connections() -> Dict[str, Any]:
    """
    Check database connection pool health and reset if necessary

    Returns:
        Dictionary with pool statistics
    """
    from common.db.database import pool, initialize_pool

    with log_context(logger, task="check_database_connections"):
        if not pool:
            logger.warning("Database connection pool not initialized, initializing now")
            initialize_pool()
            return {
                "status": "initialized",
                "min_connections": pool.minconn,
                "max_connections": pool.maxconn,
                "used_connections": 0
            }

        # Get pool statistics
        min_conn = pool.minconn
        max_conn = pool.maxconn
        used_conn = len(pool._used)

        logger.info(f"Database connection pool status", extra={
            'used_connections': used_conn,
            'max_connections': max_conn,
            'usage_percent': (used_conn / max_conn) * 100 if max_conn > 0 else 0
        })

        # Check if pool is near capacity and should be reset
        if used_conn > max_conn * 0.8:
            logger.warning(f"Database connection pool is at high capacity", extra={
                'usage_percent': (used_conn / max_conn) * 100
            })

        # Check for leaked connections (connections used for very long periods)
        if hasattr(pool, '_used') and pool._used:
            old_connections = []
            current_time = time.time()

            for conn_id, (conn, timestamp) in pool._used.items():
                # Check if connection has been held for more than 10 minutes
                if current_time - timestamp > 600:
                    old_connections.append((conn_id, current_time - timestamp))

            if old_connections:
                logger.warning(f"Found potentially leaked database connections", extra={
                    'leaked_count': len(old_connections)
                })
                for conn_id, age in old_connections:
                    logger.warning(f"Connection has been active for long time", extra={
                        'connection_id': conn_id,
                        'age_seconds': age
                    })

        return {
            "status": "checked",
            "min_connections": min_conn,
            "max_connections": max_conn,
            "used_connections": used_conn
        }


@celery_app.task(name='system.maintenance.check_subscription_statistics')
@log_operation("check_subscription_statistics")
def check_subscription_statistics() -> Dict[str, Any]:
    """
    Generate and save subscription statistics

    Returns:
        Dictionary with subscriber counts and statistics
    """
    start_time = time.time()
    aggregator = LogAggregator(logger, "check_subscription_statistics")

    with log_context(logger, task="check_subscription_statistics"):
        try:
            with db_session() as db:
                # Count active subscribers
                active_subscribers = db.query(func.count(User.id)).filter(
                    or_(
                        User.subscription_until > datetime.now(),
                        User.free_until > datetime.now()
                    )
                ).scalar()

                # Count paid subscribers
                paid_subscribers = db.query(func.count(User.id)).filter(
                    User.subscription_until > datetime.now()
                ).scalar()

                # Count free trial subscribers
                free_trial_subscribers = db.query(func.count(User.id)).filter(
                    User.free_until > datetime.now(),
                    or_(
                        User.subscription_until.is_(None),
                        User.subscription_until < datetime.now()
                    )
                ).scalar()

                # Count subscribers by platform
                telegram_subscribers = db.query(func.count(User.id)).filter(
                    User.telegram_id.isnot(None),
                    or_(
                        User.subscription_until > datetime.now(),
                        User.free_until > datetime.now()
                    )
                ).scalar()

                # Count by subscription filter
                subscription_counts = {}

                # Count by city
                city_counts = db.query(
                    UserFilter.city,
                    func.count(UserFilter.city).label('count')
                ).join(
                    User, UserFilter.user_id == User.id
                ).filter(
                    or_(
                        User.subscription_until > datetime.now(),
                        User.free_until > datetime.now()
                    ),
                    UserFilter.city.isnot(None)
                ).group_by(
                    UserFilter.city
                ).all()

                city_stats = {
                    GEO_ID_MAPPING.get(city_id, f"Unknown ({city_id})"): count
                    for city_id, count in city_counts
                }

                subscription_counts["by_city"] = city_stats

                # Count by property type
                property_type_counts = db.query(
                    UserFilter.property_type,
                    func.count(UserFilter.property_type).label('count')
                ).join(
                    User, UserFilter.user_id == User.id
                ).filter(
                    or_(
                        User.subscription_until > datetime.now(),
                        User.free_until > datetime.now()
                    ),
                    UserFilter.property_type.isnot(None)
                ).group_by(
                    UserFilter.property_type
                ).all()

                property_stats = {
                    property_type: count for property_type, count in property_type_counts
                }

                subscription_counts["by_property_type"] = property_stats

                # Store statistics in Redis for later access
                statistics = {
                    "timestamp": datetime.now().isoformat(),
                    "active_subscribers": active_subscribers,
                    "paid_subscribers": paid_subscribers,
                    "free_trial_subscribers": free_trial_subscribers,
                    "platform_breakdown": {
                        "telegram": telegram_subscribers,
                    },
                    "subscription_counts": subscription_counts
                }

                BaseCacheManager.set("subscription_statistics", statistics, CacheTTL.LONG)

                execution_time = time.time() - start_time

                logger.info("Generated subscription statistics", extra={
                    'active_subscribers': active_subscribers,
                    'paid_subscribers': paid_subscribers,
                    'free_trial_subscribers': free_trial_subscribers,
                    'execution_time': execution_time
                })

                aggregator.add_item({'statistics': "generated"}, success=True)
                aggregator.log_summary()

                return {
                    "status": "success",
                    "statistics": statistics,
                    "execution_time_seconds": execution_time
                }
        except Exception as e:
            logger.error("Error generating subscription statistics", exc_info=True, extra={
                'error_type': type(e).__name__
            })
            aggregator.add_error(str(e), {})
            aggregator.log_summary()
            return {
                "status": "error",
                "error": str(e),
                "execution_time_seconds": time.time() - start_time
            }