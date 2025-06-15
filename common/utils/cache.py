# common/utils/cache.py

import json
import hashlib
import redis
from typing import Union, Optional

from common.config import REDIS_URL
from common.utils.logging_config import log_operation, log_context, LogAggregator

# Import the common utils logger
from . import logger

# Create a Redis client instance
redis_client = redis.from_url(REDIS_URL)


# Standardized TTL values based on data access patterns
class CacheTTL:
    """Standard TTL values for different types of cached data"""
    SHORT = 60  # 1 minute - for frequently changing data
    MEDIUM = 300  # 5 minutes - for semi-stable data
    STANDARD = 3600  # 1 hour - for stable data
    LONG = 86400  # 1 day - for very stable data
    EXTENDED = 604800  # 1 week - for nearly static data


@log_operation("cache_key")
def cache_key(prefix, *args, **kwargs):
    """Generate a cache key from the arguments"""
    key_parts = [prefix]

    # Add positional args
    for arg in args:
        key_parts.append(str(arg))

    # Add keyword args, sorted by key
    for k in sorted(kwargs.keys()):
        key_parts.append(f"{k}:{kwargs[k]}")

    # Create hash for longer keys
    if len(":".join(key_parts)) > 200:
        result = f"{prefix}:{hashlib.md5(':'.join(key_parts).encode()).hexdigest()}"
    else:
        result = ":".join(key_parts)

    logger.debug("Generated cache key", extra={
        'prefix': prefix,
        'key': result[:50] + '...' if len(result) > 50 else result,
        'key_length': len(result)
    })

    return result


@log_operation("get_entity_cache_key")
def get_entity_cache_key(entity_type: str, entity_id: Union[int, str], suffix: Optional[str] = None) -> str:
    """
    Generate a standardized cache key for an entity.

    Args:
        entity_type: Type of entity (e.g., 'user', 'ad', 'subscription')
        entity_id: Entity identifier
        suffix: Optional additional suffix

    Returns:
        A standardized cache key string
    """
    key = f"{entity_type}:{entity_id}"
    if suffix:
        key += f":{suffix}"

    logger.debug("Generated entity cache key", extra={
        'entity_type': entity_type,
        'entity_id': entity_id,
        'suffix': suffix,
        'key': key
    })

    return key


def redis_cache(prefix, ttl=CacheTTL.STANDARD):
    """Cache decorator that uses Redis with standardized TTL"""

    def decorator(func):
        from functools import wraps

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            key = cache_key(prefix, *args, **kwargs)

            with log_context(logger, cache_key=key[:50], ttl=ttl, function=func.__name__):
                # Try to get from cache
                try:
                    cached = redis_client.get(key)
                    if cached:
                        logger.debug("Cache hit", extra={'key': key[:50]})
                        return json.loads(cached)
                except (redis.RedisError, json.JSONDecodeError) as e:
                    logger.warning("Cache retrieval error", exc_info=True, extra={
                        'key': key[:50],
                        'error_type': type(e).__name__
                    })

                # Execute function
                result = func(*args, **kwargs)

                # Cache result
                if result:
                    try:
                        redis_client.set(key, json.dumps(result), ex=ttl)
                        logger.debug("Cached result", extra={'key': key[:50], 'ttl': ttl})
                    except (redis.RedisError, json.JSONEncodeError) as e:
                        logger.warning("Cache write error", exc_info=True, extra={
                            'key': key[:50],
                            'error_type': type(e).__name__
                        })

                return result

        # Add cache invalidation method to the function
        def invalidate_cache(*args, **kwargs):
            if args or kwargs:
                # Invalidate specific key
                key = cache_key(prefix, *args, **kwargs)
                try:
                    redis_client.delete(key)
                    logger.debug("Invalidated cache key", extra={'key': key[:50]})
                except redis.RedisError as e:
                    logger.warning("Cache invalidation error", exc_info=True, extra={
                        'key': key[:50],
                        'error_type': type(e).__name__
                    })
            else:
                # Invalidate all keys with this prefix
                pattern = f"{prefix}:*"
                try:
                    keys = redis_client.keys(pattern)
                    if keys:
                        redis_client.delete(*keys)
                        logger.debug("Invalidated cache pattern", extra={
                            'pattern': pattern,
                            'count': len(keys)
                        })
                except redis.RedisError as e:
                    logger.warning("Cache pattern invalidation error", exc_info=True, extra={
                        'pattern': pattern,
                        'error_type': type(e).__name__
                    })

        wrapper.invalidate_cache = invalidate_cache
        return wrapper

    return decorator


