# common/flows/__init__.py
import os
from common.utils.logging_config import setup_logging
from common.utils.log_management import setup_file_logging

# Initialize flows library logger
logger = setup_logging('common_flows', log_level='INFO', log_format='text')

# Add file logging if we're in production
if os.getenv('ENVIRONMENT', 'development') == 'production':
    setup_file_logging(
        logger,
        log_dir="/app/logs/common_flows",
        max_bytes=10 * 1024 * 1024,  # 10MB
        backup_count=5,
        when='d',
        interval=1
    )

# Import everything else
from common.messaging.unified_flow import flow_library
from .subscription_flow import subscription_flow
from .property_search_flow import property_search_flow

# Export logger and flow_library for use in other modules
__all__ = ['logger', 'flow_library']