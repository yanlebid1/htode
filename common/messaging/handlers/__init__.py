# common/messaging/handlers/__init__.py

import os
from common.utils.logging_config import setup_logging
from common.utils.log_management import setup_file_logging

# Initialize messaging handlers logger
logger = setup_logging('messaging_handlers', log_level='INFO', log_format='text')

# Add file logging if we're in production
if os.getenv('ENVIRONMENT', 'development') == 'production':
    setup_file_logging(
        logger,
        log_dir="/app/logs/messaging_handlers",
        max_bytes=10 * 1024 * 1024,  # 10MB
        backup_count=5,
        when='d',
        interval=1
    )

# Export logger for use in other modules
__all__ = ['logger', 'handle_support_command', 'handle_support_category', 'SUPPORT_CATEGORIES']

from .support_handler import (
    handle_support_command,
    handle_support_category,
    SUPPORT_CATEGORIES
)