# system/maintenance/cleanup.py

from ._common import (
    celery_app,
    db_session,
    time,
    datetime,
    timedelta,
    logger,
    log_operation,
    log_context,
    LogAggregator,
    CLEANUP_DEFAULT_DAYS,
    Dict,
    Any,
)
from common.db.models.verification import Verification as VerificationCode
from common.db.repositories.ad_repository import AdRepository
from common.utils.s3_utils import delete_s3_image
from common.utils.cache_managers import AdCacheManager


@celery_app.task(name="system.maintenance.cleanup_old_ads")
@log_operation("cleanup_old_ads")
def cleanup_old_ads(days_old: int = CLEANUP_DEFAULT_DAYS, check_activity: bool = True) -> Dict[str, Any]:
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
        logger.info(
            f"Starting cleanup of ads older than {days_old} days",
            extra={"check_activity": check_activity},
        )

        try:
            with db_session() as db:
                # Calculate cutoff date
                cutoff_date = datetime.now() - timedelta(days=days_old)

                # Get old ads
                old_ads = AdRepository.get_older_than(db, cutoff_date)
                logger.info(
                    "Found old ads for cleanup",
                    extra={
                        "ad_count": len(old_ads),
                        "cutoff_date": cutoff_date.isoformat(),
                    },
                )

                for ad in old_ads:
                    should_delete = True

                    # Check if ad is still active if requested
                    if check_activity:
                        from common.services.ad_service import AdService

                        if not AdService.is_ad_inactive(ad.resource_url):
                            should_delete = False
                            logger.debug(
                                "Ad is still active, skipping",
                                extra={"ad_id": ad.id, "resource_url": ad.resource_url},
                            )

                    if should_delete:
                        # Get ad images before deleting
                        images = AdRepository.get_ad_images(db, ad.id)

                        # Delete the ad and related data
                        if AdRepository.delete_with_related(db, ad.id):
                            deleted_count += 1
                            aggregator.add_item({"ad_id": ad.id}, success=True)

                            # Delete images from S3
                            for image_url in images:
                                if delete_s3_image(image_url):
                                    images_deleted_count += 1

                            # Clear cache
                            clear_ad_cache(ad.id, ad.resource_url)
                        else:
                            aggregator.add_error(
                                "Failed to delete ad", {"ad_id": ad.id}
                            )

            execution_time = time.time() - start_time
            aggregator.log_summary()

            logger.info(
                "Cleanup completed",
                extra={
                    "execution_time": execution_time,
                    "ads_deleted": deleted_count,
                    "images_deleted": images_deleted_count,
                },
            )

            return {
                "status": "completed",
                "ads_deleted": deleted_count,
                "images_deleted": images_deleted_count,
                "execution_time_seconds": execution_time,
            }
        except Exception as e:
            logger.error(
                "Error in cleanup_old_ads",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            aggregator.add_error(str(e), {})
            aggregator.log_summary()
            return {
                "status": "error",
                "error": str(e),
                "execution_time_seconds": time.time() - start_time,
            }


@log_operation("clear_ad_cache")
def clear_ad_cache(ad_id: int, resource_url: str = None):
    """
    Clear all cache entries related to a specific ad

    Args:
        ad_id: ID of the ad
        resource_url: Optional resource URL for additional cache keys
    """
    with log_context(logger, ad_id=ad_id, resource_url=resource_url):
        # Use the cache manager to handle invalidation
        deleted_count = AdCacheManager.invalidate_all(ad_id, resource_url)
        logger.debug(
            "Cleared cache for ad",
            extra={"ad_id": ad_id, "deleted_count": deleted_count},
        )


@celery_app.task(name="system.maintenance.cleanup_expired_verification_codes")
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
                from sqlalchemy import text

                # Cleanup verification codes
                verification_codes_deleted = (
                    db.query(VerificationCode)
                    .filter(VerificationCode.expires_at < datetime.now())
                    .delete()
                )

                # Cleanup email verification tokens
                # Using raw SQL because the EmailVerificationToken model appears to be missing
                result = db.execute(
                    text(
                        "DELETE FROM email_verification_tokens WHERE expires_at < CURRENT_TIMESTAMP"
                    )
                )
                email_tokens_deleted = result.rowcount

                db.commit()

                logger.info(
                    "Cleaned up verification codes and tokens",
                    extra={
                        "verification_codes_deleted": verification_codes_deleted,
                        "email_tokens_deleted": email_tokens_deleted,
                    },
                )

                return {
                    "verification_codes_deleted": verification_codes_deleted,
                    "email_tokens_deleted": email_tokens_deleted,
                }
        except Exception as e:
            logger.error(
                "Error cleaning up expired verification codes",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            return {
                "verification_codes_deleted": 0,
                "email_tokens_deleted": 0,
                "error": str(e),
            }
