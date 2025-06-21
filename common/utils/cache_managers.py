# common/utils/cache_managers.py
import json
from typing import Dict, Any, List, Optional, Union

from common.utils.cache import redis_client, CacheTTL, get_entity_cache_key
from common.utils.logging_config import log_operation, log_context, LogAggregator

# Import the logger from the parent module
from . import logger


class BaseCacheManager:
    """Base class for all cache managers"""

    @staticmethod
    @log_operation("cache_get")
    def get(key: str) -> Optional[Any]:
        """Get a value from a cache"""
        with log_context(logger, cache_key=key):
            data = redis_client.get(key)
            if data:
                try:
                    result = json.loads(data)
                    logger.debug("Cache hit", extra={"key": key[:50]})
                    return result
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON in cache", extra={"key": key})
                    return None
            logger.debug("Cache miss", extra={"key": key[:50]})
            return None

    @staticmethod
    @log_operation("cache_set")
    def set(key: str, value: Any, ttl: int = CacheTTL.STANDARD) -> None:
        """Set a value in the cache"""
        with log_context(logger, cache_key=key, ttl=ttl):
            try:
                # Use default=str to safely serialize non-standard types like Decimal
                serialized = json.dumps(value, default=str)
                redis_client.set(key, serialized, ex=ttl)
                logger.debug("Value cached", extra={"key": key[:50], "ttl": ttl})
            except (TypeError, ValueError) as e:
                logger.error(
                    "Failed to serialize value for cache",
                    exc_info=True,
                    extra={"key": key, "error_type": type(e).__name__},
                )

    @staticmethod
    @log_operation("cache_delete")
    def delete(key: str) -> None:
        """Delete a cache key"""
        with log_context(logger, cache_key=key):
            redis_client.delete(key)
            logger.debug("Cache key deleted", extra={"key": key[:50]})

    @staticmethod
    @log_operation("cache_exists")
    def key_exists(key: str) -> bool:
        """Check if a key exists in the cache"""
        with log_context(logger, cache_key=key):
            exists = bool(redis_client.exists(key))
            logger.debug("Cache key check", extra={"key": key[:50], "exists": exists})
            return exists

    @staticmethod
    @log_operation("cache_delete_pattern")
    def delete_pattern(pattern: str) -> int:
        """
        Delete all keys matching a pattern

        Args:
            pattern: Redis a key pattern to match (e.g., "user:*:filters")

        Returns:
            Number of deleted keys
        """
        with log_context(logger, pattern=pattern):
            try:
                keys = redis_client.keys(pattern)
                if keys:
                    count = redis_client.delete(*keys)
                    logger.info(
                        "Deleted keys by pattern",
                        extra={"pattern": pattern, "count": count},
                    )
                    return count
                else:
                    logger.debug(
                        "No keys found for pattern", extra={"pattern": pattern}
                    )
                    return 0
            except Exception as e:
                logger.error(
                    "Error deleting keys by pattern",
                    exc_info=True,
                    extra={"pattern": pattern, "error_type": type(e).__name__},
                )
                return 0

    @staticmethod
    @log_operation("cache_delete_keys")
    def delete_keys(keys: List[str]) -> int:
        """
        Delete multiple keys

        Args:
            keys: List of keys to delete

        Returns:
            Number of deleted keys
        """
        if not keys:
            return 0

        with log_context(logger, key_count=len(keys)):
            try:
                existing_keys = [key for key in keys if redis_client.exists(key)]
                if existing_keys:
                    count = redis_client.delete(*existing_keys)
                    logger.info(
                        "Deleted multiple keys",
                        extra={
                            "requested_count": len(keys),
                            "existing_count": len(existing_keys),
                            "deleted_count": count,
                        },
                    )
                    return count
                else:
                    logger.debug(
                        "No existing keys to delete",
                        extra={"requested_count": len(keys)},
                    )
                    return 0
            except Exception as e:
                logger.error(
                    "Error deleting multiple keys",
                    exc_info=True,
                    extra={"key_count": len(keys), "error_type": type(e).__name__},
                )
                return 0

    @staticmethod
    @log_operation("invalidate_keys_for_entity")
    def invalidate_keys_for_entity(
        entity_type: str, entity_id: Union[int, str], extra_patterns: List[str] = None
    ) -> int:
        """
        Invalidate all keys related to a specific entity

        Args:
            entity_type: Type of entity (e.g., 'user', 'ad')
            entity_id: Entity ID
            extra_patterns: Optional additional patterns to match

        Returns:
            Number of invalidated keys
        """
        with log_context(logger, entity_type=entity_type, entity_id=entity_id):
            aggregator = LogAggregator(logger, f"invalidate_{entity_type}_{entity_id}")

            # Base pattern for this entity
            pattern = f"{entity_type}:{entity_id}*"
            count = BaseCacheManager.delete_pattern(pattern)
            aggregator.add_item({"pattern": pattern, "count": count}, success=True)

            # Process additional patterns if provided
            if extra_patterns:
                for extra_pattern in extra_patterns:
                    pattern_count = BaseCacheManager.delete_pattern(extra_pattern)
                    count += pattern_count
                    aggregator.add_item(
                        {"pattern": extra_pattern, "count": pattern_count}, success=True
                    )

            aggregator.log_summary()
            return count


