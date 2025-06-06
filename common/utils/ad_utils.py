# common/utils/ad_utils.py

from typing import Dict, Any, Optional, List, Union
from common.db.session import db_session
from common.db.repositories.ad_repository import AdRepository
from common.utils.s3_utils import _upload_image_to_s3
from common.utils.phone_parser import extract_phone_numbers_from_resource
from common.db.models.ad import Ad
from common.utils.logging_config import log_operation, log_context, LogAggregator
from sqlalchemy.exc import IntegrityError

# Import the common utils logger
from . import logger


@log_operation("process_and_insert_ad")
def process_and_insert_ad(
        ad_data: Dict[str, Any],
        property_type: str,
        geo_id: int
) -> Optional[int]:
    """
    Process ad data and insert into the database, including image upload and phone extraction.
    """
    ad_unique_id = str(ad_data.get("id", ""))

    with log_context(logger, ad_id=ad_unique_id, property_type=property_type, geo_id=geo_id):
        if not ad_unique_id:
            logger.warning("Missing ad ID, skipping insertion", extra={'ad_data': ad_data})
            return None

        resource_url = f"https://flatfy.ua/uk/redirect/{ad_unique_id}"

        try:
            with db_session() as db:
                existing_ad = AdRepository.get_by_external_id(db, ad_unique_id)

                if existing_ad:
                    logger.info("Found existing ad", extra={
                        'external_id': ad_unique_id,
                        'database_id': existing_ad.id
                    })
                    return existing_ad.id

                # Process images
                uploaded_image_urls = []
                try:
                    uploaded_image_urls = process_ad_images(ad_data, ad_unique_id)
                    logger.info("Processed images", extra={
                        'ad_id': ad_unique_id,
                        'image_count': len(uploaded_image_urls)
                    })
                except Exception as img_upload_err:
                    logger.error("Error uploading images", exc_info=True, extra={
                        'ad_id': ad_unique_id,
                        'error_type': type(img_upload_err).__name__
                    })

                # Create ad data
                new_ad_data = {
                    "external_id": ad_unique_id,
                    "property_type": property_type,
                    "city": geo_id,
                    "address": ad_data.get("header"),
                    "price": ad_data.get("price"),
                    "square_feet": ad_data.get("area_total"),
                    "rooms_count": ad_data.get("room_count"),
                    "floor": ad_data.get("floor"),
                    "total_floors": ad_data.get("floor_count"),
                    "insert_time": ad_data.get("insert_time"),
                    "description": ad_data.get("text"),
                    "resource_url": resource_url
                }

                # Insert new ad
                try:
                    ad = AdRepository.create_ad(db, new_ad_data)
                    ad_id = ad.id
                except IntegrityError as dup:
                    # Another worker inserted the same ad concurrently
                    db.rollback()
                    logger.warning("Duplicate ad detected during insert, fetching existing", extra={
                        'external_id': ad_unique_id
                    })
                    ad = AdRepository.get_by_external_id(db, ad_unique_id)
                    if not ad:
                        raise  # propagate if truly missing
                    ad_id = ad.id

                logger.info("Created new ad", extra={
                    'external_id': ad_unique_id,
                    'database_id': ad_id
                })

                # Insert image references
                if uploaded_image_urls:
                    for url in uploaded_image_urls:
                        AdRepository.add_image(db, ad_id, url)
                    logger.info("Inserted image references", extra={
                        'ad_id': ad_id,
                        'image_count': len(uploaded_image_urls)
                    })

                # Extract and store phone numbers
                try:
                    result = extract_phone_numbers_from_resource(resource_url)
                    phones = result.phone_numbers
                    viber_link = result.viber_link

                    if phones:
                        for phone in phones:
                            AdRepository.add_phone(db, ad_id, phone)
                        logger.info("Inserted phone numbers", extra={
                            'ad_id': ad_id,
                            'phone_count': len(phones)
                        })

                    if viber_link:
                        AdRepository.add_phone(db, ad_id, None, viber_link)
                        logger.info("Inserted viber link", extra={'ad_id': ad_id})

                except Exception as e:
                    logger.error("Error extracting/storing phones", exc_info=True, extra={
                        'ad_id': ad_id,
                        'error_type': type(e).__name__
                    })

                db.commit()
                logger.info("Successfully processed and inserted ad", extra={
                    'ad_id': ad_id,
                    'external_id': ad_unique_id
                })
                return ad_id

        except Exception as e:
            logger.error("Error in process_and_insert_ad", exc_info=True, extra={
                'external_id': ad_unique_id,
                'error_type': type(e).__name__
            })
            return None


@log_operation("process_ad_images")
def process_ad_images(ad_data: Dict[str, Any], ad_unique_id: str) -> List[str]:
    """
    Process and upload images associated with an ad to S3.
    """
    uploaded_image_urls = []

    with log_context(logger, ad_id=ad_unique_id):
        aggregator = LogAggregator(logger, f"process_ad_images_{ad_unique_id}")

        try:
            images = ad_data.get('images', [])

            for image_info in images:
                image_id = image_info.get("image_id")
                if not image_id:
                    aggregator.add_error("Missing image_id", image_info)
                    continue

                original_url = f"https://market-images.lunstatic.net/lun-ua/720/720/images/{image_id}.webp"
                s3_url = _upload_image_to_s3(original_url, ad_unique_id, max_retries=3)

                if s3_url:
                    uploaded_image_urls.append(s3_url)
                    aggregator.add_item({'image_id': image_id, 's3_url': s3_url}, success=True)
                else:
                    aggregator.add_error("Failed to upload", {'image_id': image_id})

            aggregator.log_summary()
            return uploaded_image_urls

        except Exception as e:
            logger.error("Error processing ad images", exc_info=True, extra={
                'ad_id': ad_unique_id,
                'error_type': type(e).__name__
            })
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
                    logger.warning("Cannot insert images - ad not found", extra={'ad_id': ad_id})
                    return

                for url in image_urls:
                    AdRepository.add_image(db, ad_id, url)

                logger.info("Inserted ad images", extra={
                    'ad_id': ad_id,
                    'image_count': len(image_urls)
                })

        except Exception as e:
            logger.error("Error inserting ad images", exc_info=True, extra={
                'ad_id': ad_id,
                'error_type': type(e).__name__
            })


@log_operation("get_ad_images")
def get_ad_images(ad_id: Union[int, Dict[str, Any]]) -> List[str]:
    """
    Get all images associated with an ad.
    """
    # Handle either an ad dict or direct ad_id
    if isinstance(ad_id, dict):
        ad_id = ad_id.get('id')

    with log_context(logger, ad_id=ad_id):
        if not ad_id:
            logger.warning("No ad_id provided")
            return []

        try:
            with db_session() as db:
                image_urls = AdRepository.get_ad_images(db, ad_id)
                logger.debug("Retrieved ad images", extra={
                    'ad_id': ad_id,
                    'image_count': len(image_urls)
                })
                return image_urls

        except Exception as e:
            logger.error("Error getting ad images", exc_info=True, extra={
                'ad_id': ad_id,
                'error_type': type(e).__name__
            })
            return []