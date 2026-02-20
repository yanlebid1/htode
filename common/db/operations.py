# common/db/operations.py

"""
This module contains database operations that combine models and repositories.
It should be imported after both models and repositories are initialized.
"""
from typing import List, Dict, Any, Optional, Union, Tuple
from datetime import datetime, timedelta, date

from sqlalchemy import or_

from common.db.session import db_session
from common.db.models.user import User
from common.db.models.subscription import UserFilter
from common.db.models.ad import Ad, AdPhone
from common.db.repositories.user_repository import UserRepository
from common.db.repositories.subscription_repository import SubscriptionRepository
from common.db.repositories.ad_repository import AdRepository
from common.db.repositories.favorite_repository import FavoriteRepository
from common.utils.cache import CacheTTL
from common.utils.phone_utils import extract_phone_numbers_from_resource
from common.utils.cache_invalidation import (
    invalidate_favorite_caches,
    invalidate_subscription_caches,
    invalidate_user_caches,
    invalidate_ad_caches,
)

from common.utils.cache_managers import (
    UserCacheManager,
    SubscriptionCacheManager,
    AdCacheManager,
    FavoriteCacheManager,
    BaseCacheManager,
)
from common.utils.cache import get_entity_cache_key
from common.utils.logging_config import log_operation, log_context, LogAggregator
from common.constants import DEFAULT_BATCH_SIZE as BATCH_SIZE, FREE_TRIAL_DAYS

# Import the common db logger
from . import logger
from .repositories import VerificationRepository


@log_operation("create_telegram_user")
def create_telegram_user(telegram_id: str) -> Optional[User]:
    """
    Create a new Telegram user.
    Simplified for Telegram-only app.
    """
    with log_context(logger, telegram_id=telegram_id):
        try:
            with db_session() as db:
                # Check if user already exists
                existing_user = (
                    db.query(User).filter(User.telegram_id == telegram_id).first()
                )
                if existing_user:
                    logger.info(
                        "User already exists",
                        extra={"telegram_id": telegram_id, "user_id": existing_user.id},
                    )
                    return existing_user

                # Create new user
                user = User(
                    telegram_id=telegram_id,
                    free_until=datetime.now() + timedelta(days=FREE_TRIAL_DAYS),
                )
                db.add(user)
                db.commit()
                db.refresh(user)

                logger.info(
                    "Created new user",
                    extra={"telegram_id": telegram_id, "user_id": user.id},
                )

                return user

        except Exception as e:
            logger.error(
                "Error creating user",
                exc_info=True,
                extra={"telegram_id": telegram_id, "error_type": type(e).__name__},
            )
            return None


@log_operation("update_user_filter")
def update_user_filter(user_id, filters):
    """
    Update filters for a user with cache invalidation
    """
    with log_context(logger, user_id=user_id):
        logger.info(f"Updating filters for user_id: {user_id}")

        try:
            with db_session() as db:
                # Check if user exists
                user = UserRepository.get_by_id(db, user_id)
                if not user:
                    logger.error(
                        f"Cannot update filters - user_id {user_id} does not exist in database"
                    )
                    raise ValueError(f"User ID {user_id} does not exist")

                # Extract filter data
                property_type = filters.get("property_type")
                city = filters.get("city")
                rooms_count = filters.get("rooms")  # List or None
                price_min = filters.get("price_min")
                price_max = filters.get("price_max")

                # Pass city name; repository will convert to geo_id
                filter_data = {
                    "property_type": property_type,
                    "city": city,
                    "rooms_count": rooms_count,
                    "price_min": price_min,
                    "price_max": price_max,
                }

                # Update or create user filter
                user_filter = SubscriptionRepository.update_user_filter(
                    db, user_id, filter_data
                )

                logger.info(
                    f"Updated filters: [{user_id}, {property_type}, {city}, {rooms_count}, {price_min}, {price_max}]",
                    extra={"user_id": user_id, "filter_data": filter_data},
                )

                # Use centralized cache invalidation
                invalidate_subscription_caches(user_id)

                return user_filter

        except Exception as e:
            logger.error(
                "Error updating user filters",
                exc_info=True,
                extra={"user_id": user_id, "error_type": type(e).__name__},
            )
            raise


@log_operation("invalidate_user_filter_caches")
def invalidate_user_filter_caches(user_id: int):
    """Centralized function to invalidate all related caches when a user filter changes"""
    with log_context(logger, user_id=user_id):
        # Use the cache manager to handle invalidation
        UserCacheManager.invalidate_all(user_id)
        SubscriptionCacheManager.invalidate_all(user_id)
        logger.debug("Invalidated user filter caches")


@log_operation("get_user_filters")
def get_user_filters(user_id):
    """Get user filters with caching"""
    with log_context(logger, user_id=user_id):
        # Try to get from cache first using the cache manager
        filters = UserCacheManager.get_filters(user_id)
        if filters:
            logger.debug("Cache hit for user filters", extra={"user_id": user_id})
            return filters

        # Cache miss, query the database
        with db_session() as db:
            filters = SubscriptionRepository.get_user_filters(db, user_id)

            # Cache the result if found
            if filters:
                UserCacheManager.set_filters(user_id, filters)
                logger.debug("Cached user filters", extra={"user_id": user_id})
            else:
                logger.debug("No filters found for user", extra={"user_id": user_id})

            return filters


