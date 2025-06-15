# services/scraper_service/app/logging_config.py
import os
from common.utils.log_management import setup_log_aggregation
from . import logger


# Configure log aggregation if needed
def configure_logging():
    """Configure additional logging features for the scraper service"""

    # Set up log aggregation if configured
    aggregation_backend = os.getenv('LOG_AGGREGATION_BACKEND')
    if aggregation_backend:
        setup_log_aggregation(logger, aggregation_backend)

    # Add any service-specific logging configuration here
    logger.info("Scraper service logging configured", extra={
        'log_level': logger.level,
        'aggregation_backend': aggregation_backend,
        'environment': os.getenv('ENVIRONMENT', 'development')
    })


# Run configuration when module is imported
configure_logging()