def async_redis_cache(prefix, ttl=CacheTTL.STANDARD):
    """Cache decorator for async functions"""

    def decorator(func):
        from functools import wraps

        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            key = cache_key(prefix, *args, **kwargs)

            with log_context(logger, cache_key=key[:50], ttl=ttl, function=func.__name__):
                # Try to get from cache
                try:
                    cached = redis_client.get(key)
                    if cached:
                        logger.debug("Cache hit", extra={'key': key[:50]})
                        return json.loads(cached)
                except (redis.RedisError, json.JSONDecodeError) as e:
                    logger.warning("Cache retrieval error", exc_info=True, extra={
                        'key': key[:50],
                        'error_type': type(e).__name__
                    })

                # Execute function
                result = await func(*args, **kwargs)

                # Cache result
                if result:
                    try:
                        redis_client.set(key, json.dumps(result), ex=ttl)
                        logger.debug("Cached result", extra={'key': key[:50], 'ttl': ttl})
                    except (redis.RedisError, json.JSONEncodeError) as e:
                        logger.warning("Cache write error", exc_info=True, extra={
                            'key': key[:50],
                            'error_type': type(e).__name__
                        })

                return result

        # Add cache invalidation method to the function
        def invalidate_cache(*args, **kwargs):
            if args or kwargs:
                # Invalidate specific key
                key = cache_key(prefix, *args, **kwargs)
                try:
                    redis_client.delete(key)
                    logger.debug("Invalidated cache key", extra={'key': key[:50]})
                except redis.RedisError as e:
                    logger.warning("Cache invalidation error", exc_info=True, extra={
                        'key': key[:50],
                        'error_type': type(e).__name__
                    })
            else:
                # Invalidate all keys with this prefix
                pattern = f"{prefix}:*"
                try:
                    keys = redis_client.keys(pattern)
                    if keys:
                        redis_client.delete(*keys)
                        logger.debug("Invalidated cache pattern", extra={
                            'pattern': pattern,
                            'count': len(keys)
                        })
                except redis.RedisError as e:
                    logger.warning("Cache pattern invalidation error", exc_info=True, extra={
                        'pattern': pattern,
                        'error_type': type(e).__name__
                    })

        wrapper.invalidate_cache = invalidate_cache
        return wrapper

    return decorator


@log_operation("get_cached")
def get_cached(key, default=None):
    """Get a value from cache with fallback default"""
    with log_context(logger, cache_key=key):
        try:
            value = redis_client.get(key)
            if value:
                logger.debug("Cache hit", extra={'key': key})
                return json.loads(value)
            logger.debug("Cache miss", extra={'key': key})
            return default
        except (redis.RedisError, json.JSONDecodeError) as e:
            logger.warning("Cache retrieval error", exc_info=True, extra={
                'key': key,
                'error_type': type(e).__name__
            })
            return default


@log_operation("set_cached")
def set_cached(key, value, ttl=CacheTTL.STANDARD):
    """Set a value in cache with standard TTL"""
    with log_context(logger, cache_key=key, ttl=ttl):
        try:
            redis_client.set(key, json.dumps(value), ex=ttl)
            logger.debug("Cached value", extra={'key': key, 'ttl': ttl})
            return value
        except (redis.RedisError, json.JSONEncodeError) as e:
            logger.warning("Cache write error", exc_info=True, extra={
                'key': key,
                'error_type': type(e).__name__
            })
            return value


@log_operation("batch_get_cached")
def batch_get_cached(keys, prefix=""):
    """
    Get multiple values from cache in a single operation
    Returns a dict of {key: value} for found keys

    Args:
        keys: List of keys to retrieve
        prefix: Optional prefix for all keys

    Returns:
        Dictionary mapping original keys to their values
    """
    if not keys:
        return {}

    with log_context(logger, key_count=len(keys), prefix=prefix):
        aggregator = LogAggregator(logger, "batch_get_cached")

        # Create standardized keys
        prefixed_keys = [f"{prefix}:{k}" if prefix else k for k in keys]

        try:
            # Use Redis pipeline for batched operations
            with redis_client.pipeline() as pipe:
                for key in prefixed_keys:
                    pipe.get(key)
                values = pipe.execute()

            result = {}
            cache_hits = 0

            for i, value in enumerate(values):
                if value:
                    cache_hits += 1
                    original_key = keys[i]
                    try:
                        result[original_key] = json.loads(value)
                        aggregator.add_item({'key': original_key}, success=True)
                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON in cache", extra={'key': prefixed_keys[i]})
                        # Return the raw value if it can't be parsed as JSON
                        result[original_key] = value.decode('utf-8') if isinstance(value, bytes) else value
                        aggregator.add_error("Invalid JSON", {'key': original_key})
                else:
                    aggregator.add_item({'key': keys[i]}, success=False)

            logger.debug("Batch cache results", extra={
                'total_keys': len(keys),
                'cache_hits': cache_hits,
                'hit_rate': cache_hits / len(keys) if keys else 0
            })

            aggregator.log_summary()
            return result

        except redis.RedisError as e:
            logger.error("Batch cache retrieval error", exc_info=True, extra={
                'key_count': len(keys),
                'error_type': type(e).__name__
            })
            return {}


