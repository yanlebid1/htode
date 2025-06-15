# common/utils/cache_invalidation.py

from typing import Optional, List, Union

# Import only BaseCacheManager to avoid circular imports
from common.utils.cache_managers import BaseCacheManager
from common.utils.cache import get_entity_cache_key
from common.utils.logging_config import log_operation, log_context, LogAggregator

# Import the logger from the parent module
from . import logger


@log_operation("invalidate_ad_caches")
def invalidate_ad_caches(ad_id: int, resource_url: Optional[str] = None) -> int:
    """
    Invalidate all caches related to an ad.

    Args:
        ad_id: Database ad ID
        resource_url: Optional resource URL of the ad

    Returns:
        Number of invalidated cache keys
    """
    with log_context(logger, ad_id=ad_id, resource_url=resource_url):
        # Collect keys to delete
        keys_to_delete = [
            get_entity_cache_key("full_ad", ad_id),
            get_entity_cache_key("ad_images", ad_id),
            get_entity_cache_key("matching_users", ad_id)
        ]

        # Add resource URL-related keys
        if resource_url:
            keys_to_delete.extend([
                get_entity_cache_key("extra_images", resource_url),
                get_entity_cache_key("ad_description", resource_url)
            ])

        # Delete all collected keys
        deleted_count = BaseCacheManager.delete_keys(keys_to_delete)

        # Also delete any pattern-based keys that might be related
        pattern_keys = [
            f"ad:{ad_id}:*",
            f"matching_users:*"  # This might be broader than needed
        ]

        aggregator = LogAggregator(logger, f"invalidate_ad_patterns_{ad_id}")

        for pattern in pattern_keys:
            count = BaseCacheManager.delete_pattern(pattern)
            deleted_count += count
            aggregator.add_item({'pattern': pattern, 'count': count}, success=True)

        aggregator.log_summary()

        logger.debug("Invalidated cache keys for ad", extra={
            'ad_id': ad_id,
            'total_deleted': deleted_count
        })

        return deleted_count


@log_operation("invalidate_phone_caches")
def invalidate_phone_caches(ad_id: int) -> int:
    """
    Invalidate phone-related caches for an ad.

    Args:
        ad_id: Database ad ID

    Returns:
        Number of invalidated cache keys
    """
    with log_context(logger, ad_id=ad_id):
        # Invalidate full ad cache since it contains phone information
        return invalidate_ad_caches(ad_id)


@log_operation("warm_cache_for_user")
def warm_cache_for_user(user_id: int) -> None:
    """
    Warm up commonly accessed caches for a user to improve performance.
    This should be called when a user logs in or starts a new session.

    Args:
        user_id: Database user ID
    """
    from common.db.operations import (
        get_user_filters,
        list_favorites,
        get_subscription_data_for_user,
        batch_get_full_ad_data
    )
    from common.utils.cache_managers import UserCacheManager, FavoriteCacheManager, SubscriptionCacheManager, \
        AdCacheManager

    with log_context(logger, user_id=user_id):
        logger.info("Warming cache for user", extra={'user_id': user_id})

        aggregator = LogAggregator(logger, f"warm_cache_{user_id}")

        try:
            # Prefetch user filters
            filters = get_user_filters(user_id)

            # Store in cache using manager
            if filters:
                UserCacheManager.set_filters(user_id, filters)
                aggregator.add_item({'type': 'filters', 'cached': True}, success=True)
            else:
                aggregator.add_item({'type': 'filters', 'cached': False}, success=False)

            # Prefetch user's favorites
            favorites = list_favorites(user_id)

            # Store in cache using manager
            if favorites:
                FavoriteCacheManager.set_user_favorites(user_id, favorites)
                aggregator.add_item({'type': 'favorites', 'count': len(favorites)}, success=True)
            else:
                aggregator.add_item({'type': 'favorites', 'count': 0}, success=False)

            # Prefetch subscription data
            subscription_data = get_subscription_data_for_user(user_id)

            # Store in cache using manager
            if subscription_data:
                SubscriptionCacheManager.set_user_subscriptions(user_id, [subscription_data])
                aggregator.add_item({'type': 'subscription', 'cached': True}, success=True)
            else:
                aggregator.add_item({'type': 'subscription', 'cached': False}, success=False)

            # If we have favorites, prefetch full data for those ads
            if favorites:
                ad_ids = [fav.get('ad_id') for fav in favorites if fav.get('ad_id')]
                ad_data_dict = batch_get_full_ad_data(ad_ids)

                # Store each ad in cache using manager
                ads_cached = 0
                for ad_id, ad_data in ad_data_dict.items():
                    if ad_data:
                        AdCacheManager.set_full_ad_data(ad_id, ad_data)
                        ads_cached += 1

                aggregator.add_item({'type': 'ad_data', 'count': ads_cached}, success=True)

            aggregator.log_summary()
            logger.info("Cache warmed for user", extra={'user_id': user_id})

        except Exception as e:
            logger.error("Error warming cache for user", exc_info=True, extra={
                'user_id': user_id,
                'error_type': type(e).__name__
            })


