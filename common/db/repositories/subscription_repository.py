# common/db/repositories/subscription_repository.py

from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from common.db.models.subscription import UserFilter
from common.db.models.user import User
from common.utils.cache import CacheTTL
from common.config import GEO_ID_MAPPING, get_key_by_value
from common.utils.cache_managers import (
    SubscriptionCacheManager,
    UserCacheManager,
    BaseCacheManager,
)
from common.utils.cache import get_entity_cache_key
from common.utils.logging_config import log_operation, log_context, LogAggregator

# Import the repository logger
from . import logger


class SubscriptionRepository:
    """Repository for subscription operations"""

    @staticmethod
    @log_operation("get_user_filters")
    def get_user_filters(db: Session, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user filters with caching"""
        with log_context(logger, user_id=user_id):
            # Try to get from cache first using the cache manager
            cached_filters = UserCacheManager.get_filters(user_id)
            if cached_filters:
                logger.debug("Cache hit for user filters", extra={"user_id": user_id})
                return cached_filters

            # Cache miss, query database
            filters = db.query(UserFilter).filter(UserFilter.user_id == user_id).first()
            if not filters:
                logger.debug("No filters found for user", extra={"user_id": user_id})
                return None

            # Convert to dict
            filters_dict = {
                "id": filters.id,
                "user_id": filters.user_id,
                "property_type": filters.property_type,
                "city": filters.city,
                "rooms_count": filters.rooms_count,
                "price_min": filters.price_min,
                "price_max": filters.price_max,
                "is_paused": filters.is_paused,
                "floor_max": filters.floor_max,
                "is_not_first_floor": filters.is_not_first_floor,
                "is_not_last_floor": filters.is_not_last_floor,
                "is_last_floor_only": filters.is_last_floor_only,
                "pets_allowed": filters.pets_allowed,
                "without_broker": filters.without_broker,
            }

            # Cache the result
            UserCacheManager.set_filters(user_id, filters_dict)
            logger.debug("Cached user filters", extra={"user_id": user_id})

            return filters_dict

    @staticmethod
    @log_operation("update_user_filter")
    def update_user_filter(
        db: Session, user_id: int, filters_data: Dict[str, Any]
    ) -> UserFilter:
        """Update or create user filters"""
        with log_context(logger, user_id=user_id):
            # Check if user exists first
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.error("User not found", extra={"user_id": user_id})
                raise ValueError(f"User ID {user_id} does not exist")

            # Convert city name to ID if needed
            city = filters_data.get("city")
            if city:
                geo_id = get_key_by_value(city, GEO_ID_MAPPING)
                logger.debug(
                    "Converted city to geo_id", extra={"city": city, "geo_id": geo_id}
                )
            else:
                geo_id = None

            # Get existing filter or create new one
            user_filter = (
                db.query(UserFilter).filter(UserFilter.user_id == user_id).first()
            )
            if not user_filter:
                user_filter = UserFilter(user_id=user_id)
                db.add(user_filter)
                logger.debug("Creating new filter", extra={"user_id": user_id})
            else:
                logger.debug("Updating existing filter", extra={"user_id": user_id})

            # Update fields from filters_data
            updated_fields = []

            if "property_type" in filters_data:
                user_filter.property_type = filters_data.get("property_type")
                updated_fields.append("property_type")

            if "city" in filters_data:
                user_filter.city = geo_id
                updated_fields.append("city")

            rooms_count = filters_data.get("rooms_count")
            if rooms_count is None:
                rooms_count = filters_data.get("rooms")
            user_filter.rooms_count = rooms_count
            updated_fields.append("rooms_count")

            if "price_min" in filters_data:
                user_filter.price_min = filters_data.get("price_min")
                updated_fields.append("price_min")

            if "price_max" in filters_data:
                user_filter.price_max = filters_data.get("price_max")
                updated_fields.append("price_max")

            # Advanced filters if provided
            if "floor_max" in filters_data:
                user_filter.floor_max = filters_data.get("floor_max")
                updated_fields.append("floor_max")

            if "is_not_first_floor" in filters_data:
                user_filter.is_not_first_floor = filters_data.get("is_not_first_floor")
                updated_fields.append("is_not_first_floor")

            if "is_not_last_floor" in filters_data:
                user_filter.is_not_last_floor = filters_data.get("is_not_last_floor")
                updated_fields.append("is_not_last_floor")

            if "is_last_floor_only" in filters_data:
                user_filter.is_last_floor_only = filters_data.get("is_last_floor_only")
                updated_fields.append("is_last_floor_only")

            if "pets_allowed" in filters_data:
                user_filter.pets_allowed = filters_data.get("pets_allowed")
                updated_fields.append("pets_allowed")

            if "without_broker" in filters_data:
                user_filter.without_broker = filters_data.get("without_broker")
                updated_fields.append("without_broker")

            db.commit()
            db.refresh(user_filter)

            # Invalidate cache using the cache manager
            SubscriptionCacheManager.invalidate_all(user_id)
            UserCacheManager.invalidate_all(user_id)

            logger.info(
                "Updated user filter",
                extra={"user_id": user_id, "updated_fields": updated_fields},
            )

            return user_filter

    @staticmethod
    @log_operation("enable_subscription")
    def enable_subscription(db: Session, user_id: int) -> bool:
        """Enable subscription for a user"""
        with log_context(logger, user_id=user_id):
            filters = db.query(UserFilter).filter(UserFilter.user_id == user_id).all()
            if not filters:
                logger.warning("No filters found to enable", extra={"user_id": user_id})
                return False

            count = 0
            for f in filters:
                f.is_paused = False
                count += 1

            db.commit()

            # Invalidate cache using the cache manager
            SubscriptionCacheManager.invalidate_all(user_id)

            logger.info(
                "Enabled subscription",
                extra={"user_id": user_id, "filters_updated": count},
            )

            return True

    @staticmethod
    @log_operation("disable_subscription")
    def disable_subscription(db: Session, user_id: int) -> bool:
        """Disable subscription for a user"""
        with log_context(logger, user_id=user_id):
            filters = db.query(UserFilter).filter(UserFilter.user_id == user_id).all()
            if not filters:
                logger.warning(
                    "No filters found to disable", extra={"user_id": user_id}
                )
                return False

            count = 0
            for f in filters:
                f.is_paused = True
                count += 1

            db.commit()

            # Invalidate cache using the cache manager
            SubscriptionCacheManager.invalidate_all(user_id)

            logger.info(
                "Disabled subscription",
                extra={"user_id": user_id, "filters_updated": count},
            )

            return True

    @staticmethod
    @log_operation("remove_subscription")
    def remove_subscription(db: Session, subscription_id: int, user_id: int) -> bool:
        """Remove a subscription"""
        with log_context(logger, subscription_id=subscription_id, user_id=user_id):
            filter_to_remove = (
                db.query(UserFilter)
                .filter(UserFilter.id == subscription_id, UserFilter.user_id == user_id)
                .first()
            )

            if not filter_to_remove:
                logger.warning(
                    "Subscription not found",
                    extra={"subscription_id": subscription_id, "user_id": user_id},
                )
                return False

            db.delete(filter_to_remove)
            db.commit()

            # Invalidate cache using the cache manager
            SubscriptionCacheManager.invalidate_all(user_id, subscription_id)

            logger.info(
                "Removed subscription",
                extra={"subscription_id": subscription_id, "user_id": user_id},
            )

            return True

    @staticmethod
    @log_operation("count_subscriptions")
    def count_subscriptions(db: Session, user_id: int) -> int:
        """Count the number of subscriptions for a user"""
        with log_context(logger, user_id=user_id):
            count = db.query(UserFilter).filter(UserFilter.user_id == user_id).count()
            logger.debug(
                "Counted subscriptions", extra={"user_id": user_id, "count": count}
            )
            return count

    @staticmethod
    @log_operation("list_subscriptions_paginated")
    def list_subscriptions_paginated(
        db: Session, user_id: int, page: int = 0, per_page: int = 5
    ) -> List[Dict[str, Any]]:
        """Get a paginated list of subscriptions with caching"""
        with log_context(logger, user_id=user_id, page=page, per_page=per_page):
            # Create a cache key that includes pagination parameters
            cache_key = get_entity_cache_key(
                "user_subscriptions_paginated", user_id, f"{page}:{per_page}"
            )

            # Try to get from the cache first
            cached_data = BaseCacheManager.get(cache_key)
            if cached_data:
                logger.debug(
                    "Cache hit for paginated subscriptions",
                    extra={"user_id": user_id, "page": page},
                )
                return cached_data

            # Cache miss, query database
            offset = page * per_page

            filters = (
                db.query(UserFilter)
                .filter(UserFilter.user_id == user_id)
                .order_by(UserFilter.id)
                .limit(per_page)
                .offset(offset)
                .all()
            )

            # Format the results
            aggregator = LogAggregator(
                logger, f"list_subscriptions_paginated_{user_id}"
            )
            result = []

            for f in filters:
                # Convert geo_id to city name if available
                city_name = GEO_ID_MAPPING.get(f.city) if f.city else None

                sub_dict = {
                    "id": f.id,
                    "user_id": f.user_id,
                    "property_type": f.property_type,
                    "city": f.city,
                    "city_name": city_name,
                    "rooms_count": f.rooms_count,
                    "price_min": f.price_min,
                    "price_max": f.price_max,
                    "is_paused": f.is_paused,
                }
                result.append(sub_dict)
                aggregator.add_item({"subscription_id": f.id}, success=True)

            # Cache the result (shorter TTL for paginated data)
            BaseCacheManager.set(cache_key, result, CacheTTL.SHORT)

            aggregator.log_summary()
            logger.debug(
                "Retrieved and cached paginated subscriptions",
                extra={"user_id": user_id, "page": page, "result_count": len(result)},
            )

            return result

    @staticmethod
    @log_operation("list_subscriptions")
    def list_subscriptions(db: Session, user_id: int) -> List[Dict[str, Any]]:
        """List user subscriptions with caching"""
        with log_context(logger, user_id=user_id):
            # Try to get from the cache first using the cache manager
            cached_subscriptions = SubscriptionCacheManager.get_user_subscriptions(
                user_id
            )
            if cached_subscriptions:
                logger.debug("Cache hit for subscriptions", extra={"user_id": user_id})
                return cached_subscriptions

            # Cache miss, query database
            filters = db.query(UserFilter).filter(UserFilter.user_id == user_id).all()

            aggregator = LogAggregator(logger, f"list_subscriptions_{user_id}")
            result = []

            for f in filters:
                # Convert geo_id to city name if available
                city_name = GEO_ID_MAPPING.get(f.city) if f.city else None

                sub_dict = {
                    "id": f.id,
                    "property_type": f.property_type,
                    "city_id": f.city,
                    "city_name": city_name,
                    "rooms_count": f.rooms_count,
                    "price_min": f.price_min,
                    "price_max": f.price_max,
                    "is_paused": f.is_paused,
                }
                result.append(sub_dict)
                aggregator.add_item({"subscription_id": f.id}, success=True)

            # Cache the result
            SubscriptionCacheManager.set_user_subscriptions(user_id, result)

            aggregator.log_summary()
            logger.debug(
                "Retrieved and cached subscriptions",
                extra={"user_id": user_id, "result_count": len(result)},
            )

            return result

    @staticmethod
    @log_operation("transfer_subscriptions")
    def transfer_subscriptions(db: Session, from_user_id: int, to_user_id: int) -> bool:
        """Transfer subscriptions from one user to another"""
        with log_context(logger, from_user_id=from_user_id, to_user_id=to_user_id):
            # Get all subscriptions for the source user
            subscriptions = (
                db.query(UserFilter).filter(UserFilter.user_id == from_user_id).all()
            )

            if not subscriptions:
                logger.info(
                    "No subscriptions to transfer",
                    extra={"from_user_id": from_user_id, "to_user_id": to_user_id},
                )
                return True  # Nothing to transfer

            aggregator = LogAggregator(
                logger, f"transfer_subscriptions_{from_user_id}_to_{to_user_id}"
            )
            transferred_count = 0

            # Check if target user already has any of these subscriptions
            for sub in subscriptions:
                # Check for duplicate with same parameters
                duplicate = (
                    db.query(UserFilter)
                    .filter(
                        UserFilter.user_id == to_user_id,
                        UserFilter.property_type == sub.property_type,
                        UserFilter.city == sub.city,
                        UserFilter.price_min == sub.price_min,
                        UserFilter.price_max == sub.price_max,
                    )
                    .first()
                )

                if not duplicate:
                    # Create a new subscription for the target user
                    new_sub = UserFilter(
                        user_id=to_user_id,
                        property_type=sub.property_type,
                        city=sub.city,
                        rooms_count=sub.rooms_count,
                        price_min=sub.price_min,
                        price_max=sub.price_max,
                        is_paused=sub.is_paused,
                        floor_max=sub.floor_max,
                        is_not_first_floor=sub.is_not_first_floor,
                        is_not_last_floor=sub.is_not_last_floor,
                        is_last_floor_only=sub.is_last_floor_only,
                        pets_allowed=sub.pets_allowed,
                        without_broker=sub.without_broker,
                    )
                    db.add(new_sub)
                    transferred_count += 1
                    aggregator.add_item({"subscription_id": sub.id}, success=True)
                else:
                    aggregator.add_item(
                        {"subscription_id": sub.id, "reason": "duplicate"},
                        success=False,
                    )

            # Commit changes
            db.commit()

            aggregator.log_summary()
            logger.info(
                "Transferred subscriptions",
                extra={
                    "from_user_id": from_user_id,
                    "to_user_id": to_user_id,
                    "transferred_count": transferred_count,
                    "total_count": len(subscriptions),
                },
            )

            return True

    @staticmethod
    @log_operation("add_subscription")
    def add_subscription(
        db: Session, user_id: int, filter_data: Dict[str, Any]
    ) -> UserFilter:
        """Add a new subscription"""
        with log_context(logger, user_id=user_id):
            user_filter = UserFilter(
                user_id=user_id,
                property_type=filter_data.get("property_type"),
                city=filter_data.get("city"),
                rooms_count=filter_data.get("rooms_count"),
                price_min=filter_data.get("price_min"),
                price_max=filter_data.get("price_max"),
            )
            db.add(user_filter)
            db.commit()
            db.refresh(user_filter)

            logger.info(
                "Added new subscription",
                extra={"user_id": user_id, "subscription_id": user_filter.id},
            )

            return user_filter

    @staticmethod
    @log_operation("enable_subscription_by_id")
    def enable_subscription_by_id(
        db: Session, subscription_id: int, user_id: int
    ) -> bool:
        """
        Enable a specific subscription by its ID.
        """
        with log_context(logger, subscription_id=subscription_id, user_id=user_id):
            subscription = (
                db.query(UserFilter)
                .filter(UserFilter.id == subscription_id, UserFilter.user_id == user_id)
                .first()
            )

            if not subscription:
                logger.warning(
                    "Subscription not found",
                    extra={"subscription_id": subscription_id, "user_id": user_id},
                )
                return False

            subscription.is_paused = False
            db.commit()

            logger.info(
                "Enabled subscription by ID",
                extra={"subscription_id": subscription_id, "user_id": user_id},
            )

            return True

    @staticmethod
    @log_operation("get_subscription_data")
    def get_subscription_data(db: Session, user_id: int) -> Optional[Dict[str, Any]]:
        """Get subscription data for a user"""
        with log_context(logger, user_id=user_id):
            user_filter = (
                db.query(UserFilter).filter(UserFilter.user_id == user_id).first()
            )

            if not user_filter:
                logger.debug("No subscription data found", extra={"user_id": user_id})
                return None

            result = {
                "id": user_filter.id,
                "user_id": user_filter.user_id,
                "property_type": user_filter.property_type,
                "city": user_filter.city,
                "rooms_count": user_filter.rooms_count,
                "price_min": user_filter.price_min,
                "price_max": user_filter.price_max,
                "is_paused": user_filter.is_paused,
            }

            logger.debug("Retrieved subscription data", extra={"user_id": user_id})
            return result

    @staticmethod
    @log_operation("get_active_cities")
    def get_active_cities(db: Session) -> List[int]:
        """
        Get all distinct cities from active users' filters.
        """
        with log_context(logger):
            try:
                cities = (
                    db.query(UserFilter.city)
                    .join(User, UserFilter.user_id == User.id)
                    .filter(
                        UserFilter.city.isnot(None),
                        not UserFilter.is_paused,
                        or_(
                            User.subscription_until > datetime.now(),
                            User.free_until > datetime.now(),
                        ),
                    )
                    .distinct()
                    .all()
                )

                # Extract city IDs from result tuples
                city_ids = [city[0] for city in cities]

                logger.debug(
                    "Retrieved active cities", extra={"city_count": len(city_ids)}
                )

                return city_ids
            except Exception as e:
                logger.error(
                    "Error getting active cities",
                    exc_info=True,
                    extra={"error_type": type(e).__name__},
                )
                return []
