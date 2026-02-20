# services/notifier_service/app/tasks.py

from common.celery_app import celery_app
from common.db.operations import find_users_for_ad
from common.utils.unified_request_utils import fetch_ads_flatfy
from common.config import GEO_ID_MAPPING, get_key_by_value, build_ad_text
from common.utils.ad_utils import (
    process_and_insert_ad,
    get_ad_images as utils_get_ad_images,
)

# Import logging utilities from common modules
from common.utils.logging_config import log_context, log_operation, LogAggregator
from common.utils.tracing import init_tracing
from common.constants import NOTIFICATION_BATCH_SIZE

# Import the service logger
from . import logger

# Initialize tracing on module load (worker startup)
init_tracing("notifier_service")

# TELEGRAM_SEND_TASK = "telegram_service.app.tasks.send_ad_with_extra_buttons"
TELEGRAM_SEND_TASK = "common.messaging.tasks.send_ad_with_extra_buttons"


@log_operation("get_ad_images")
def get_ad_images_local(ad):
    """
    Get images for an ad (renamed to avoid recursion)
    """
    ad_id = ad.get("id")
    with log_context(logger, ad_id=ad_id):
        images = utils_get_ad_images(ad_id)  # Call the imported function
        logger.debug(
            f"Retrieved {len(images) if images else 0} images for ad",
            extra={"ad_id": ad_id, "images_count": len(images) if images else 0},
        )
        return images


@log_operation("insert_ad")
def insert_ad(ad_data, property_type, geo_id):
    """Insert the ad into the ad table"""
    ad_id = ad_data.get("id")
    with log_context(logger, ad_id=ad_id, property_type=property_type, geo_id=geo_id):
        logger.info(
            "Inserting ad",
            extra={"ad_id": ad_id, "property_type": property_type, "geo_id": geo_id},
        )
        return process_and_insert_ad(ad_data, property_type, geo_id)


@celery_app.task(name="notifier_service.app.tasks.sort_and_notify_new_ads")
@log_operation("sort_and_notify_new_ads")
def sort_and_notify_new_ads(new_ads):
    """
    Receives a list of newly inserted ads from the scraper,
    checks which users want each ad, and sends them via
    Telegram or another channel.
    """
    with log_context(logger, ads_count=len(new_ads), operation="sort_and_notify"):
        logger.info(
            "Received new ads for sorting/notification",
            extra={"ads_count": len(new_ads)},
        )

        aggregator = LogAggregator(logger, "sort_and_notify_new_ads")

        for ad in new_ads:
            ad_id = ad.get("id")
            with log_context(logger, ad_id=ad_id):
                try:
                    s3_image_urls = (
                        get_ad_images_local(ad)[0] if get_ad_images_local(ad) else None
                    )
                    users_to_notify = find_users_for_ad(ad)

                    logger.info(
                        "Found users to notify for ad",
                        extra={"ad_id": ad_id, "users_count": len(users_to_notify)},
                    )

                    # ALWAYS use batch notifications for consistency and performance

                    # Convert ad to dict format for serialization
                    ad_dict = {
                        "id": ad.get("id"),
                        "external_id": ad.get("external_id"),
                        "price": ad.get("price"),
                        "city": ad.get("city"),
                        "address": ad.get("address"),
                        "rooms_count": ad.get("rooms_count"),
                        "square_feet": ad.get("square_feet"),
                        "floor": ad.get("floor"),
                        "total_floors": ad.get("total_floors"),
                        "resource_url": ad.get("resource_url"),
                    }

                    # ULTRA-FAST BATCHING: Larger batches for maximum throughput
                    total_batches = 0
                    for i in range(0, len(users_to_notify), NOTIFICATION_BATCH_SIZE):
                        batch = users_to_notify[i : i + NOTIFICATION_BATCH_SIZE]
                        
                        # Use the batch notification task for ALL notifications
                        celery_app.send_task(
                            "common.tasks.notify_user_batch",
                            args=[batch, ad_dict, s3_image_urls],
                            queue="notification_queue",
                            priority=1,  # Low priority
                        )

                        aggregator.add_item(
                            {
                                "ad_id": ad_id,
                                "batch_size": len(batch),
                                "batch_start": i,
                            },
                            success=True,
                        )
                        total_batches += 1

                    logger.info(
                        "Scheduled batch notifications",
                        extra={
                            "ad_id": ad_id,
                            "total_users": len(users_to_notify),
                            "batches": total_batches,
                            "avg_batch_size": len(users_to_notify) / total_batches if total_batches > 0 else 0,
                        },
                    )

                    aggregator.add_item(
                        {"ad_id": ad_id, "notified_users": len(users_to_notify)},
                        success=True,
                    )

                except Exception as e:
                    logger.error(
                        "Error processing ad for notification",
                        exc_info=True,
                        extra={"ad_id": ad_id, "error_type": type(e).__name__},
                    )
                    aggregator.add_error(str(e), {"ad_id": ad_id})

        aggregator.log_summary()