class UserCacheManager(BaseCacheManager):
    """Manager for user-related cache operations"""

    @staticmethod
    @log_operation("get_user_filters")
    def get_filters(user_id: int) -> Optional[Dict[str, Any]]:
        """Get cached user filters"""
        key = get_entity_cache_key("user_filters", user_id)
        with log_context(logger, user_id=user_id):
            return BaseCacheManager.get(key)

    @staticmethod
    @log_operation("set_user_filters")
    def set_filters(
        user_id: int, filters_data: Dict[str, Any], ttl: int = CacheTTL.MEDIUM
    ) -> None:
        """Cache user filters"""
        key = get_entity_cache_key("user_filters", user_id)
        with log_context(logger, user_id=user_id):
            BaseCacheManager.set(key, filters_data, ttl)

    @staticmethod
    @log_operation("get_subscription_status")
    def get_subscription_status(user_id: int) -> Optional[Dict[str, Any]]:
        """Get cached subscription status"""
        key = get_entity_cache_key("subscription_status", user_id)
        with log_context(logger, user_id=user_id):
            return BaseCacheManager.get(key)

    @staticmethod
    @log_operation("set_subscription_status")
    def set_subscription_status(
        user_id: int, status_data: Dict[str, Any], ttl: int = CacheTTL.MEDIUM
    ) -> None:
        """Cache subscription status"""
        key = get_entity_cache_key("subscription_status", user_id)
        with log_context(logger, user_id=user_id):
            BaseCacheManager.set(key, status_data, ttl)

    @staticmethod
    @log_operation("invalidate_all_user_caches")
    def invalidate_all(user_id: int) -> int:
        """Invalidate all user-related caches"""
        from common.utils.cache import invalidate_user_caches

        with log_context(logger, user_id=user_id):
            return invalidate_user_caches(user_id)


class SubscriptionCacheManager(BaseCacheManager):
    """Manager for subscription-related cache operations"""

    @staticmethod
    @log_operation("get_user_subscriptions")
    def get_user_subscriptions(user_id: int) -> Optional[List[Dict[str, Any]]]:
        """Get a cached user subscriptions list"""
        key = get_entity_cache_key("user_subscriptions_list", user_id)
        with log_context(logger, user_id=user_id):
            return BaseCacheManager.get(key)

    @staticmethod
    @log_operation("set_user_subscriptions")
    def set_user_subscriptions(
        user_id: int, subscriptions: List[Dict[str, Any]], ttl: int = CacheTTL.MEDIUM
    ) -> None:
        """Cache user subscriptions list"""
        key = get_entity_cache_key("user_subscriptions_list", user_id)
        with log_context(logger, user_id=user_id, count=len(subscriptions)):
            BaseCacheManager.set(key, subscriptions, ttl)

    @staticmethod
    @log_operation("invalidate_all_subscription_caches")
    def invalidate_all(user_id: int, subscription_id: Optional[int] = None) -> int:
        """Invalidate all subscription-related caches"""
        from common.utils.cache import invalidate_subscription_caches

        with log_context(logger, user_id=user_id, subscription_id=subscription_id):
            return invalidate_subscription_caches(user_id, subscription_id)


