# common/utils/logging_config.py
import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from functools import wraps
import inspect
from contextlib import contextmanager


class StructuredLogger(logging.Logger):
    """Custom logger that adds structured logging capabilities"""

    def _log(self, level, msg, args, exc_info=None, extra=None, stack_info=False):
        if extra is None:
            extra = {}

        # Add context information if available
        if hasattr(self, '_context'):
            extra.update(self._context)

        # Add timestamp in ISO format
        extra['timestamp'] = datetime.utcnow().isoformat()

        # Add service name if set
        if hasattr(self, '_service_name'):
            extra['service'] = self._service_name

        super()._log(level, msg, args, exc_info, extra, stack_info)


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs logs in JSON format"""

    def format(self, record):
        log_record = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'name': record.name,
            'level': record.levelname,
            'message': record.getMessage(),
            'service': getattr(record, 'service', 'unknown')
        }

        # Add exception info if present
        if record.exc_info:
            log_record['exception'] = self.formatException(record.exc_info)

        # Add any extra fields (context, custom extras, etc.)
        for key, value in record.__dict__.items():
            if key not in [
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
                'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                'thread', 'threadName', 'processName', 'process', 'message'
            ]:
                # Ensure value is JSON-serializable; fallback to string
                try:
                    json.dumps(value)
                    log_record[key] = value
                except (TypeError, ValueError):
                    log_record[key] = repr(value)

        # Use default=str to convert any remaining unserializable objects
        return json.dumps(log_record, default=str)


def setup_logging(
        service_name: str,
        log_level: str = 'INFO',
        log_format: str = 'json'  # 'json' or 'text'
) -> logging.Logger:
    """
    Set up logging configuration for a service

    Args:
        service_name: Name of the service
        log_level: Logging level
        log_format: Format to use ('json' or 'text')

    Returns:
        Configured logger
    """
    # Set custom logger class
    logging.setLoggerClass(StructuredLogger)

    # Create logger
    logger = logging.getLogger(service_name)
    logger.setLevel(getattr(logging, log_level.upper()))

    # Clear any existing handlers
    logger.handlers.clear()

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, log_level.upper()))

    # Set formatter
    if log_format == 'json':
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Add service name to logger
    logger._service_name = service_name

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


@contextmanager
def log_context(logger: logging.Logger, **kwargs):
    """
    Context manager for adding contextual information to logs

    Args:
        logger: Logger instance
        **kwargs: Context key-value pairs
    """
    old_context = getattr(logger, '_context', {})
    new_context = old_context.copy()
    new_context.update(kwargs)
    logger._context = new_context
    try:
        yield
    finally:
        logger._context = old_context


def log_operation(operation_name: str):
    """
    Decorator for logging function entry and exit

    Args:
        operation_name: Name of the operation being performed
    """

    def decorator(func):
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Get logger from first argument if it's a class method
            if args and hasattr(args[0], 'logger'):
                logger = args[0].logger
            elif hasattr(func, '__module__'):
                logger = logging.getLogger(func.__module__)
            else:
                logger = logging.getLogger(__name__)

            with log_context(logger, operation=operation_name):
                logger.debug(f"Starting {operation_name}", extra={
                    'args': str(args[1:])[:100],  # Limit args length
                    'kwargs': str(kwargs)[:100]
                })

                try:
                    result = func(*args, **kwargs)
                    logger.debug(f"Completed {operation_name}")
                    return result
                except Exception as e:
                    logger.exception(f"Error in {operation_name}: {e}")
                    raise

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Get logger from first argument if it's a class method
            if args and hasattr(args[0], 'logger'):
                logger = args[0].logger
            elif hasattr(func, '__module__'):
                logger = logging.getLogger(func.__module__)
            else:
                logger = logging.getLogger(__name__)

            with log_context(logger, operation=operation_name):
                logger.debug(f"Starting {operation_name}", extra={
                    'args': str(args[1:])[:100],  # Limit args length
                    'kwargs': str(kwargs)[:100]
                })

                try:
                    result = await func(*args, **kwargs)
                    logger.debug(f"Completed {operation_name}")
                    return result
                except Exception as e:
                    logger.exception(f"Error in {operation_name}: {e}")
                    raise

        # Return appropriate wrapper based on function type
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


class LogAggregator:
    """
    Aggregates multiple log entries into a single summary log
    """

    def __init__(self, logger: logging.Logger, operation: str):
        self.logger = logger
        self.operation = operation
        self.items = []
        self.errors = []
        self.start_time = datetime.utcnow()

    def add_item(self, item: Dict[str, Any], success: bool = True):
        """Add an item to the aggregation"""
        self.items.append({'item': item, 'success': success})

    def add_error(self, error: str, item: Optional[Dict[str, Any]] = None):
        """Add an error to the aggregation"""
        self.errors.append({'error': error, 'item': item})

    def log_summary(self, level: int = logging.INFO):
        """Log the aggregated summary"""
        end_time = datetime.utcnow()
        duration = (end_time - self.start_time).total_seconds()

        successful_items = [item for item in self.items if item['success']]
        failed_items = [item for item in self.items if not item['success']]

        summary = {
            'operation': self.operation,
            'duration_seconds': duration,
            'total_items': len(self.items),
            'successful_items': len(successful_items),
            'failed_items': len(failed_items),
            'errors': len(self.errors)
        }

        self.logger.log(level, f"{self.operation} completed", extra=summary)

        # Log errors if any
        if self.errors:
            self.logger.error(f"{self.operation} encountered errors", extra={
                'errors': self.errors[:10]  # Limit to first 10 errors
            })