@log_operation("notify_user_about_ad")
def _notify_user_about_ad(user_id, ad, s3_image_urls):

    with log_context(logger, user_id=user_id, ad_id=ad.get("id")):
        text = build_ad_text(ad)

        logger.info(
            "Notifying user about ad",
            extra={
                "user_id": user_id,
                "ad_id": ad.get("id"),
                "external_id": ad.get("external_id"),
            },
        )

        celery_app.send_task(
            "common.messaging.tasks.send_ad_with_extra_buttons",
            args=[
                user_id,
                text,
                s3_image_urls,
                ad.get("resource_url"),
                ad.get("id"),
                ad.get("external_id"),
            ],
            queue="telegram_queue",
        )


@celery_app.task(name="notifier_service.app.tasks.notify_user_with_ads")
@log_operation("notify_user_with_ads")
def notify_user_with_ads(telegram_id, user_filters):
    with log_context(logger, telegram_id=telegram_id, filters=user_filters):
        try:
            logger.info(
                "Starting to notify user with ads",
                extra={
                    "telegram_id": telegram_id,
                    "city": user_filters.get("city"),
                    "rooms": user_filters.get("rooms"),
                    "price_range": f"{user_filters.get('price_min')}-{user_filters.get('price_max')}",
                },
            )

            city = user_filters.get("city")
            property_type = 2
            geo_id = get_key_by_value(city, GEO_ID_MAPPING)

            # Build optional params
            room_counts = user_filters.get("rooms")
            price_min = user_filters.get("price_min")
            price_max = user_filters.get("price_max")

            data = fetch_ads_flatfy(
                geo_id=geo_id,
                page=1,
                room_count=room_counts,
                price_min=price_min,
                price_max=price_max,
                section_id=property_type,
            )

            if not data:
                logger.info(
                    "No ads found with these filters",
                    extra={"telegram_id": telegram_id, "filters": user_filters},
                )
                return

            logger.info(
                "Received data from fetch_ads_flatfy",
                extra={"telegram_id": telegram_id, "ads_count": len(data)},
            )

            aggregator = LogAggregator(logger, f"notify_user_with_ads_{telegram_id}")

            for ad in data:
                with log_context(logger, ad_id=ad.get("id")):
                    try:
                        # handle each ad similarly
                        ad_id = process_and_insert_ad(ad, property_type, geo_id)
                        if not ad_id:
                            logger.warning(
                                "Failed to insert ad", extra={"ad_id": ad.get("id")}
                            )
                            aggregator.add_error(
                                "Failed to insert", {"ad_id": ad.get("id")}
                            )
                            continue

                        # Get the first image for the ad
                        ad_images = utils_get_ad_images(ad_id)
                        first_image = ad_images[0] if ad_images else None

                        ad_external_id = str(ad.get("id"))
                        resource_url = f"https://flatfy.ua/uk/redirect/{ad_external_id}"

                        text = build_ad_text({
                            "price": ad.get("price"),
                            "city": city,
                            "address": ad.get("header"),
                            "rooms_count": ad.get("room_count"),
                            "square_feet": ad.get("area_total"),
                            "floor": ad.get("floor"),
                            "total_floors": ad.get("floor_count"),
                        })

                        celery_args = [
                            telegram_id,
                            text,
                            first_image,
                            resource_url,
                            ad_id,
                            ad_external_id,
                        ]

                        logger.info(
                            "Sending notification for ad",
                            extra={
                                "telegram_id": telegram_id,
                                "ad_id": ad_id,
                                "external_id": ad_external_id,
                            },
                        )

                        celery_app.send_task(
                            TELEGRAM_SEND_TASK, args=celery_args, queue="telegram_queue"
                        )

                        aggregator.add_item({"ad_id": ad_id}, success=True)

                    except Exception as e:
                        logger.error(
                            "Error processing ad for notification",
                            exc_info=True,
                            extra={
                                "ad_id": ad.get("id"),
                                "telegram_id": telegram_id,
                                "error_type": type(e).__name__,
                            },
                        )
                        aggregator.add_error(str(e), {"ad_id": ad.get("id")})

            aggregator.log_summary()

        except Exception as e:
            logger.error(
                "Error notifying user with ads",
                exc_info=True,
                extra={"telegram_id": telegram_id, "error_type": type(e).__name__},
            )
            raise