class AdCacheManager(BaseCacheManager):
    """Manager for ad-related cache operations"""

    @staticmethod
    @log_operation("get_full_ad_data")
    def get_full_ad_data(ad_id: int) -> Optional[Dict[str, Any]]:
        """Get cached full ad data"""
        key = get_entity_cache_key("full_ad", ad_id)
        with log_context(logger, ad_id=ad_id):
            return BaseCacheManager.get(key)

    @staticmethod
    @log_operation("set_full_ad_data")
    def set_full_ad_data(
        ad_id: int, ad_data: Dict[str, Any], ttl: int = CacheTTL.MEDIUM
    ) -> None:
        """Cache full ad data"""
        key = get_entity_cache_key("full_ad", ad_id)
        with log_context(logger, ad_id=ad_id):
            BaseCacheManager.set(key, ad_data, ttl)

    @staticmethod
    @log_operation("get_ad_images")
    def get_ad_images(ad_id: int) -> Optional[List[str]]:
        """Get cached ad images"""
        key = get_entity_cache_key("ad_images", ad_id)
        with log_context(logger, ad_id=ad_id):
            return BaseCacheManager.get(key)

    @staticmethod
    @log_operation("set_ad_images")
    def set_ad_images(ad_id: int, images: List[str], ttl: int = CacheTTL.LONG) -> None:
        """Cache ad images"""
        key = get_entity_cache_key("ad_images", ad_id)
        with log_context(logger, ad_id=ad_id, image_count=len(images)):
            BaseCacheManager.set(key, images, ttl)

    @staticmethod
    @log_operation("get_ad_description")
    def get_ad_description(resource_url: str) -> Optional[str]:
        """Get cached ad description"""
        key = get_entity_cache_key("ad_description", resource_url)
        with log_context(logger, resource_url=resource_url[:50]):
            try:
                data = redis_client.get(key)
                if data:
                    logger.debug(
                        "Cache hit for ad description", extra={"key": key[:50]}
                    )
                    return data.decode("utf-8")
                logger.debug("Cache miss for ad description", extra={"key": key[:50]})
                return None
            except Exception as e:
                logger.error(
                    "Error getting ad description from cache",
                    exc_info=True,
                    extra={"key": key[:50], "error_type": type(e).__name__},
                )
                return None

    @staticmethod
    @log_operation("set_ad_description")
    def set_ad_description(
        resource_url: str, description: str, ttl: int = CacheTTL.LONG
    ) -> None:
        """Cache ad description"""
        key = get_entity_cache_key("ad_description", resource_url)
        with log_context(logger, resource_url=resource_url[:50]):
            try:
                redis_client.set(key, description, ex=ttl)
                logger.debug(
                    "Cached ad description", extra={"key": key[:50], "ttl": ttl}
                )
            except Exception as e:
                logger.error(
                    "Error setting ad description in cache",
                    exc_info=True,
                    extra={"key": key[:50], "error_type": type(e).__name__},
                )

    @staticmethod
    @log_operation("invalidate_all_ad_caches")
    def invalidate_all(ad_id: int, resource_url: Optional[str] = None) -> int:
        """
        Invalidate all ad-related caches

        Args:
            ad_id: Ad ID
            resource_url: Optional resource URL

        Returns:
            Number of invalidated keys
        """
        with log_context(logger, ad_id=ad_id, resource_url=resource_url):
            aggregator = LogAggregator(logger, f"invalidate_ad_{ad_id}")

            # Collect keys to delete
            keys_to_delete = [
                get_entity_cache_key("full_ad", ad_id),
                get_entity_cache_key("ad_images", ad_id),
                get_entity_cache_key("matching_users", ad_id),
            ]

            # Add resource URL-related keys
            if resource_url:
                keys_to_delete.extend(
                    [
                        get_entity_cache_key("extra_images", resource_url),
                        get_entity_cache_key("ad_description", resource_url),
                    ]
                )

            # Delete all collected keys
            deleted_count = BaseCacheManager.delete_keys(keys_to_delete)
            aggregator.add_item(
                {"keys": len(keys_to_delete), "deleted": deleted_count}, success=True
            )

            # Also delete any pattern-based keys that might be related
            pattern_keys = [
                f"ad:{ad_id}:*",
                "matching_users:*",  # This might be broader than needed
            ]

            for pattern in pattern_keys:
                count = BaseCacheManager.delete_pattern(pattern)
                deleted_count += count
                aggregator.add_item({"pattern": pattern, "count": count}, success=True)

            aggregator.log_summary()
            logger.info(
                "Invalidated all ad caches",
                extra={"ad_id": ad_id, "total_deleted": deleted_count},
            )

            return deleted_count


class FavoriteCacheManager(BaseCacheManager):
    """Manager for favorite-related cache operations"""

    @staticmethod
    @log_operation("get_user_favorites")
    def get_user_favorites(user_id: int) -> Optional[List[Dict[str, Any]]]:
        """Get cached user favorites"""
        key = get_entity_cache_key("user_favorites", user_id)
        with log_context(logger, user_id=user_id):
            return BaseCacheManager.get(key)

    @staticmethod
    @log_operation("set_user_favorites")
    def set_user_favorites(
        user_id: int, favorites: List[Dict[str, Any]], ttl: int = CacheTTL.MEDIUM
    ) -> None:
        """Cache user favorites"""
        key = get_entity_cache_key("user_favorites", user_id)
        with log_context(logger, user_id=user_id, count=len(favorites)):
            BaseCacheManager.set(key, favorites, ttl)

    @staticmethod
    @log_operation("invalidate_all_favorite_caches")
    def invalidate_all(user_id: int) -> int:
        """Invalidate all favorite-related caches"""
        from common.utils.cache import invalidate_favorite_caches

        with log_context(logger, user_id=user_id):
            return invalidate_favorite_caches(user_id)
