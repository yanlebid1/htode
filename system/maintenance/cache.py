# system/maintenance/cache.py

from ._common import (
    celery_app,
    db_session,
    or_,
    func,
    time,
    datetime,
    timedelta,
    timezone,
    logger,
    log_operation,
    log_context,
    LogAggregator,
    User,
    UserFilter,
    redis_client,
    CacheTTL,
    GEO_ID_MAPPING,
    BaseCacheManager,
    AdCacheManager,
    UserCacheManager,
    ACTIVE_USER_LOOKBACK_DAYS,
    Dict,
    Any,
)
from common.db.operations import batch_get_full_ad_data, batch_get_user_filters
from common.db.models.favorite import FavoriteAd


@celery_app.task(name="system.maintenance.cleanup_redis_cache")
@log_operation("cleanup_redis_cache")
def cleanup_redis_cache(
    pattern: str = None, older_than_days: int = None
) -> Dict[str, int]:
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

            # Get all keys matching the pattern using SCAN (non-blocking)
            from common.utils.cache import _scan_keys
            matching_keys = _scan_keys(pattern)
            logger.info(
                "Found keys matching pattern",
                extra={"pattern": pattern, "key_count": len(matching_keys)},
            )

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
                        aggregator.add_item(
                            {"key": str(key), "age_days": age_days}, success=True
                        )

                # Delete the filtered keys
                if keys_to_delete:
                    deleted_count = BaseCacheManager.delete_keys(keys_to_delete)
        else:
            # Delete all matching keys
            deleted_count = BaseCacheManager.delete_pattern(pattern)
            aggregator.add_item(
                {"pattern": pattern, "deleted": deleted_count}, success=True
            )

        execution_time = time.time() - start_time
        aggregator.log_summary()

        logger.info(
            "Cache cleanup completed",
            extra={"deleted_count": deleted_count, "execution_time": execution_time},
        )

        return {
            "deleted_count": deleted_count,
            "execution_time_seconds": execution_time,
        }


@celery_app.task(name="system.maintenance.cache_warming")
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
                active_cities = (
                    db.query(UserFilter.city)
                    .join(User, UserFilter.user_id == User.id)
                    .filter(
                        UserFilter.city.isnot(None),
                        or_(
                            User.subscription_until > datetime.now(timezone.utc),
                            User.free_until > datetime.now(timezone.utc),
                        ),
                    )
                    .distinct()
                    .all()
                )

                logger.info(
                    "Found active cities", extra={"city_count": len(active_cities)}
                )

                # Cache city data using BaseCacheManager
                for city_row in active_cities:
                    city_id = city_row[0]  # Extract the city ID from the row
                    city_key = f"city:{city_id}"
                    city_data = {
                        "id": city_id,
                        "name": GEO_ID_MAPPING.get(city_id, "Unknown"),
                    }
                    BaseCacheManager.set(city_key, city_data, CacheTTL.LONG)
                    cached_items += 1
                    aggregator.add_item({"city_id": city_id}, success=True)

                # 2. Warm up cache for most viewed ads
                top_ads_subquery = (
                    db.query(
                        FavoriteAd.ad_id,
                        func.count(FavoriteAd.ad_id).label("view_count"),
                    )
                    .group_by(FavoriteAd.ad_id)
                    .order_by(func.count(FavoriteAd.ad_id).desc())
                    .limit(50)
                    .subquery()
                )

                top_ads = db.query(top_ads_subquery.c.ad_id).all()

                logger.info("Found top viewed ads", extra={"ad_count": len(top_ads)})

                if top_ads:
                    ad_ids = [row[0] for row in top_ads]

                    # Batch fetch ad data
                    ad_data_dict = batch_get_full_ad_data(ad_ids)

                    # Cache individually using AdCacheManager
                    for ad_id, ad_data in ad_data_dict.items():
                        if ad_data:
                            AdCacheManager.set_full_ad_data(ad_id, ad_data)
                            cached_items += 1
                            aggregator.add_item({"ad_id": ad_id}, success=True)

                # 3. Warm up cache for active users
                active_users = (
                    db.query(User.id)
                    .filter(User.last_active > datetime.now(timezone.utc) - timedelta(days=ACTIVE_USER_LOOKBACK_DAYS))
                    .limit(100)
                    .all()
                )

                logger.info(
                    "Found active users", extra={"user_count": len(active_users)}
                )

                if active_users:
                    user_ids = [row[0] for row in active_users]

                    # Batch fetch user filters
                    user_filters = batch_get_user_filters(user_ids)

                    # Cache individually using UserCacheManager
                    for user_id, filters in user_filters.items():
                        UserCacheManager.set_filters(user_id, filters)
                        cached_items += 1
                        aggregator.add_item({"user_id": user_id}, success=True)

        except Exception as e:
            logger.error(
                "Error during cache warming",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            aggregator.add_error(str(e), {})
            aggregator.log_summary()
            return {
                "status": "error",
                "error": str(e),
                "cached_items": cached_items,
                "execution_time_seconds": time.time() - start_time,
            }

        execution_time = time.time() - start_time
        aggregator.log_summary()

        logger.info(
            "Cache warming completed",
            extra={"cached_items": cached_items, "execution_time": execution_time},
        )

        return {
            "status": "success",
            "cached_items": cached_items,
            "execution_time_seconds": execution_time,
        }