@log_operation("batch_get_user_filters")
def batch_get_user_filters(user_ids):
    """
    Get filters for multiple users in a single query to prevent N+1 problems.
    Uses the cache manager approach.
    """
    if not user_ids:
        return {}

    with log_context(logger, user_count=len(user_ids)):
        aggregator = LogAggregator(logger, "batch_get_user_filters")

        # Result dictionary
        results = {}

        # Step 1: Try to get as many filters from cache as possible
        for user_id in user_ids:
            cached_filters = UserCacheManager.get_filters(user_id)
            if cached_filters:
                results[user_id] = cached_filters
                aggregator.add_item(
                    {"user_id": user_id, "from_cache": True}, success=True
                )

        # Step 2: Find which user_ids were not in cache
        missing_user_ids = [uid for uid in user_ids if uid not in results]

        # If all users were found in cache, return immediately
        if not missing_user_ids:
            logger.debug(
                "All user filters found in cache", extra={"user_count": len(user_ids)}
            )
            aggregator.log_summary()
            return results

        # Step 3: Fetch missing data from database in batches
        with db_session() as db:
            for i in range(0, len(missing_user_ids), BATCH_SIZE):
                batch = missing_user_ids[i : i + BATCH_SIZE]

                # Use repository to get filters for this batch
                for user_id in batch:
                    user_filter = SubscriptionRepository.get_user_filters(db, user_id)
                    if user_filter:
                        results[user_id] = user_filter
                        # Cache each result
                        UserCacheManager.set_filters(user_id, user_filter)
                        aggregator.add_item(
                            {"user_id": user_id, "from_db": True}, success=True
                        )
                    else:
                        aggregator.add_item(
                            {"user_id": user_id, "not_found": True}, success=False
                        )

        aggregator.log_summary()
        return results


@log_operation("get_user_by_telegram_id")
def get_user_by_telegram_id(telegram_id: str) -> Optional[User]:
    """
    Get user by Telegram ID.
    Simplified for Telegram-only app.
    """
    with log_context(logger, telegram_id=telegram_id):
        try:
            with db_session() as db:
                user = db.query(User).filter(User.telegram_id == telegram_id).first()

                if user:
                    logger.debug(
                        "Found user",
                        extra={"telegram_id": telegram_id, "user_id": user.id},
                    )
                else:
                    logger.debug("User not found", extra={"telegram_id": telegram_id})

                return user

        except Exception as e:
            logger.error(
                "Error getting user",
                exc_info=True,
                extra={"telegram_id": telegram_id, "error_type": type(e).__name__},
            )
            return None


@log_operation("get_platform_ids_for_user")
def get_platform_ids_for_user(user_id: int) -> dict:
    """
    Get all messaging platform IDs for a user.
    This doesn't need caching as it's called infrequently and the data is small.
    """
    with log_context(logger, user_id=user_id):
        try:
            with db_session() as db:
                user = UserRepository.get_by_id(db, user_id)

                if not user:
                    logger.warning("User not found", extra={"user_id": user_id})
                    return {}

                # Create a cleaned dictionary with only non-None values
                platform_ids = {}
                if user.telegram_id is not None:
                    platform_ids["telegram_id"] = user.telegram_id

                logger.debug(
                    "Retrieved platform IDs",
                    extra={"user_id": user_id, "platforms": list(platform_ids.keys())},
                )
                return platform_ids
        except Exception as e:
            logger.error(
                "Error getting platform IDs",
                exc_info=True,
                extra={"user_id": user_id, "error_type": type(e).__name__},
            )
            return {}


@log_operation("find_users_for_ad")
def find_users_for_ad(ad):
    """
    Finds users whose subscription filters match this ad.
    Uses the cache manager approach.
    """
    try:
        # Extract the ad ID for caching
        ad_id = (
            ad.get("id")
            if isinstance(ad, dict)
            else ad.id if hasattr(ad, "id") else None
        )

        if not ad_id:
            logger.error("Cannot find users for ad without ID")
            return []

        with log_context(logger, ad_id=ad_id):
            # Try to get from cache using BaseCacheManager
            cache_key = get_entity_cache_key("matching_users", ad_id)
            cached_users = BaseCacheManager.get(cache_key)
            if cached_users:
                logger.info(f"Cache hit for ad {ad_id} matching users")
                return cached_users

            logger.info(f"Looking for users for ad: {ad_id}")

            with db_session() as db:
                # Use repository to find matching users
                if isinstance(ad, dict):
                    existing_ad = db.query(Ad).get(ad_id)
                    if not existing_ad:
                        # Create temporary Ad object for matching
                        ad_obj = Ad(
                            id=ad_id,
                            property_type=ad.get("property_type"),
                            city=ad.get("city"),
                            rooms_count=ad.get("rooms_count"),
                            price=ad.get("price"),
                        )
                    else:
                        ad_obj = existing_ad
                else:
                    ad_obj = ad

                # Use repository to find matching users
                user_ids = AdRepository.find_users_for_ad(db, ad_obj)

            # Cache the results
            BaseCacheManager.set(cache_key, user_ids, CacheTTL.STANDARD)

            logger.info(f"Found {len(user_ids)} users for ad: {ad_id}")
            return user_ids

    except Exception as e:
        logger.error(
            "Error finding users for ad",
            exc_info=True,
            extra={
                "ad_id": (
                    ad.get("id")
                    if isinstance(ad, dict)
                    else getattr(ad, "id", "unknown")
                ),
                "error_type": type(e).__name__,
            },
        )
        return []


