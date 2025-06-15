# common/utils/log_management.py
import os
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Optional


def setup_file_logging(
        logger: logging.Logger,
        log_dir: str = "/app/logs",
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
        when: str = 'd',
        interval: int = 1
) -> None:
    """
    Set up file-based logging with rotation

    Args:
        logger: Logger instance
        log_dir: Directory for log files
        max_bytes: Maximum size for rotating logs
        backup_count: Number of backup files to keep
        when: Time-based rotation unit ('d' for daily)
        interval: Rotation interval
    """
    # Ensure log directory exists
    os.makedirs(log_dir, exist_ok=True)

    service_name = getattr(logger, '_service_name', 'unknown')

    # Size-based rotation for error logs
    error_handler = RotatingFileHandler(
        os.path.join(log_dir, f"{service_name}_error.log"),
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))

    # Time-based rotation for all logs
    general_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, f"{service_name}.log"),
        when=when,
        interval=interval,
        backupCount=backup_count
    )
    general_handler.setLevel(logging.INFO)
    general_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))

    logger.addHandler(error_handler)
    logger.addHandler(general_handler)


def setup_log_aggregation(
        logger: logging.Logger,
        aggregation_backend: Optional[str] = None
) -> None:
    """
    Set up log aggregation backend (e.g., ELK stack, CloudWatch)

    Args:
        logger: Logger instance
        aggregation_backend: Backend to use ('elk', 'cloudwatch', etc.)
    """
    if aggregation_backend == 'elk':
        # Set up ELK stack logging
        pass
    elif aggregation_backend == 'cloudwatch':
        # Set up CloudWatch logging
        pass
    # Add more backends as needed