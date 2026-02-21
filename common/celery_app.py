# common/celery_app.py
from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue
from common.config import REDIS_URL
import importlib
import logging
import os

# Use Redis cluster for Celery - queue Redis for high throughput
REDIS_QUEUE_URL = os.getenv("REDIS_QUEUE_URL", REDIS_URL)

celery_app = Celery("shared_app", broker=REDIS_QUEUE_URL, backend=REDIS_QUEUE_URL)

# Common configuration
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone and time settings
    timezone="UTC",
    enable_utc=True,
    # Task execution settings
    task_acks_late=True,  # Tasks are acknowledged after execution (not before)
    task_reject_on_worker_lost=True,  # Reject tasks if worker crashes or disconnects
    worker_prefetch_multiplier=1,  # Prefetch just one task at a time for better load balancing
    # Task time limits — prevent runaway tasks from blocking workers indefinitely
    task_soft_time_limit=300,      # 5 min soft limit — raises SoftTimeLimitExceeded
    task_time_limit=360,           # 6 min hard kill
    task_track_started=True,       # Track when tasks enter "started" state
    # Retry settings
    task_default_retry_delay=60,  # 1 minute delay between retries
    task_max_retries=3,  # Maximum number of retries
    # Result backend settings
    result_expires=86400,  # Results expire after 1 day
    # Error handling
    task_ignore_result=False,  # Store task results by default
    task_store_errors_even_if_ignored=True,  # Store errors even if results are ignored
    # Queue timeout settings
    broker_transport_options={
        "visibility_timeout": 43200,  # 12 hours (in seconds)
    },
    # Rate limiting - optimized for batch processing and high throughput
    task_annotations={
        "scraper_service.app.tasks.fetch_new_ads": {
            "rate_limit": "1/m",
            "time_limit": 1800,           # 30 min hard limit for scraping
            "soft_time_limit": 1500,      # 25 min soft limit
        },  # 1 per minute - scraping rate limit
        # BATCH NOTIFICATION SYSTEM - Safe rates respecting Telegram limits
        "common.tasks.notify_user_batch": {
            "rate_limit": "25/m"
        },  # SAFE: 25 batches/min × 250 users = 6,250 users/min (25 msg/sec limit per bot)
        "notifier_service.app.tasks.notify_user_with_ads": {
            "rate_limit": "30/m"
        },  # Increased from 10/m to 30/m for individual notifications
        "notifier_service.app.tasks.sort_and_notify_new_ads": {
            "rate_limit": "20/m"
        },  # 20 ad processing per minute
        # TELEGRAM API LIMITS - Safe optimized limits (respecting Telegram's 30/s official limit)
        "common.messaging.tasks.send_ad_with_extra_buttons": {
            "rate_limit": "25/s"
        },  # SAFE: 25 messages/sec = 1500 users/min (below Telegram's 30/s limit)
        "telegram_service.app.tasks.*": {
            "rate_limit": "20/s"
        },  # SAFE: General Telegram tasks under official limit
        # MAINTENANCE TASKS - Conservative limits
        "system.maintenance.optimize_database": {
            "rate_limit": "1/h"
        },  # Max once per hour
        "system.maintenance.cleanup_redis_cache": {
            "rate_limit": "1/h"
        },  # Once per hour
        "system.maintenance.backup_database": {
            "rate_limit": "1/h",
            "time_limit": 3600,        # 1 hour hard limit
            "soft_time_limit": 1800,   # 30 min soft limit
        },
    },
)


# Queue definitions with priorities
task_exchange = Exchange("tasks", type="topic")

celery_app.conf.task_queues = (
    # High priority - scraping and ad processing
    Queue("scraper_queue", task_exchange, routing_key="scraper.#", priority=10),
    Queue("priority_queue", task_exchange, routing_key="priority.#", priority=9),
    # Medium priority - phone extraction
    Queue("phone_extraction_queue", task_exchange, routing_key="phones.#", priority=5),
    # Low-Medium priority - telegram API
    Queue("telegram_queue", task_exchange, routing_key="telegram.#", priority=3),
    # Low priority - batch notifications
    Queue("notification_queue", task_exchange, routing_key="notify.#", priority=1),
    # Maintenance tasks
    Queue("maintenance_queue", task_exchange, routing_key="maintenance.#", priority=2),
    # Dead letter queue for permanently failed tasks
    Queue("dead_letter", Exchange("dead_letter"), routing_key="dead_letter"),
    
    # Multi-bot queues - flower-themed bot pool 🌸
    # Each flower bot gets its own queue for parallel processing
    *[Queue(f"telegram_bot_{bot_name}_queue", task_exchange, 
            routing_key=f"telegram.bot.{bot_name}", priority=3)
      for bot_name in ["orchid", "tulip", "daisy", "lavender", "jasmine",
                       "sunflower", "lotus", "peony", "violet", "azalea",
                       "clover", "marigold", "bluebell", "gardenia", "aster",
                       "hibiscus", "freesia", "verbena", "hyacinth", "fuchsia"]],
)

# Enable priority support
celery_app.conf.task_queue_max_priority = 10
celery_app.conf.task_default_priority = 5