@log_operation("batch_find_users_for_ads")
def batch_find_users_for_ads(ads):
    """
    Find matching users for multiple ads in an efficient way
    using the cache manager approach.
    """
    if not ads:
        return {}

    with log_context(logger, ad_count=len(ads)):
        aggregator = LogAggregator(logger, "batch_find_users_for_ads")

        results = {}
        ad_ids = [ad.get("id") for ad in ads if ad.get("id")]

        # Step 1: Try to get matches from cache
        for ad_id in ad_ids:
            cache_key = get_entity_cache_key("matching_users", ad_id)
            cached_users = BaseCacheManager.get(cache_key)
            if cached_users:
                results[ad_id] = cached_users
                aggregator.add_item({"ad_id": ad_id, "from_cache": True}, success=True)

        # Step 2: Find which ads were not in cache
        processed_ad_ids = set(results.keys())
        ads_to_process = [ad for ad in ads if ad.get("id") not in processed_ad_ids]

        if not ads_to_process:
            aggregator.log_summary()
            return results

        # Step 3: Process the remaining ads
        with db_session() as db:
            # Get all active users
            active_users = (
                db.query(User.id)
                .filter(
                    or_(
                        User.free_until > datetime.now(),
                        User.subscription_until > datetime.now(),
                    )
                )
                .all()
            )

            active_user_ids = [row[0] for row in active_users]

            if not active_user_ids:
                logger.info("No active users found")
                aggregator.log_summary()
                return results

            # Get all user filters in one query
            batch_get_user_filters(active_user_ids)

            # Process each ad against all user filters in memory
            for ad in ads_to_process:
                ad_id = ad.get("id")
                if not ad_id:
                    continue

                # Convert dict to Ad object if needed
                if isinstance(ad, dict):
                    existing_ad = db.query(Ad).get(ad_id)
                    if not existing_ad:
                        # Create temporary Ad object for matching
                        ad_obj = Ad(
                            id=ad_id,
                            property_type=ad.get("property_type"),
                            city=ad.get("city"),
                            rooms_count=ad.get("rooms_count"),
                            price=ad.get("price"),
                        )
                    else:
                        ad_obj = existing_ad
                else:
                    ad_obj = ad

                # Use repository to find matching users
                matching_users = AdRepository.find_users_for_ad(db, ad_obj)

                # Store results and cache them
                results[ad_id] = matching_users
                cache_key = get_entity_cache_key("matching_users", ad_id)
                BaseCacheManager.set(cache_key, matching_users, CacheTTL.STANDARD)

                aggregator.add_item(
                    {"ad_id": ad_id, "matching_users": len(matching_users)},
                    success=True,
                )

        aggregator.log_summary()
        return results


@log_operation("get_subscription_data_for_user")
def get_subscription_data_for_user(user_id: int) -> dict:
    """
    Get subscription data for a user with caching
    """
    with log_context(logger, user_id=user_id):
        # Try to get from the cache using the cache manager
        cached_data = SubscriptionCacheManager.get_user_subscriptions(user_id)
        if cached_data:
            logger.debug("Cache hit for subscription data", extra={"user_id": user_id})
            return cached_data

        try:
            with db_session() as db:
                user_filter = SubscriptionRepository.get_user_filters(db, user_id)

                if user_filter:
                    # Cache for 5 minutes using the cache manager
                    SubscriptionCacheManager.set_user_subscriptions(
                        user_id, user_filter
                    )
                    logger.debug("Cached subscription data", extra={"user_id": user_id})
                    return user_filter
                else:
                    logger.debug(
                        "No subscription data found", extra={"user_id": user_id}
                    )
                    return None
        except Exception as e:
            logger.error(
                "Error getting subscription data",
                exc_info=True,
                extra={"user_id": user_id, "error_type": type(e).__name__},
            )
            return None


@log_operation("get_full_ad_data")
def get_full_ad_data(ad_id: int):
    """Get complete ad data with related entities and caching"""
    with log_context(logger, ad_id=ad_id):
        # Try to get from cache using the cache manager
        cached_data = AdCacheManager.get_full_ad_data(ad_id)
        if cached_data:
            logger.debug("Cache hit for full ad data", extra={"ad_id": ad_id})
            return cached_data

        try:
            with db_session() as db:
                ad_data = AdRepository.get_full_ad_data(db, ad_id)

                if ad_data:
                    # Cache the result using the cache manager
                    AdCacheManager.set_full_ad_data(ad_id, ad_data)
                    logger.debug("Cached full ad data", extra={"ad_id": ad_id})
                else:
                    logger.debug("No ad data found", extra={"ad_id": ad_id})

                return ad_data
        except Exception as e:
            logger.error(
                "Error getting full ad data",
                exc_info=True,
                extra={"ad_id": ad_id, "error_type": type(e).__name__},
            )
            return None


@log_operation("batch_get_full_ad_data")
def batch_get_full_ad_data(ad_ids):
    """
    Get complete data for multiple ads in a single query using AdCacheManager

    Args:
        ad_ids: List of ad IDs

    Returns:
        Dict mapping ad_id to ad data
    """
    if not ad_ids:
        return {}

    with log_context(logger, ad_count=len(ad_ids)):
        aggregator = LogAggregator(logger, "batch_get_full_ad_data")

        results = {}

        # Try to get from cache first
        for ad_id in ad_ids:
            cached_data = AdCacheManager.get_full_ad_data(ad_id)
            if cached_data:
                results[ad_id] = cached_data
                aggregator.add_item({"ad_id": ad_id, "from_cache": True}, success=True)

        # Identify which ads were not in cache
        missing_ad_ids = [ad_id for ad_id in ad_ids if ad_id not in results]

        if not missing_ad_ids:
            aggregator.log_summary()
            return results

        # Process batches of missing ads
        with db_session() as db:
            for i in range(0, len(missing_ad_ids), BATCH_SIZE):
                batch = missing_ad_ids[i : i + BATCH_SIZE]

                for ad_id in batch:
                    ad_data = AdRepository.get_full_ad_data(db, ad_id)
                    if ad_data:
                        results[ad_id] = ad_data
                        # Cache individual results
                        AdCacheManager.set_full_ad_data(ad_id, ad_data)
                        aggregator.add_item(
                            {"ad_id": ad_id, "from_db": True}, success=True
                        )
                    else:
                        aggregator.add_item(
                            {"ad_id": ad_id, "not_found": True}, success=False
                        )

        aggregator.log_summary()
        return results


