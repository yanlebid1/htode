# common/utils/ad_utils.py

from typing import Dict, Any, Optional, List, Union
from common.db.session import db_session
from common.db.repositories.ad_repository import AdRepository
from common.utils.s3_utils import _upload_image_to_s3
from common.db.models.ad import Ad
from common.utils.logging_config import log_operation, log_context, LogAggregator

# Import the common utils logger
from . import logger


@log_operation("process_and_insert_ad")
def process_and_insert_ad(
    ad_data: Dict[str, Any],
    property_type: str,
    geo_id: int,
    extract_phones_sync: bool = True,
) -> Optional[int]:
    """Process ad data and insert into the database, including image upload and phone extraction.

    Args:
        ad_data: Dictionary with ad data from API
        property_type: Type of property
        geo_id: City geo ID
        extract_phones_sync: If True, extract phones synchronously before returning (ensures complete data)
                           If False, schedule async extraction (faster but incomplete data initially)
    """
    # Use the AdService implementation
    from common.services.ad_service import AdService

    with db_session() as db:
        return AdService.process_and_insert_ad(
            db=db,
            ad_data=ad_data,
            property_type=property_type,
            geo_id=geo_id,
            extract_phones_sync=extract_phones_sync,
        )


@log_operation("process_ad_images")
def process_ad_images(ad_data: Dict[str, Any], ad_unique_id: str) -> List[str]:
    """
    Process and upload images associated with an ad to S3.
    """
    uploaded_image_urls = []

    with log_context(logger, ad_id=ad_unique_id):
        aggregator = LogAggregator(logger, f"process_ad_images_{ad_unique_id}")

        try:
            images = ad_data.get("images", [])

            for image_info in images:
                image_id = image_info.get("image_id")
                if not image_id:
                    aggregator.add_error("Missing image_id", image_info)
                    continue

                original_url = f"https://market-images.lunstatic.net/lun-ua/720/720/images/{image_id}.webp"
                s3_url = _upload_image_to_s3(original_url, ad_unique_id, max_retries=3)

                if s3_url:
                    uploaded_image_urls.append(s3_url)
                    aggregator.add_item(
                        {"image_id": image_id, "s3_url": s3_url}, success=True
                    )
                else:
                    aggregator.add_error("Failed to upload", {"image_id": image_id})

            aggregator.log_summary()
            return uploaded_image_urls

        except Exception as e:
            logger.error(
                "Error processing ad images",
                exc_info=True,
                extra={"ad_id": ad_unique_id, "error_type": type(e).__name__},
            )
            return uploaded_image_urls


@log_operation("insert_ad_images")
def insert_ad_images(ad_id: int, image_urls: List[str]) -> None:
    """
    Insert ad images into the database.
    """
    if not image_urls:
        return

    with log_context(logger, ad_id=ad_id, image_count=len(image_urls)):
        try:
            with db_session() as db:
                ad = db.query(Ad).get(ad_id)

                if not ad:
                    logger.warning(
                        "Cannot insert images - ad not found", extra={"ad_id": ad_id}
                    )
                    return

                for url in image_urls:
                    AdRepository.add_image(db, ad_id, url)

                logger.info(
                    "Inserted ad images",
                    extra={"ad_id": ad_id, "image_count": len(image_urls)},
                )

        except Exception as e:
            logger.error(
                "Error inserting ad images",
                exc_info=True,
                extra={"ad_id": ad_id, "error_type": type(e).__name__},
            )


@log_operation("get_ad_images")
def get_ad_images(ad_id: Union[int, Dict[str, Any]]) -> List[str]:
    """
    Get all images associated with an ad.
    """
    # Handle either an ad dict or direct ad_id
    if isinstance(ad_id, dict):
        ad_id = ad_id.get("id")

    with log_context(logger, ad_id=ad_id):
        if not ad_id:
            logger.warning("No ad_id provided")
            return []

        try:
            with db_session() as db:
                image_urls = AdRepository.get_ad_images(db, ad_id)
                logger.debug(
                    "Retrieved ad images",
                    extra={"ad_id": ad_id, "image_count": len(image_urls)},
                )
                return image_urls

        except Exception as e:
            logger.error(
                "Error getting ad images",
                exc_info=True,
                extra={"ad_id": ad_id, "error_type": type(e).__name__},
            )
            return []