# Service-specific queue routing
celery_app.conf.task_routes = {
    # Scraper tasks - highest priority
    "scraper_service.app.tasks.*": {
        "queue": "scraper_queue",
        "routing_key": "scraper.tasks",
        "priority": 10,
    },
    # Phone extraction - medium priority
    "extract_phones_for_ad": {
        "queue": "phone_extraction_queue",
        "routing_key": "phones.extract",
        "priority": 5,
    },
    "common.tasks.extract_phones_for_ad": {
        "queue": "phone_extraction_queue",
        "routing_key": "phones.extract",
        "priority": 5,
    },
    # Batch notifications - low priority
    "notify_user_batch": {
        "queue": "notification_queue",
        "routing_key": "notify.batch",
        "priority": 1,
    },
    "common.tasks.notify_user_batch": {
        "queue": "notification_queue",
        "routing_key": "notify.batch",
        "priority": 1,
    },
    # Telegram tasks
    "telegram_service.app.tasks.*": {
        "queue": "telegram_queue",
        "routing_key": "telegram.tasks",
        "priority": 3,
    },
    "common.messaging.tasks.send_ad_with_extra_buttons": {
        "queue": "telegram_queue",
        "routing_key": "telegram.send",
        "priority": 3,
    },
    # Multi-bot messaging task - routes to bot-specific queues
    "common.messaging.tasks.send_ad_multibot": {
        "queue": "telegram_queue",  # Default queue
        "routing_key": "telegram.multibot",
        "priority": 3,
    },
    # Notifier tasks - use priority queue
    "notifier_service.app.tasks.*": {
        "queue": "priority_queue",
        "routing_key": "priority.notify",
        "priority": 8,
    },
    # Maintenance tasks
    "system.maintenance.*": {
        "queue": "maintenance_queue",
        "routing_key": "maintenance.tasks",
        "priority": 2,
    },
    # Cleanup tasks
    "common.tasks.cleanup_stale_extractions": {
        "queue": "maintenance_queue",
        "routing_key": "maintenance.cleanup",
        "priority": 2,
    },
}

# Scheduled tasks
celery_app.conf.beat_schedule = {
    "subscription-reminders-daily": {
        "task": "telegram_service.app.tasks.send_subscription_reminders",
        "schedule": crontab(hour=10, minute=0),  # Run daily at 10:00 AM
    },
    "fetch-new-ads-every-5-minutes": {
        "task": "scraper_service.app.tasks.fetch_new_ads",
        "schedule": 300.0,  # 5 minutes in seconds
    },
    "system-maintenance-weekly": {
        "task": "system.maintenance.cleanup_old_ads",
        "schedule": crontab(day_of_week="sun", hour=2, minute=0),  # Sunday at 2 AM
        "kwargs": {
            "days_old": 30,
            "check_activity": True,
        },  # Clean ads older than 30 days and check if they're inactive
    },
    "check-expiring-subscriptions-daily": {
        "task": "telegram_service.app.tasks.check_expiring_subscriptions",
        "schedule": crontab(hour=9, minute=0),  # Run daily at 9:00 AM
    },
    # Daily maintenance task for cleaning inactive ads
    "cleanup-inactive-ads-daily": {
        "task": "system.maintenance.cleanup_old_ads",
        "schedule": crontab(hour=3, minute=0),  # Daily at 3 AM
        "kwargs": {
            "days_old": 7,
            "check_activity": True,
        },  # Check and clean inactive ads older than 7 days
    },
    # Daily cleanup of expired verification codes
    "cleanup-expired-verification-codes": {
        "task": "system.maintenance.cleanup_expired_verification_codes",
        "schedule": crontab(hour=1, minute=30),  # Daily at 1:30 AM
    },
    # Weekly subscription statistics
    "generate-subscription-statistics": {
        "task": "system.maintenance.check_subscription_statistics",
        "schedule": crontab(day_of_week="mon", hour=7, minute=0),  # Monday at 7 AM
    },
    # New maintenance tasks
    # Daily cleanup of Redis cache
    "cleanup-redis-cache-daily": {
        "task": "system.maintenance.cleanup_redis_cache",
        "schedule": crontab(hour=4, minute=30),  # Daily at 4:30 AM
        "kwargs": {
            "pattern": "*",
            "older_than_days": 7,
        },  # Clean all cache items older than 7 days
    },
    # Weekly database optimization
    "optimize-database-weekly": {
        "task": "system.maintenance.optimize_database",
        "schedule": crontab(day_of_week="sat", hour=3, minute=0),  # Saturday at 3 AM
    },
    # Cache warming every 6 hours
    "cache-warming": {
        "task": "system.maintenance.cache_warming",
        "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours
    },
    # Check database connections every hour
    "check-database-connections": {
        "task": "system.maintenance.check_database_connections",
        "schedule": crontab(minute=15, hour="*/1"),  # Every hour at 15 minutes past
    },
    # Update currency rate at 9 AM
    "update-currency-rate-morning": {
        "task": "system.maintenance.update_currency_rate",
        "schedule": crontab(hour=9, minute=0),  # Daily at 9:00 AM
    },
    # Update currency rate at 6 PM
    "update-currency-rate-evening": {
        "task": "system.maintenance.update_currency_rate",
        "schedule": crontab(hour=18, minute=0),  # Daily at 6:00 PM
    },
    # Cleanup stale phone extractions
    "cleanup-stale-phone-extractions": {
        "task": "common.tasks.cleanup_stale_extractions",
        "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours
    },
    # Daily PostgreSQL backup to S3
    "backup-database-daily": {
        "task": "system.maintenance.backup_database",
        "schedule": crontab(hour=2, minute=0),  # Daily at 2 AM UTC
    },
    # Weekly cleanup of old backups from S3
    "cleanup-old-backups-weekly": {
        "task": "system.maintenance.cleanup_old_backups",
        "schedule": crontab(day_of_week="sun", hour=4, minute=0),  # Sunday 4 AM
        "kwargs": {"retention_days": 30},
    },
}

# Ensure maintenance tasks are registered even if import errors occur; log failures explicitly
try:
    importlib.import_module("system.maintenance")
except Exception as _e:
    logging.getLogger(__name__).error("Failed to import system.maintenance: %s", _e)

# Also configure Celery to always import this module on worker start
celery_app.conf.update(imports=["system.maintenance"])