@log_operation("list_favorites_with_eager_loading")
def list_favorites_with_eager_loading(user_id: int):
    """
    List user's favorite ads with eager loading of related data
    This prevents N+1 query problems by loading all related data in a single query
    """
    with log_context(logger, user_id=user_id):
        try:
            with db_session() as db:
                favorites = FavoriteRepository.list_favorites(db, user_id)
                logger.info(
                    "Listed favorites with eager loading",
                    extra={"user_id": user_id, "favorites_count": len(favorites)},
                )
                return favorites
        except Exception as e:
            logger.error(
                "Error listing favorites with eager loading",
                exc_info=True,
                extra={"user_id": user_id, "error_type": type(e).__name__},
            )
            return []


@log_operation("add_subscription")
def add_subscription(
    user_id, property_type, city_id, rooms_count, price_min, price_max
):
    """Add a subscription with proper cache invalidation"""
    with log_context(
        logger, user_id=user_id, property_type=property_type, city_id=city_id
    ):
        with db_session() as db:
            # Check subscription count
            count = SubscriptionRepository.count_subscriptions(db, user_id)
            if count >= 20:
                logger.warning(
                    "Subscription limit reached",
                    extra={"user_id": user_id, "current_count": count},
                )
                raise ValueError("You already have 20 subscriptions, cannot add more.")

            # Create filter data
            filter_data = {
                "property_type": property_type,
                "city": city_id,
                "rooms_count": rooms_count,
                "price_min": price_min,
                "price_max": price_max,
            }

            # Add subscription
            subscription = SubscriptionRepository.add_subscription(
                db, user_id, filter_data
            )

            # Invalidate cache using the cache manager
            SubscriptionCacheManager.invalidate_all(user_id)

            logger.info(
                "Added subscription",
                extra={
                    "user_id": user_id,
                    "subscription_id": subscription.id,
                    "filter_data": filter_data,
                },
            )
            return subscription.id


@log_operation("list_subscriptions")
def list_subscriptions(user_id: int):
    """List user subscriptions with caching using cache managers"""
    with log_context(logger, user_id=user_id):
        # Use the cache manager to get cached subscriptions
        cached_subscriptions = SubscriptionCacheManager.get_user_subscriptions(user_id)
        if cached_subscriptions:
            logger.debug("Cache hit for user subscriptions", extra={"user_id": user_id})
            return cached_subscriptions

        try:
            with db_session() as db:
                subscriptions = SubscriptionRepository.list_subscriptions(db, user_id)

                # Cache the result using the cache manager
                SubscriptionCacheManager.set_user_subscriptions(user_id, subscriptions)

                logger.info(
                    "Listed subscriptions",
                    extra={
                        "user_id": user_id,
                        "subscription_count": len(subscriptions),
                    },
                )
                return subscriptions
        except Exception as e:
            logger.error(
                "Error listing subscriptions",
                exc_info=True,
                extra={"user_id": user_id, "error_type": type(e).__name__},
            )
            return []


@log_operation("remove_subscription")
def remove_subscription(subscription_id: int, user_id: int) -> bool:
    """
    Remove a subscription with cache invalidation
    """
    with log_context(logger, subscription_id=subscription_id, user_id=user_id):
        try:
            with db_session() as db:
                success = SubscriptionRepository.remove_subscription(
                    db, subscription_id, user_id
                )

                # Invalidate relevant cache entries
                invalidate_user_filter_caches(user_id)

                logger.info(
                    "Removed subscription",
                    extra={
                        "subscription_id": subscription_id,
                        "user_id": user_id,
                        "success": success,
                    },
                )
                return success
        except Exception as e:
            logger.error(
                "Error removing subscription",
                exc_info=True,
                extra={
                    "subscription_id": subscription_id,
                    "user_id": user_id,
                    "error_type": type(e).__name__,
                },
            )
            return False


@log_operation("update_subscription")
def update_subscription(subscription_id: int, user_id: int, new_values: dict):
    """
    Update a subscription with cache invalidation using cache managers
    """
    with log_context(logger, subscription_id=subscription_id, user_id=user_id):
        try:
            with db_session() as db:
                # Get the subscription
                subscription = (
                    db.query(UserFilter)
                    .filter(
                        UserFilter.id == subscription_id, UserFilter.user_id == user_id
                    )
                    .first()
                )

                if not subscription:
                    logger.warning(
                        "Subscription not found",
                        extra={"subscription_id": subscription_id, "user_id": user_id},
                    )
                    return False

                # Update values
                for key, value in new_values.items():
                    setattr(subscription, key, value)

                db.commit()

                # Invalidate cache using the cache manager
                SubscriptionCacheManager.invalidate_all(user_id, subscription_id)

                logger.info(
                    "Updated subscription",
                    extra={
                        "subscription_id": subscription_id,
                        "user_id": user_id,
                        "updates": new_values,
                    },
                )
                return True
        except Exception as e:
            logger.error(
                "Error updating subscription",
                exc_info=True,
                extra={
                    "subscription_id": subscription_id,
                    "user_id": user_id,
                    "error_type": type(e).__name__,
                },
            )
            return False


