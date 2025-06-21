# services/telegram_service/app/celery_app.py
from common.celery_app import celery_app

# Error handlers would be imported here if needed in the future


# Telegram-specific configuration
celery_app.conf.update(
    # Throttling to respect Telegram API limits
    worker_concurrency=2,  # Limit concurrent tasks to avoid Telegram rate limits
)
