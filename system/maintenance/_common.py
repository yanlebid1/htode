# system/maintenance/_common.py
# Shared imports and logger setup for all maintenance modules.

import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any

from sqlalchemy import or_, func, text

from common.celery_app import celery_app
from common.db.session import db_session
from common.db.models.user import User
from common.db.models.subscription import UserFilter
from common.utils.cache import redis_client, CacheTTL
from common.config import GEO_ID_MAPPING
from common.utils.cache_managers import BaseCacheManager, AdCacheManager, UserCacheManager
from common.utils.logging_config import (
    setup_logging,
    log_operation,
    log_context,
    LogAggregator,
)
from common.utils.log_management import setup_file_logging
from common.constants import (
    SUBSCRIPTION_REMINDER_DAYS,
    CLEANUP_DEFAULT_DAYS,
    ACTIVE_USER_LOOKBACK_DAYS,
)

# Initialize system logger (shared across all maintenance modules)
logger = setup_logging("system_maintenance", log_level="INFO", log_format="text")

# Add file logging if we're in production
if os.getenv("ENVIRONMENT", "development") == "production":
    setup_file_logging(
        logger,
        log_dir="/app/logs/system",
        max_bytes=10 * 1024 * 1024,  # 10MB
        backup_count=5,
        when="d",
        interval=1,
    )
