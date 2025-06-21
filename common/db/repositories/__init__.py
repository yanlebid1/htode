# common/db/repositories/__init__.py
import os
from common.utils.logging_config import setup_logging
from common.utils.log_management import setup_file_logging

# Initialize repository logger
logger = setup_logging("db_repositories", log_level="WARNING", log_format="text")

# Add file logging if we're in production
if os.getenv("ENVIRONMENT", "development") == "production":
    setup_file_logging(
        logger,
        log_dir="/app/logs/db_repositories",
        max_bytes=10 * 1024 * 1024,  # 10MB
        backup_count=5,
        when="d",
        interval=1,
    )

# Export repositories
from common.db.repositories.user_repository import UserRepository
from common.db.repositories.ad_repository import AdRepository
from common.db.repositories.subscription_repository import SubscriptionRepository
from common.db.repositories.favorite_repository import FavoriteRepository
from common.db.repositories.payment_repository import PaymentRepository
from common.db.repositories.verification_repository import VerificationRepository

# Export logger for use in other modules
__all__ = [
    "logger",
    "UserRepository",
    "AdRepository",
    "SubscriptionRepository",
    "FavoriteRepository",
    "PaymentRepository",
    "VerificationRepository",
]
