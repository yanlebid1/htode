# common/db/repositories/ad_repository.py

from typing import List, Optional, Dict, Any
import decimal
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from common.db.models import FavoriteAd
from common.db.models.ad import Ad, AdImage, AdPhone
from common.utils.cache import redis_cache, CacheTTL
from common.config import GEO_ID_MAPPING, get_key_by_value
from common.utils.cache_invalidation import invalidate_ad_caches
from common.utils.cache_managers import AdCacheManager, BaseCacheManager
from common.utils.logging_config import log_operation, log_context

# Import the repository logger
from . import logger


class AdRepository:
    """Repository for ad operations"""

    @staticmethod
    @log_operation("get_ad_by_id")
    def get_by_id(db: Session, ad_id: int) -> Optional[Ad]:
        """Get ad by database ID"""
        with log_context(logger, ad_id=ad_id):
            ad = db.query(Ad).filter(Ad.id == ad_id).first()
            if ad:
                logger.debug("Found ad by ID", extra={"ad_id": ad_id})
            else:
                logger.debug("No ad found for ID", extra={"ad_id": ad_id})
            return ad

    @staticmethod
    @log_operation("get_ad_by_external_id")
    def get_by_external_id(db: Session, external_id: str) -> Optional[Ad]:
        """Get ad by external ID"""
        with log_context(logger, external_id=external_id):
            ad = db.query(Ad).filter(Ad.external_id == external_id).first()
            if ad:
                logger.debug(
                    "Found ad by external ID",
                    extra={"external_id": external_id, "ad_id": ad.id},
                )
            else:
                logger.debug(
                    "No ad found for external ID", extra={"external_id": external_id}
                )
            return ad

    @staticmethod
    @log_operation("get_ad_by_resource_url")
    def get_by_resource_url(db: Session, resource_url: str) -> Optional[Ad]:
        """Get ad by resource URL"""
        with log_context(logger, resource_url=resource_url[:100]):
            ad = db.query(Ad).filter(Ad.resource_url == resource_url).first()
            if ad:
                logger.debug(
                    "Found ad by resource URL",
                    extra={"resource_url": resource_url[:100], "ad_id": ad.id},
                )
            else:
                logger.debug(
                    "No ad found for resource URL",
                    extra={"resource_url": resource_url[:100]},
                )
            return ad

    @staticmethod
    @log_operation("create_ad")
    def create_ad(db: Session, ad_data: Dict[str, Any]) -> Ad:
        """Create a new ad with duplicate handling"""
        external_id = ad_data.get("external_id")

        with log_context(logger, external_id=external_id):
            # First, check if ad already exists
            existing_ad = AdRepository.get_by_external_id(db, external_id)
            if existing_ad:
                logger.info(
                    "Ad already exists, returning existing",
                    extra={"ad_id": existing_ad.id, "external_id": external_id},
                )
                return existing_ad

            try:
                ad = Ad(**ad_data)
                db.add(ad)
                db.commit()
                db.refresh(ad)
                logger.info(
                    "Created new ad",
                    extra={"ad_id": ad.id, "external_id": ad.external_id},
                )
                return ad
            except IntegrityError:
                # Handle race condition where another process inserted the same ad
                db.rollback()
                logger.warning(
                    "Duplicate detected during insert, fetching existing",
                    extra={"external_id": external_id},
                )
                existing_ad = AdRepository.get_by_external_id(db, external_id)
                if existing_ad:
                    return existing_ad
                else:
                    logger.error(
                        "Failed to find existing ad after duplicate error",
                        extra={"external_id": external_id},
                    )
                    raise

    @staticmethod
    @log_operation("update_ad")
    def update_ad(db: Session, ad_id: int, ad_data: Dict[str, Any]) -> Optional[Ad]:
        """Update an existing ad"""
        with log_context(logger, ad_id=ad_id):
            ad = AdRepository.get_by_id(db, ad_id)
            if not ad:
                logger.warning("Cannot update ad - not found", extra={"ad_id": ad_id})
                return None

            for key, value in ad_data.items():
                if hasattr(ad, key):
                    setattr(ad, key, value)

            db.commit()
            db.refresh(ad)
            logger.info(
                "Updated ad",
                extra={"ad_id": ad_id, "updated_fields": list(ad_data.keys())},
            )
            return ad

    @staticmethod
    @log_operation("delete_ad")
    def delete_ad(db: Session, ad_id: int) -> bool:
        """Delete an ad by ID"""
        with log_context(logger, ad_id=ad_id):
            ad = AdRepository.get_by_id(db, ad_id)
            if not ad:
                logger.warning("Cannot delete ad - not found", extra={"ad_id": ad_id})
                return False

            db.delete(ad)
            db.commit()
            logger.info("Deleted ad", extra={"ad_id": ad_id})
            return True

    @staticmethod
    @log_operation("get_ads_by_filter")
    def get_ads_by_filter(
        db: Session, filter_data: Dict[str, Any], limit: int = 10, offset: int = 0
    ) -> List[Ad]:
        """Get ads based on filter criteria"""
        with log_context(logger, limit=limit, offset=offset):
            query = db.query(Ad)

            # Apply filters
            if "property_type" in filter_data and filter_data["property_type"]:
                query = query.filter(Ad.property_type == filter_data["property_type"])

            if "city" in filter_data and filter_data["city"]:
                query = query.filter(Ad.city == filter_data["city"])

            if "rooms_count" in filter_data and filter_data["rooms_count"]:
                query = query.filter(Ad.rooms_count.in_(filter_data["rooms_count"]))

            if "price_min" in filter_data and filter_data["price_min"]:
                query = query.filter(Ad.price >= filter_data["price_min"])

            if "price_max" in filter_data and filter_data["price_max"]:
                query = query.filter(Ad.price <= filter_data["price_max"])

            # Apply ordering and pagination
            query = query.order_by(Ad.insert_time.desc())
            query = query.limit(limit).offset(offset)

            ads = query.all()
            logger.debug(
                "Found ads by filter",
                extra={"filter_count": len(filter_data), "result_count": len(ads)},
            )
            return ads

    @staticmethod
    @log_operation("get_full_ad_data")
    def get_full_ad_data(db: Session, ad_id: int) -> Optional[Dict[str, Any]]:
        """Get complete ad data with images and phones"""
        with log_context(logger, ad_id=ad_id):
            # Try to get from cache first using the cache manager
            cached_data = AdCacheManager.get_full_ad_data(ad_id)
            if cached_data:
                logger.debug("Cache hit for full ad data", extra={"ad_id": ad_id})
                return cached_data

            # Cache miss, query database
            ad = (
                db.query(Ad)
                .options(joinedload(Ad.images), joinedload(Ad.phones))
                .filter(Ad.id == ad_id)
                .first()
            )

            if not ad:
                logger.debug("No ad found for full data", extra={"ad_id": ad_id})
                return None

            # Convert to dict
            ad_dict = {
                "id": ad.id,
                "external_id": ad.external_id,
                "property_type": ad.property_type,
                "city": ad.city,
                "address": ad.address,
                "price": (
                    float(ad.price)
                    if isinstance(ad.price, decimal.Decimal)
                    else ad.price
                ),
                "square_feet": (
                    float(ad.square_feet)
                    if isinstance(ad.square_feet, decimal.Decimal)
                    else ad.square_feet
                ),
                "rooms_count": ad.rooms_count,
                "floor": ad.floor,
                "total_floors": ad.total_floors,
                "insert_time": ad.insert_time.isoformat() if ad.insert_time else None,
                "description": ad.description,
                "resource_url": ad.resource_url,
                "original_currency": ad.original_currency,
                "images": [img.image_url for img in ad.images][
                    :20
                ],  # Limit to 20 images
                "phones": [phone.phone for phone in ad.phones if phone.phone][
                    :10
                ],  # Limit to 10 phones
                "viber_link": next(
                    (phone.viber_link for phone in ad.phones if phone.viber_link), None
                ),
            }

            # Cache the result
            AdCacheManager.set_full_ad_data(ad_id, ad_dict)
            logger.debug("Cached full ad data", extra={"ad_id": ad_id})

            return ad_dict

    @staticmethod
    @log_operation("add_image")
    def add_image(db: Session, ad_id: int, image_url: str) -> AdImage:
        """Add an image to an ad"""
        with log_context(logger, ad_id=ad_id, image_url=image_url[:100]):
            image = AdImage(ad_id=ad_id, image_url=image_url)
            db.add(image)
            db.commit()
            db.refresh(image)

            # Use centralized cache invalidation
            invalidate_ad_caches(ad_id)

            logger.info(
                "Added image to ad", extra={"ad_id": ad_id, "image_id": image.id}
            )
            return image

    @staticmethod
    @log_operation("add_phone")
    def add_phone(
        db: Session, ad_id: int, phone: str, viber_link: Optional[str] = None
    ) -> AdPhone:
        """Add a phone to an ad"""
        with log_context(logger, ad_id=ad_id, has_viber=bool(viber_link)):
            ad_phone = AdPhone(ad_id=ad_id, phone=phone, viber_link=viber_link)
            db.add(ad_phone)
            db.commit()
            db.refresh(ad_phone)

            # Use centralized cache invalidation
            invalidate_ad_caches(ad_id)

            logger.info(
                "Added phone to ad",
                extra={
                    "ad_id": ad_id,
                    "phone_id": ad_phone.id,
                    "has_viber": bool(viber_link),
                },
            )
            return ad_phone

    @staticmethod
    @log_operation("get_ad_images")
    def get_ad_images(db: Session, ad_id: int) -> List[str]:
        """Get all images for an ad with caching"""
        with log_context(logger, ad_id=ad_id):
            # Try to get from cache first using the cache manager
            cached_images = AdCacheManager.get_ad_images(ad_id)
            if cached_images:
                logger.debug("Cache hit for ad images", extra={"ad_id": ad_id})
                return cached_images

            # Cache miss, query database
            images = db.query(AdImage).filter(AdImage.ad_id == ad_id).all()
            image_urls = [img.image_url for img in images]

            # Cache the result
            AdCacheManager.set_ad_images(ad_id, image_urls)
            logger.debug(
                "Cached ad images",
                extra={"ad_id": ad_id, "image_count": len(image_urls)},
            )

            return image_urls

    @staticmethod
    @log_operation("get_ad_phones")
    def get_ad_phones(db: Session, ad_id: int) -> List[Dict[str, str]]:
        """Get all phones for an ad"""
        with log_context(logger, ad_id=ad_id):
            phones = db.query(AdPhone).filter(AdPhone.ad_id == ad_id).all()
            result = [{"phone": p.phone, "viber_link": p.viber_link} for p in phones]
            logger.debug(
                "Retrieved ad phones",
                extra={"ad_id": ad_id, "phone_count": len(result)},
            )
            return result

    @staticmethod
    @log_operation("get_full_description")
    def get_full_description(db: Session, resource_url: str) -> Optional[str]:
        """Get full ad description by resource URL with caching"""
        with log_context(logger, resource_url=resource_url[:100]):
            # Try to get from cache first using the cache manager
            cached_description = AdCacheManager.get_ad_description(resource_url)
            if cached_description:
                logger.debug(
                    "Cache hit for ad description",
                    extra={"resource_url": resource_url[:100]},
                )
                return cached_description

            # Cache miss, query database
            ad = db.query(Ad).filter(Ad.resource_url == resource_url).first()
            description = ad.description if ad else None

            # Cache the result if found
            if description:
                AdCacheManager.set_ad_description(resource_url, description)
                logger.debug(
                    "Cached ad description", extra={"resource_url": resource_url[:100]}
                )

            return description

    @staticmethod
    @redis_cache("ads_period", ttl=300)  # 5 minute cache
    @log_operation("fetch_ads_for_period")
    def fetch_ads_for_period(
        db: Session, filters: Dict[str, Any], days: int, limit: int = 3
    ) -> List[Ad]:
        """
        Query ads table, matching the user's filters,
        for ads from the last `days` days. Return up to `limit` ads.
        """
        with log_context(logger, days=days, limit=limit, filter_count=len(filters)):
            query = db.query(Ad)

            # Apply filters
            city = filters.get("city")
            if city:
                geo_id = get_key_by_value(city, GEO_ID_MAPPING)
                if geo_id:
                    query = query.filter(Ad.city == geo_id)

            if filters.get("property_type"):
                query = query.filter(Ad.property_type == filters["property_type"])

            if filters.get("rooms") is not None:
                # Handle array membership
                rooms = filters["rooms"]
                if rooms:
                    query = query.filter(Ad.rooms_count.in_(rooms))

            if filters.get("price_min") is not None:
                query = query.filter(Ad.price >= filters["price_min"])

            if filters.get("price_max") is not None:
                query = query.filter(Ad.price <= filters["price_max"])

            # Filter by date
            days_ago = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.filter(Ad.insert_time >= days_ago)

            # Order by newest first
            query = query.order_by(Ad.insert_time.desc())

            # Limit results
            query = query.limit(limit)

            ads = query.all()
            logger.debug(
                "Fetched ads for period", extra={"days": days, "result_count": len(ads)}
            )
            return ads

    @staticmethod
    @log_operation("find_users_for_ad")
    def find_users_for_ad(db: Session, ad) -> List[int]:
        """
        Finds users whose subscription filters match this ad.
        Uses caching to improve performance.
        """
        from common.db.models.user import User
        from common.db.models.subscription import UserFilter

        # Get ad ID for logging
        ad_id = ad.id if hasattr(ad, "id") else ad.get("id")

        with log_context(logger, ad_id=ad_id):
            try:
                if not ad_id:
                    logger.warning("Cannot find users for ad without ID")
                    return []

                # Create a cache key
                key = f"matching_users:{ad_id}"

                # Try to get from cache
                cached_users = BaseCacheManager.get(key)
                if cached_users:
                    logger.debug("Cache hit for matching users", extra={"ad_id": ad_id})
                    return cached_users

                # Cache miss, perform the query
                # Get ad properties for matching
                if hasattr(ad, "property_type"):
                    # It's an ORM object
                    ad_property_type = ad.property_type
                    ad_city = ad.city
                    ad_rooms = ad.rooms_count
                    ad_price = ad.price
                else:
                    # It's a dictionary
                    ad_property_type = ad.get("property_type")
                    ad_city = ad.get("city")
                    ad_rooms = ad.get("rooms_count")
                    ad_price = ad.get("price")

                # Query users with matching filters
                query = db.query(User.id).join(
                    UserFilter, User.id == UserFilter.user_id
                )

                # Filter for active users only
                query = query.filter(
                    or_(
                        User.free_until > datetime.now(timezone.utc),
                        User.subscription_until > datetime.now(timezone.utc),
                    )
                )

                # Filter for non-paused subscriptions
                query = query.filter(not UserFilter.is_paused)

                # Apply ad property filters
                filters = []

                # Property type filter (if set)
                filters.append(
                    or_(
                        UserFilter.property_type is None,
                        UserFilter.property_type == ad_property_type,
                    )
                )

                # City filter (if set)
                filters.append(or_(UserFilter.city is None, UserFilter.city == ad_city))

                # Rooms filter (array membership)
                filters.append(
                    or_(
                        UserFilter.rooms_count is None,
                        UserFilter.rooms_count.any(ad_rooms),
                    )
                )

                # Price range filter
                filters.append(
                    or_(UserFilter.price_min is None, ad_price >= UserFilter.price_min)
                )

                filters.append(
                    or_(UserFilter.price_max is None, ad_price <= UserFilter.price_max)
                )

                # Apply all filters
                query = query.filter(and_(*filters))

                # Execute query
                results = query.all()
                user_ids = [result[0] for result in results]

                # Cache the results
                BaseCacheManager.set(key, user_ids, CacheTTL.STANDARD)

                logger.info(
                    "Found matching users for ad",
                    extra={"ad_id": ad_id, "user_count": len(user_ids)},
                )

                return user_ids

            except Exception as e:
                logger.error(
                    "Error finding users for ad",
                    exc_info=True,
                    extra={"ad_id": ad_id, "error_type": type(e).__name__},
                )
                return []

    @staticmethod
    @log_operation("delete_ad_with_related")
    def delete_with_related(db: Session, ad_id: int) -> bool:
        """
        Delete an ad and all its related data (images, phones, favorites) using transaction.
        """
        with log_context(logger, ad_id=ad_id):
            try:
                # Get the ad first
                ad = db.query(Ad).get(ad_id)
                if not ad:
                    logger.warning(
                        "Attempted to delete non-existent ad", extra={"ad_id": ad_id}
                    )
                    return False

                resource_url = ad.resource_url

                # Delete related data
                favorites_count = (
                    db.query(FavoriteAd).filter(FavoriteAd.ad_id == ad_id).delete()
                )
                phones_count = db.query(AdPhone).filter(AdPhone.ad_id == ad_id).delete()
                images_count = db.query(AdImage).filter(AdImage.ad_id == ad_id).delete()

                # Delete the ad itself
                db.delete(ad)
                db.commit()

                # Use centralized cache invalidation
                invalidate_ad_caches(ad_id, resource_url)

                logger.info(
                    "Successfully deleted ad and related data",
                    extra={
                        "ad_id": ad_id,
                        "favorites_deleted": favorites_count,
                        "phones_deleted": phones_count,
                        "images_deleted": images_count,
                    },
                )
                return True

            except Exception as e:
                db.rollback()
                logger.error(
                    "Error deleting ad",
                    exc_info=True,
                    extra={"ad_id": ad_id, "error_type": type(e).__name__},
                )
                return False

    @staticmethod
    @log_operation("get_ads_older_than")
    def get_older_than(db: Session, cutoff_date: datetime) -> List[Ad]:
        """
        Get ads older than the specified date.
        """
        with log_context(logger, cutoff_date=cutoff_date.isoformat()):
            ads = db.query(Ad).filter(Ad.insert_time < cutoff_date).all()
            logger.debug(
                "Found ads older than cutoff",
                extra={"cutoff_date": cutoff_date.isoformat(), "ad_count": len(ads)},
            )
            return ads

    @staticmethod
    @log_operation("get_description_by_resource_url")
    def get_description_by_resource_url(
        db: Session, resource_url: str
    ) -> Optional[str]:
        """
        Get the full description of an ad by its resource URL.
        """
        with log_context(logger, resource_url=resource_url[:100]):
            ad = db.query(Ad).filter(Ad.resource_url == resource_url).first()
            if ad:
                logger.debug(
                    "Found description for resource URL",
                    extra={"resource_url": resource_url[:100], "ad_id": ad.id},
                )
                return ad.description
            else:
                logger.debug(
                    "No ad found for resource URL",
                    extra={"resource_url": resource_url[:100]},
                )
                return None
