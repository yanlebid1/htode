# services/scraper_service/app/celery_app.py
from common.celery_app import celery_app

# Import error handlers
try:
    import common.celery_error_handlers  # We'll create this file next
except ImportError:
    pass  # Silently continue if error handlers module doesn't exist yet

# Import tasks to register them
from . import tasks

# Scraper-specific configuration
celery_app.conf.update(
    # For example, scraper might need a longer task timeout
    task_time_limit=600,  # 10 minutes timeout
    worker_max_tasks_per_child=50,  # Restart worker after 50 tasks to prevent memory leaks
)

# Note: The beat schedule is already defined in common/celery_app.py
# and the rate limiting for fetch_new_ads is already set there as well