@log_operation("add_favorite_ad")
def add_favorite_ad(user_id: int, ad_id: int) -> Optional[int]:
    """
    Add a favorite ad with cache invalidation

    Returns:
        Favorite ID or None if failed
    """
    with log_context(logger, user_id=user_id, ad_id=ad_id):
        try:
            with db_session() as db:
                # Use repository to add favorite
                favorite = FavoriteRepository.add_favorite(db, user_id, ad_id)

                # Use centralized cache invalidation
                invalidate_favorite_caches(user_id)

                favorite_id = favorite.id if favorite else None
                logger.info(
                    "Added favorite ad",
                    extra={
                        "user_id": user_id,
                        "ad_id": ad_id,
                        "favorite_id": favorite_id,
                    },
                )
                return favorite_id
        except ValueError as e:
            # This handles the case where user already has 50 favorites
            logger.warning(
                f"Couldn't add favorite: {str(e)}",
                extra={"user_id": user_id, "ad_id": ad_id},
            )
            raise
        except Exception as e:
            logger.error(
                "Error adding favorite ad",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "ad_id": ad_id,
                    "error_type": type(e).__name__,
                },
            )
            return None


@log_operation("list_favorites")
def list_favorites(user_id):
    """List user's favorite ads with caching"""
    with log_context(logger, user_id=user_id):
        # Try to get from cache using the cache manager
        cached_favorites = FavoriteCacheManager.get_user_favorites(user_id)
        if cached_favorites:
            logger.debug("Cache hit for user favorites", extra={"user_id": user_id})
            return cached_favorites

        try:
            with db_session() as db:
                favorites = FavoriteRepository.list_favorites(db, user_id)

                # Cache for 5 minutes using the cache manager
                FavoriteCacheManager.set_user_favorites(user_id, favorites)

                logger.info(
                    "Listed favorites",
                    extra={"user_id": user_id, "favorites_count": len(favorites)},
                )
                return favorites
        except Exception as e:
            logger.error(
                "Error listing favorites",
                exc_info=True,
                extra={"user_id": user_id, "error_type": type(e).__name__},
            )
            return []


@log_operation("remove_favorite_ad")
def remove_favorite_ad(user_id: int, ad_id: int) -> bool:
    """Remove a favorite ad with cache invalidation"""
    with log_context(logger, user_id=user_id, ad_id=ad_id):
        try:
            with db_session() as db:
                # Use repository to remove favorite
                success = FavoriteRepository.remove_favorite(db, user_id, ad_id)

                # Use centralized cache invalidation
                invalidate_favorite_caches(user_id)

                logger.info(
                    "Removed favorite ad",
                    extra={"user_id": user_id, "ad_id": ad_id, "success": success},
                )
                return success
        except Exception as e:
            logger.error(
                "Error removing favorite ad",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "ad_id": ad_id,
                    "error_type": type(e).__name__,
                },
            )
            return False


@log_operation("get_extra_images")
def get_extra_images(resource_url):
    """Get extra images for an ad with caching using cache managers"""
    with log_context(logger, resource_url=resource_url[:50]):
        # Create a cache key
        cache_key = get_entity_cache_key("extra_images", resource_url)

        # Try to get from cache
        cached_images = BaseCacheManager.get(cache_key)
        if cached_images:
            logger.debug(
                "Cache hit for extra images", extra={"resource_url": resource_url[:50]}
            )
            return cached_images

        try:
            with db_session() as db:
                # First, look up the ad using resource_url
                ad = AdRepository.get_by_resource_url(db, resource_url)
                if not ad:
                    logger.warning(
                        "Ad not found by resource URL",
                        extra={"resource_url": resource_url[:50]},
                    )
                    return []

                # Get images for the ad
                images = AdRepository.get_ad_images(db, ad.id)

                # Cache the result
                BaseCacheManager.set(cache_key, images, CacheTTL.LONG)

                logger.info(
                    "Retrieved and cached extra images",
                    extra={
                        "resource_url": resource_url[:50],
                        "image_count": len(images),
                    },
                )
                return images
        except Exception as e:
            logger.error(
                "Error getting extra images",
                exc_info=True,
                extra={
                    "resource_url": resource_url[:50],
                    "error_type": type(e).__name__,
                },
            )
            return []


@log_operation("get_full_ad_description")
def get_full_ad_description(resource_url):
    """Get full ad description with caching"""
    with log_context(logger, resource_url=resource_url[:50]):
        # Try to get from cache using the cache manager
        cached_description = AdCacheManager.get_ad_description(resource_url)
        if cached_description:
            logger.debug(
                "Cache hit for ad description",
                extra={"resource_url": resource_url[:50]},
            )
            return cached_description

        logger.info(f"Getting full ad description for resource_url: {resource_url}...")

        try:
            with db_session() as db:
                description = AdRepository.get_description_by_resource_url(
                    db, resource_url
                )

            if description:
                # Cache for 1 hour using the cache manager
                AdCacheManager.set_ad_description(resource_url, description)
                logger.info(
                    "Retrieved and cached ad description",
                    extra={
                        "resource_url": resource_url[:50],
                        "description_length": len(description),
                    },
                )
            else:
                logger.warning(
                    "No description found", extra={"resource_url": resource_url[:50]}
                )

            return description
        except Exception as e:
            logger.error(
                "Error getting full ad description",
                exc_info=True,
                extra={
                    "resource_url": resource_url[:50],
                    "error_type": type(e).__name__,
                },
            )
            return None


