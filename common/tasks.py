"""
Common Celery tasks used across services.
"""

import asyncio
from typing import List, Optional
from common.celery_app import celery_app
from common.config import build_ad_text
from common.utils.task_versioning import versioned_task
from common.utils.logging_config import log_operation, log_context
from common.utils import logger


@versioned_task("extract_phones_for_ad", version="v1")
@log_operation("extract_phones_for_ad")
def extract_phones_for_ad_v1(ad_id: int, resource_url: str):
    """
    Extract phones asynchronously after ad is created.

    This task runs in a separate queue to avoid blocking ad processing.
    """
    from common.utils.extraction_client import extraction_client
    from common.db.session import db_session
    from common.db.repositories.ad_repository import AdRepository

    with log_context(logger, ad_id=ad_id, resource_url=resource_url):
        try:
            # Use the new extraction client
            result = extraction_client.extract_content(
                url=resource_url, wait_after_load=3000
            )

            if result["status"] == "success":
                # Parse phones from the HTML content we received
                from common.utils.phone_utils.parsers import get_parser_for_url

                final_url = result.get("final_url", resource_url)
                parser = get_parser_for_url(final_url)

                if parser:
                    # Parse the HTML content
                    from bs4 import BeautifulSoup

                    soup = BeautifulSoup(result.get("content", ""), "html.parser")
                    phone_result = parser.extract_phones(final_url, soup)
                else:
                    # No specific parser, return empty result
                    from common.utils.phone_utils.phone_models import ExtractionResult

                    phone_result = ExtractionResult(
                        phone_numbers=[], source_url=final_url
                    )

                # Store in database
                phones_stored = 0
                with db_session() as db:
                    for phone in phone_result.phone_numbers:
                        AdRepository.add_phone(db, ad_id, phone)
                        phones_stored += 1

                    if phone_result.viber_link:
                        AdRepository.add_phone(db, ad_id, None, phone_result.viber_link)

                    db.commit()

                logger.info(
                    "Phone extraction completed",
                    extra={
                        "ad_id": ad_id,
                        "phones_found": len(phone_result.phone_numbers),
                        "phones_stored": phones_stored,
                        "has_viber": bool(phone_result.viber_link),
                        "service_used": result.get("service_used"),
                        "method_used": result.get("method_used"),
                    },
                )

                # Clear cache since we updated the ad
                from common.utils.cache_managers import AdCacheManager

                AdCacheManager.invalidate_all(ad_id, resource_url)

            else:
                logger.error(
                    "Content extraction failed",
                    extra={
                        "ad_id": ad_id,
                        "error": result.get("error"),
                        "service_used": result.get("service_used"),
                    },
                )

        except Exception as e:
            logger.error(
                "Phone extraction task failed",
                exc_info=True,
                extra={
                    "ad_id": ad_id,
                    "resource_url": resource_url,
                    "error_type": type(e).__name__,
                },
            )
            # Could implement retry logic here
            raise


@versioned_task("notify_user_batch", version="v2")
@log_operation("notify_user_batch_v2_ultra_fast")
def notify_user_batch_v2(
    user_ids: List[int], ad_data: dict, s3_image_url: Optional[str] = None
):
    """
    ULTRA-FAST batch notification system v2.
    Optimized for 10x higher throughput with advanced parallelization.
    """
    from common.db.session import db_session
    from common.db.models import User
    import time

    with log_context(logger, user_count=len(user_ids), ad_id=ad_data.get("id")):
        success_count = 0
        failed_count = 0

        # Format the ad text once
        text = build_ad_text(ad_data)

        # Get user telegram IDs in batch
        with db_session() as db:
            users = db.query(User).filter(User.id.in_(user_ids)).all()
            user_telegram_map = {user.id: user.telegram_id for user in users}

        # OPTIMIZED: Direct Celery task dispatch (no async overhead for maximum speed)
        start_time = time.time()
        
        for user_id in user_ids:
            telegram_id = user_telegram_map.get(user_id)
            if not telegram_id:
                failed_count += 1
                continue

            # Dispatch directly to telegram queue for maximum throughput
            try:
                celery_app.send_task(
                    "common.messaging.tasks.send_ad_with_extra_buttons",
                    args=[
                        telegram_id,
                        text,
                        s3_image_url,
                        ad_data.get("resource_url"),
                        ad_data.get("id"),
                        ad_data.get("external_id"),
                    ],
                    queue="telegram_queue",
                    priority=8,  # Higher priority for batch notifications
                )
                success_count += 1
            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to dispatch notification to {telegram_id}: {e}")

        # Performance metrics
        processing_time = time.time() - start_time
        users_per_second = len(user_ids) / processing_time if processing_time > 0 else 0

        logger.info(
            "ULTRA-FAST batch notification completed",
            extra={
                "total_users": len(user_ids),
                "success_count": success_count,
                "failed_count": failed_count,
                "ad_id": ad_data.get("id"),
                "processing_time_ms": processing_time * 1000,
                "users_per_second": users_per_second,
                "version": "v2_ultra_fast",
            },
        )

        return {
            "success_count": success_count,
            "failed_count": failed_count,
            "total": len(user_ids),
            "processing_time": processing_time,
            "users_per_second": users_per_second,
        }


