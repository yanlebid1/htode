# services/notifier_service/app/celery_app.py
from common.celery_app import celery_app

# Import error handlers
try:
    import common.celery_error_handlers  # We'll create this file next
except ImportError:
    pass  # Silently continue if error handlers module doesn't exist yet

# Import tasks to register them
from . import tasks

# Notifier-specific configuration if needed
# The common configuration already sets worker_prefetch_multiplier=1