@log_operation("store_ad_phones")
def store_ad_phones(resource_url: str, ad_id: int) -> int:
    """
    Extracts phone numbers and stores them with cache invalidation
    """
    with log_context(logger, resource_url=resource_url[:50], ad_id=ad_id):
        try:
            with db_session() as db:
                # First check if the ad exists in the database
                ad = AdRepository.get_by_id(db, ad_id)

                if not ad:
                    logger.warning(
                        f"Cannot store phones for ad_id={ad_id} - ad doesn't exist in the database"
                    )
                    return 0

                # Extract phones from resource
                result = extract_phone_numbers_from_resource(resource_url)
                phones = result.phone_numbers
                viber_link = result.viber_link

                # Delete existing phones for this ad to avoid duplicates
                phones_count = db.query(AdPhone).filter(AdPhone.ad_id == ad_id).delete()
                logger.info(f"Deleted {phones_count} existing phones for ad_id={ad_id}")

                phones_added = 0

                # Insert new phones
                for phone in phones:
                    AdRepository.add_phone(db, ad_id, phone)
                    phones_added += 1

                # Insert viber link if available
                if viber_link:
                    AdRepository.add_phone(db, ad_id, None, viber_link)
                    logger.info("Added viber link", extra={"ad_id": ad_id})

                # Commit changes
                db.commit()

                # Use centralized cache invalidation
                invalidate_ad_caches(ad_id, resource_url)

                logger.info(
                    "Stored phone numbers",
                    extra={
                        "ad_id": ad_id,
                        "phones_added": phones_added,
                        "has_viber_link": bool(viber_link),
                    },
                )
                return phones_added
        except Exception as e:
            logger.error(
                "Error extracting or storing phones",
                exc_info=True,
                extra={
                    "ad_id": ad_id,
                    "resource_url": resource_url[:50],
                    "error_type": type(e).__name__,
                },
            )
            return 0


@log_operation("warm_cache_for_user")
def warm_cache_for_user(user_id):
    """
    Warm up cache for a user's most commonly accessed data
    Call this when user logs in or starts interacting with the system
    """
    from common.utils.cache_invalidation import warm_cache_for_user as warm_cache

    with log_context(logger, user_id=user_id):
        logger.info("Starting cache warming for user", extra={"user_id": user_id})
        result = warm_cache(user_id)
        logger.info("Completed cache warming for user", extra={"user_id": user_id})
        return result


@log_operation("start_free_subscription_of_user")
def start_free_subscription_of_user(user_id: int) -> bool:
    """
    Start or extend a user's free subscription period for 7 days.

    Args:
        user_id: Database user ID

    Returns:
        True if successful, False otherwise
    """
    with log_context(logger, user_id=user_id):
        try:
            with db_session() as db:
                result = UserRepository.start_free_subscription(db, user_id)

            # Use centralized cache invalidation
            invalidate_user_caches(user_id)

            logger.info(
                "Started free subscription",
                extra={"user_id": user_id, "success": result},
            )
            return result
        except Exception as e:
            logger.error(
                "Error starting free subscription",
                exc_info=True,
                extra={"user_id": user_id, "error_type": type(e).__name__},
            )
            return False


@log_operation("get_subscription_until_for_user")
def get_subscription_until_for_user(user_id: int, free: bool = False) -> Optional[str]:
    """
    Get the subscription expiration date for a user using cache managers.

    Args:
        user_id: Database user ID
        free: If True, returns free_until date, otherwise returns subscription_until date

    Returns:
        Subscription expiration date as string or None if not found
    """
    with log_context(logger, user_id=user_id, free=free):
        # Create a cache key
        cache_key = get_entity_cache_key(
            "user_subscription", user_id, "free" if free else "paid"
        )

        # Try to get from cache
        cached_date = BaseCacheManager.get(cache_key)
        if cached_date:
            logger.debug(
                "Cache hit for subscription date",
                extra={"user_id": user_id, "free": free},
            )
            return cached_date

        try:
            with db_session() as db:
                user = UserRepository.get_by_id(db, user_id)

                if not user:
                    logger.warning("User not found", extra={"user_id": user_id})
                    return None

                # Get the appropriate date field
                if free:
                    date_value = user.free_until
                else:
                    date_value = user.subscription_until

                if date_value:
                    if isinstance(date_value, datetime):
                        formatted_date = date_value.strftime("%d.%m.%Y")
                    else:
                        formatted_date = str(date_value)

                    # Cache the result
                    BaseCacheManager.set(cache_key, formatted_date, CacheTTL.MEDIUM)
                    logger.debug(
                        "Cached subscription date",
                        extra={
                            "user_id": user_id,
                            "free": free,
                            "date": formatted_date,
                        },
                    )
                    return formatted_date

            logger.debug(
                "No subscription date found", extra={"user_id": user_id, "free": free}
            )
            return None
        except Exception as e:
            logger.error(
                "Error getting subscription date",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "free": free,
                    "error_type": type(e).__name__,
                },
            )
            return None


@log_operation("get_ad_images")
def get_ad_images(ad_id: Union[int, Dict[str, Any]]) -> List[str]:
    """
    Get all images associated with an ad with caching.
    """
    try:
        # Handle either an ad dict or direct ad_id
        if isinstance(ad_id, dict):
            ad_id = ad_id.get("id")

        if not ad_id:
            logger.warning("No ad_id provided for get_ad_images")
            return []

        with log_context(logger, ad_id=ad_id):
            # Try to get from cache using the cache manager
            cached_images = AdCacheManager.get_ad_images(ad_id)
            if cached_images:
                logger.debug("Cache hit for ad images", extra={"ad_id": ad_id})
                return cached_images

            # Cache miss, query database for images
            with db_session() as db:
                image_urls = AdRepository.get_ad_images(db, ad_id)

                # Cache the result using the cache manager
                if image_urls:
                    AdCacheManager.set_ad_images(ad_id, image_urls)
                    logger.debug(
                        "Cached ad images",
                        extra={"ad_id": ad_id, "image_count": len(image_urls)},
                    )
                else:
                    logger.debug("No images found for ad", extra={"ad_id": ad_id})

                return image_urls

    except Exception as e:
        logger.error(
            "Error getting ad images",
            exc_info=True,
            extra={
                "ad_id": ad_id if "ad_id" in locals() else None,
                "error_type": type(e).__name__,
            },
        )
        return []