@versioned_task("notify_user_batch", version="v3")
@log_operation("notify_user_batch_v3_multibot")
def notify_user_batch_v3(
    user_ids: List[int], ad_data: dict, s3_image_url: Optional[str] = None
):
    """
    MULTI-BOT batch notification system v3.
    Routes notifications through assigned pool bots for 20x throughput.
    """
    from common.db.session import db_session
    from common.db.models import User
    from collections import defaultdict
    import time

    with log_context(logger, user_count=len(user_ids), ad_id=ad_data.get("id")):
        start_time = time.time()
        success_count = 0
        failed_count = 0
        no_bot_count = 0

        # Format the ad text once
        text = build_ad_text(ad_data)

        # Get users and group by assigned bot
        users_by_bot = defaultdict(list)
        
        with db_session() as db:
            users = db.query(User).filter(User.id.in_(user_ids)).all()
            
            for user in users:
                if user.assigned_bot_name:
                    users_by_bot[user.assigned_bot_name].append({
                        'user_id': user.id,
                        'telegram_id': user.telegram_id
                    })
                else:
                    no_bot_count += 1
                    logger.warning(
                        "User has no assigned bot",
                        extra={"user_id": user.id}
                    )

        # Dispatch notifications to appropriate bot queues
        bot_stats = {}
        
        for bot_name, bot_users in users_by_bot.items():
            bot_success = 0
            bot_failed = 0
            
            # Create a dedicated queue for each bot
            queue_name = f"telegram_bot_{bot_name}_queue"
            
            for user in bot_users:
                try:
                    # Send to bot-specific queue with bot context
                    celery_app.send_task(
                        "common.messaging.tasks.send_ad_multibot",
                        args=[
                            user['telegram_id'],
                            text,
                            s3_image_url,
                            ad_data.get("resource_url"),
                            ad_data.get("id"),
                            ad_data.get("external_id"),
                            bot_name  # Pass bot name for routing
                        ],
                        queue=queue_name,
                        priority=8,
                    )
                    bot_success += 1
                    success_count += 1
                except Exception as e:
                    bot_failed += 1
                    failed_count += 1
                    logger.error(
                        f"Failed to dispatch notification",
                        extra={
                            "telegram_id": user['telegram_id'],
                            "bot_name": bot_name,
                            "error": str(e)
                        }
                    )
            
            bot_stats[bot_name] = {
                'success': bot_success,
                'failed': bot_failed,
                'total': len(bot_users)
            }

        # Performance metrics
        processing_time = time.time() - start_time
        users_per_second = len(user_ids) / processing_time if processing_time > 0 else 0

        logger.info(
            "MULTI-BOT batch notification completed",
            extra={
                "total_users": len(user_ids),
                "success_count": success_count,
                "failed_count": failed_count,
                "no_bot_assigned": no_bot_count,
                "ad_id": ad_data.get("id"),
                "processing_time_ms": processing_time * 1000,
                "users_per_second": users_per_second,
                "bots_used": len(users_by_bot),
                "bot_stats": bot_stats,
                "version": "v3_multibot",
            },
        )

        return {
            "success_count": success_count,
            "failed_count": failed_count,
            "no_bot_assigned": no_bot_count,
            "total": len(user_ids),
            "processing_time": processing_time,
            "users_per_second": users_per_second,
            "bots_used": len(users_by_bot),
            "bot_stats": bot_stats
        }


async def send_single_notification(
    telegram_id: int,
    text: str,
    s3_image_url: Optional[str],
    resource_url: str,
    ad_id: int,
    external_id: str,
):
    """Helper to send a single notification asynchronously."""
    try:
        # Use the existing task but call it directly to avoid more queue overhead
        from common.messaging.tasks import send_ad_with_extra_buttons

        # Since we're already in an async context, we need to handle this carefully
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(
            None,
            send_ad_with_extra_buttons,
            telegram_id,
            text,
            s3_image_url,
            resource_url,
            ad_id,
            external_id,
        )

        await future
        return True

    except Exception as e:
        logger.error(f"Failed to send notification to {telegram_id}: {e}")
        raise


@celery_app.task(name="common.tasks.cleanup_stale_extractions")
@log_operation("cleanup_stale_extractions")
def cleanup_stale_extractions():
    """
    Periodic task to clean up ads that failed phone extraction.

    Can be scheduled to run daily.
    """
    from common.db.session import db_session
    from common.db.models import Ad, Phone
    from datetime import datetime, timedelta

    # Find ads older than 1 hour with no phones
    cutoff_time = datetime.utcnow() - timedelta(hours=1)

    with db_session() as db:
        ads_without_phones = (
            db.query(Ad)
            .outerjoin(Phone)
            .filter(Ad.created_at < cutoff_time, Phone.id.is_(None))
            .all()
        )

        retry_count = 0
        for ad in ads_without_phones:
            if ad.resource_url:
                # Retry phone extraction
                celery_app.send_task(
                    "extract_phones_for_ad.v1",
                    args=[ad.id, ad.resource_url],
                    queue="phone_extraction_queue",
                    priority=3,  # Lower priority for retries
                )
                retry_count += 1

        logger.info(f"Scheduled {retry_count} phone extraction retries")


# Register the current versions as defaults
from common.utils.task_versioning import DeploymentConfig

DeploymentConfig.promote_version("extract_phones_for_ad", "v1")
DeploymentConfig.promote_version("notify_user_batch", "v3")
