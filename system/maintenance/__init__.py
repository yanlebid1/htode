# system/maintenance/__init__.py
# Re-exports all maintenance tasks for backward compatibility.

from .subscriptions import check_expiring_subscriptions
from .cleanup import cleanup_old_ads, clear_ad_cache, cleanup_expired_verification_codes
from .cache import cleanup_redis_cache, cache_warming
from .database import optimize_database, check_database_connections
from .statistics import check_subscription_statistics, update_currency_rate

__all__ = [
    "check_expiring_subscriptions",
    "cleanup_old_ads",
    "clear_ad_cache",
    "cleanup_expired_verification_codes",
    "cleanup_redis_cache",
    "cache_warming",
    "optimize_database",
    "check_database_connections",
    "check_subscription_statistics",
    "update_currency_rate",
]