@log_operation("disable_subscription_for_user")
def disable_subscription_for_user(user_id: int) -> bool:
    """
    Disable subscription for a user by setting is_paused to True in user_filters table

    Args:
        user_id: User's database ID

    Returns:
        True if successful, False otherwise
    """
    with log_context(logger, user_id=user_id):
        try:
            with db_session() as db:
                success = SubscriptionRepository.disable_subscription(db, user_id)

                # Use centralized cache invalidation
                invalidate_subscription_caches(user_id)

                logger.info(
                    "Disabled subscription",
                    extra={"user_id": user_id, "success": success},
                )
                return success
        except Exception as e:
            logger.error(
                "Error disabling subscription",
                exc_info=True,
                extra={"user_id": user_id, "error_type": type(e).__name__},
            )
            return False


@log_operation("enable_subscription_for_user")
def enable_subscription_for_user(user_id: int) -> bool:
    """
    Enable subscription for a user by setting is_paused to False in user_filters table

    Args:
        user_id: User's database ID

    Returns:
        True if successful, False otherwise
    """
    with log_context(logger, user_id=user_id):
        try:
            with db_session() as db:
                success = SubscriptionRepository.enable_subscription(db, user_id)

                # Use centralized cache invalidation
                invalidate_subscription_caches(user_id)

                logger.info(
                    "Enabled subscription",
                    extra={"user_id": user_id, "success": success},
                )
                return success
        except Exception as e:
            logger.error(
                "Error enabling subscription",
                exc_info=True,
                extra={"user_id": user_id, "error_type": type(e).__name__},
            )
            return False


@log_operation("count_subscriptions")
def count_subscriptions(user_id: int) -> int:
    """
    Count the number of subscriptions (filters) for a user

    Args:
        user_id: User's database ID

    Returns:
        Number of subscriptions
    """
    with log_context(logger, user_id=user_id):
        try:
            with db_session() as db:
                count = SubscriptionRepository.count_subscriptions(db, user_id)
                logger.debug(
                    "Counted subscriptions", extra={"user_id": user_id, "count": count}
                )
                return count
        except Exception as e:
            logger.error(
                "Error counting subscriptions",
                exc_info=True,
                extra={"user_id": user_id, "error_type": type(e).__name__},
            )
            return 0


@log_operation("list_subscriptions_paginated")
def list_subscriptions_paginated(
    user_id: int, page: int = 0, per_page: int = 5
) -> list:
    """
    Get a paginated list of subscriptions for a user

    Args:
        user_id: User's database ID
        page: Page number (0-based)
        per_page: Number of items per page

    Returns:
        List of subscription dictionaries
    """
    with log_context(logger, user_id=user_id, page=page, per_page=per_page):
        try:
            with db_session() as db:
                subscriptions = SubscriptionRepository.list_subscriptions_paginated(
                    db, user_id, page, per_page
                )
                logger.debug(
                    "Listed paginated subscriptions",
                    extra={
                        "user_id": user_id,
                        "page": page,
                        "per_page": per_page,
                        "count": len(subscriptions),
                    },
                )
                return subscriptions
        except Exception as e:
            logger.error(
                "Error listing paginated subscriptions",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "page": page,
                    "per_page": per_page,
                    "error_type": type(e).__name__,
                },
            )
            return []


@log_operation("get_subscription_status")
def get_subscription_status(user_id: int) -> dict:
    """
    Get subscription status data for a user with caching
    """
    with log_context(logger, user_id=user_id):
        # Try to get from cache using the cache manager
        cached_status = UserCacheManager.get_subscription_status(user_id)
        if cached_status:
            logger.debug(
                "Cache hit for subscription status", extra={"user_id": user_id}
            )
            return cached_status

        try:
            with db_session() as db:
                user = UserRepository.get_by_id(db, user_id)

                if not user:
                    logger.warning(
                        "User not found for subscription status",
                        extra={"user_id": user_id},
                    )
                    return {"active": False}

                now = datetime.now()
                free_until = user.free_until
                subscription_until = user.subscription_until

                # Calculate if subscription is active
                free_active = free_until and free_until > now
                paid_active = subscription_until and subscription_until > now

                status = {
                    "active": free_active or paid_active,
                    "free_active": free_active,
                    "paid_active": paid_active,
                    "free_until": free_until.isoformat() if free_until else None,
                    "subscription_until": (
                        subscription_until.isoformat() if subscription_until else None
                    ),
                }

                # Cache the result using the cache manager
                UserCacheManager.set_subscription_status(user_id, status)

                logger.info(
                    "Retrieved subscription status",
                    extra={
                        "user_id": user_id,
                        "active": status["active"],
                        "free_active": status["free_active"],
                        "paid_active": status["paid_active"],
                    },
                )
                return status
        except Exception as e:
            logger.error(
                "Error getting subscription status",
                exc_info=True,
                extra={"user_id": user_id, "error_type": type(e).__name__},
            )
            return {"active": False, "error": str(e)}


