# services/telegram_service/app/celery_app.py
from common.celery_app import celery_app

# Import error handlers
try:
    import common.celery_error_handlers  # We'll create this file next
except ImportError:
    pass  # Silently continue if error handlers module doesn't exist yet

from . import tasks
import common.messaging.tasks  # Add this line

# Telegram-specific configuration
celery_app.conf.update(
    # Throttling to respect Telegram API limits
    worker_concurrency=2,  # Limit concurrent tasks to avoid Telegram rate limits
)