@log_operation("invalidate_user_caches")
def invalidate_user_caches(user_id: int) -> int:
    """
    Invalidate all caches related to a user.

    Args:
        user_id: Database user ID

    Returns:
        Number of invalidated cache keys
    """
    patterns = [
        f"user:{user_id}*",
        f"user_filters:{user_id}*",
        f"subscription_status:{user_id}*",
        f"user_favorites:{user_id}*",
        f"user_subscriptions_list:{user_id}*"
    ]

    with log_context(logger, user_id=user_id):
        deleted_count = 0
        aggregator = LogAggregator(logger, f"invalidate_user_caches_{user_id}")

        for pattern in patterns:
            count = BaseCacheManager.delete_pattern(pattern)
            deleted_count += count
            aggregator.add_item({'pattern': pattern, 'count': count}, success=True)

        aggregator.log_summary()

        logger.debug("Invalidated cache keys for user", extra={
            'user_id': user_id,
            'total_deleted': deleted_count
        })

        return deleted_count


@log_operation("invalidate_subscription_caches")
def invalidate_subscription_caches(user_id: int, subscription_id: Optional[int] = None) -> int:
    """
    Invalidate all subscription-related caches for a user.

    Args:
        user_id: Database user ID
        subscription_id: Optional specific subscription ID

    Returns:
        Number of invalidated cache keys
    """
    patterns = [
        f"user_subscriptions_list:{user_id}*",
        f"user_filters:{user_id}*",
        f"subscription_status:{user_id}*"
    ]

    if subscription_id:
        patterns.append(f"subscription:{subscription_id}*")

    with log_context(logger, user_id=user_id, subscription_id=subscription_id):
        deleted_count = 0
        aggregator = LogAggregator(logger, f"invalidate_subscription_caches_{user_id}")

        for pattern in patterns:
            count = BaseCacheManager.delete_pattern(pattern)
            deleted_count += count
            aggregator.add_item({'pattern': pattern, 'count': count}, success=True)

        aggregator.log_summary()

        logger.debug("Invalidated subscription cache keys for user", extra={
            'user_id': user_id,
            'subscription_id': subscription_id,
            'total_deleted': deleted_count
        })

        return deleted_count


@log_operation("invalidate_favorite_caches")
def invalidate_favorite_caches(user_id: int) -> int:
    """
    Invalidate favorite-related caches for a user.

    Args:
        user_id: Database user ID

    Returns:
        Number of invalidated cache keys
    """
    patterns = [
        f"user_favorites:{user_id}*"
    ]

    with log_context(logger, user_id=user_id):
        deleted_count = 0
        aggregator = LogAggregator(logger, f"invalidate_favorite_caches_{user_id}")

        for pattern in patterns:
            count = BaseCacheManager.delete_pattern(pattern)
            deleted_count += count
            aggregator.add_item({'pattern': pattern, 'count': count}, success=True)

        aggregator.log_summary()

        logger.debug("Invalidated favorite cache keys for user", extra={
            'user_id': user_id,
            'total_deleted': deleted_count
        })

        return deleted_count