@log_operation("get_users_for_reminders")
def get_users_for_reminders() -> List[Dict[str, Any]]:
    """Get users who need subscription reminders"""
    with log_context(logger, operation="get_users_for_reminders"):
        aggregator = LogAggregator(logger, "get_users_for_reminders")

        try:
            # Try to get from cache first
            cache_key = get_entity_cache_key(
                "users_for_reminders", date.today().isoformat()
            )
            cached_users = BaseCacheManager.get(cache_key)

            if cached_users:
                logger.info("Retrieved users for reminders from cache")
                return cached_users

            with db_session() as db:
                # Get users whose subscriptions expire in 3, 7, or 14 days
                target_dates = [
                    datetime.now().date() + timedelta(days=3),
                    datetime.now().date() + timedelta(days=7),
                    datetime.now().date() + timedelta(days=14),
                ]

                users = (
                    db.query(User)
                    .filter(
                        User.telegram_id.isnot(None),
                        User.subscription_until.isnot(None),
                        db.func.date(User.subscription_until).in_(target_dates),
                    )
                    .all()
                )

                # Convert to list of dicts for compatibility
                result = []
                for user in users:
                    user_dict = {
                        "id": user.id,
                        "telegram_id": user.telegram_id,
                        "subscription_until": user.subscription_until,
                        "days_left": (
                            user.subscription_until.date() - datetime.now().date()
                        ).days,
                    }
                    result.append(user_dict)
                    aggregator.add_item(
                        {"user_id": user.id, "days_left": user_dict["days_left"]},
                        success=True,
                    )

                # Cache the results for 1 hour
                BaseCacheManager.set(cache_key, result, CacheTTL.SHORT)

                aggregator.log_summary()
                logger.info(f"Found {len(result)} users for reminders")
                return result

        except Exception as e:
            logger.error("Error getting users for reminders", exc_info=True)
            aggregator.add_error(str(e), {"error_type": type(e).__name__})
            return []


@log_operation("get_expiring_subscriptions")
def get_expiring_subscriptions() -> List[Dict[str, Any]]:
    """Get subscriptions that are expiring soon"""
    with log_context(logger, operation="get_expiring_subscriptions"):
        aggregator = LogAggregator(logger, "get_expiring_subscriptions")

        try:
            # Try to get from cache first
            cache_key = get_entity_cache_key(
                "expiring_subscriptions", date.today().isoformat()
            )
            cached_subscriptions = BaseCacheManager.get(cache_key)

            if cached_subscriptions:
                logger.info("Retrieved expiring subscriptions from cache")
                return cached_subscriptions

            with db_session() as db:
                # Get subscriptions expiring in the next 7 days
                today = datetime.now().date()
                seven_days_later = today + timedelta(days=7)

                users = (
                    db.query(User)
                    .filter(
                        User.telegram_id.isnot(None),
                        User.subscription_until.isnot(None),
                        User.subscription_until > datetime.now(),
                        User.subscription_until
                        <= datetime.combine(seven_days_later, datetime.min.time()),
                    )
                    .order_by(User.subscription_until)
                    .all()
                )

                # Convert to list of dicts with calculated days left
                result = []
                for user in users:
                    days_left = (user.subscription_until.date() - today).days
                    subscription_dict = {
                        "user_id": user.id,
                        "telegram_id": user.telegram_id,
                        "subscription_until": user.subscription_until,
                        "days_left": days_left,
                    }
                    result.append(subscription_dict)
                    aggregator.add_item(
                        {
                            "user_id": user.id,
                            "days_left": days_left,
                            "telegram_id": user.telegram_id,
                        },
                        success=True,
                    )

                # Cache the results for 1 hour
                BaseCacheManager.set(cache_key, result, CacheTTL.SHORT)

                aggregator.log_summary()
                logger.info(f"Found {len(result)} expiring subscriptions")
                return result

        except Exception as e:
            logger.error("Error getting expiring subscriptions", exc_info=True)
            aggregator.add_error(str(e), {"error_type": type(e).__name__})
            return []


@log_operation("send_email_verification_token")
def send_email_verification_token(email: str, user_id: Optional[int] = None) -> str:
    """
    Create and send email verification token.
    Updated to use a unified Verification model.
    """
    with log_context(logger, email=email[:5] + "...", user_id=user_id):
        try:
            with db_session() as db:
                token = VerificationRepository.create_verification(
                    db=db,
                    verification_type="email",
                    target=email.lower().strip(),
                    user_id=user_id,
                    expiry_minutes=60,  # Email tokens valid for 1 hour
                )

                logger.info(
                    "Email verification token created",
                    extra={"email": email[:5] + "...", "user_id": user_id},
                )

                # Send email with token
                from common.verification.email_service import send_verification_email

                send_verification_email(email, token)

                return token

        except Exception as e:
            logger.error(
                "Error creating email verification",
                exc_info=True,
                extra={"email": email[:5] + "...", "error_type": type(e).__name__},
            )
            raise


@log_operation("verify_email_token")
def verify_email_token(email: str, token: str) -> Tuple[bool, str]:
    """
    Verify email verification token.
    Updated to use a unified Verification model.
    """
    with log_context(logger, email=email[:5] + "..."):
        try:
            with db_session() as db:
                is_valid = VerificationRepository.verify_code(
                    db=db,
                    verification_type="email",
                    target=email.lower().strip(),
                    code=token,
                )

                if is_valid:
                    logger.info(
                        "Email verification successful",
                        extra={"email": email[:5] + "..."},
                    )
                    return True, ""
                else:
                    logger.warning(
                        "Email verification failed", extra={"email": email[:5] + "..."}
                    )
                    return False, "Недійсний токен або термін дії закінчився"

        except Exception as e:
            logger.error(
                "Error verifying email token",
                exc_info=True,
                extra={"email": email[:5] + "...", "error_type": type(e).__name__},
            )
            return False, "Помилка при перевірці токену"