@log_operation("batch_set_cached")
def batch_set_cached(key_values, ttl=CacheTTL.STANDARD, prefix=""):
    """
    Set multiple values in cache in a single operation

    Args:
        key_values: Dict of {key: value} pairs to cache
        ttl: Cache TTL in seconds
        prefix: Optional prefix for all keys
    """
    if not key_values:
        return

    with log_context(logger, key_count=len(key_values), prefix=prefix, ttl=ttl):
        aggregator = LogAggregator(logger, "batch_set_cached")

        try:
            # Use Redis pipeline for batched operations
            with redis_client.pipeline() as pipe:
                for key, value in key_values.items():
                    full_key = f"{prefix}:{key}" if prefix else key
                    try:
                        serialized = json.dumps(value)
                        pipe.set(full_key, serialized, ex=ttl)
                        aggregator.add_item({'key': key}, success=True)
                    except (TypeError, ValueError) as e:
                        logger.warning("Failed to serialize value", extra={
                            'key': full_key,
                            'error': str(e)
                        })
                        # Try to store as string if serialization fails
                        pipe.set(full_key, str(value), ex=ttl)
                        aggregator.add_error("Serialization failed", {'key': key})
                pipe.execute()

            logger.debug("Batch cache set completed", extra={'key_count': len(key_values)})
            aggregator.log_summary()

        except redis.RedisError as e:
            logger.error("Batch cache write error", exc_info=True, extra={
                'key_count': len(key_values),
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
            try:
                keys = redis_client.keys(pattern)
                if keys:
                    count = redis_client.delete(*keys)
                    deleted_count += count
                    aggregator.add_item({'pattern': pattern, 'count': count}, success=True)
                else:
                    aggregator.add_item({'pattern': pattern, 'count': 0}, success=True)
            except redis.RedisError as e:
                logger.warning("Error invalidating pattern", exc_info=True, extra={
                    'pattern': pattern,
                    'error_type': type(e).__name__
                })
                aggregator.add_error(str(e), {'pattern': pattern})

        logger.debug("Invalidated user caches", extra={
            'user_id': user_id,
            'total_deleted': deleted_count
        })

        aggregator.log_summary()
        return deleted_count


@log_operation("invalidate_subscription_caches")
def invalidate_subscription_caches(user_id: int, subscription_id: Optional[int] = None) -> int:
    """
    Invalidate subscription-related caches for a user.

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
            try:
                keys = redis_client.keys(pattern)
                if keys:
                    count = redis_client.delete(*keys)
                    deleted_count += count
                    aggregator.add_item({'pattern': pattern, 'count': count}, success=True)
                else:
                    aggregator.add_item({'pattern': pattern, 'count': 0}, success=True)
            except redis.RedisError as e:
                logger.warning("Error invalidating pattern", exc_info=True, extra={
                    'pattern': pattern,
                    'error_type': type(e).__name__
                })
                aggregator.add_error(str(e), {'pattern': pattern})

        logger.debug("Invalidated subscription caches", extra={
            'user_id': user_id,
            'subscription_id': subscription_id,
            'total_deleted': deleted_count
        })

        aggregator.log_summary()
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
            try:
                keys = redis_client.keys(pattern)
                if keys:
                    count = redis_client.delete(*keys)
                    deleted_count += count
                    aggregator.add_item({'pattern': pattern, 'count': count}, success=True)
                else:
                    aggregator.add_item({'pattern': pattern, 'count': 0}, success=True)
            except redis.RedisError as e:
                logger.warning("Error invalidating pattern", exc_info=True, extra={
                    'pattern': pattern,
                    'error_type': type(e).__name__
                })
                aggregator.add_error(str(e), {'pattern': pattern})

        logger.debug("Invalidated favorite caches", extra={
            'user_id': user_id,
            'total_deleted': deleted_count
        })

        aggregator.log_summary()
        return deleted_count