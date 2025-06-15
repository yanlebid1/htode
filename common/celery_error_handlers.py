# common/celery_error_handlers.py
import logging
from celery.signals import (
    task_failure, task_retry, worker_ready,
    worker_shutdown, beat_init
)

logger = logging.getLogger(__name__)


@task_failure.connect
def handle_task_failure(sender=None, task_id=None, exception=None,
                        args=None, kwargs=None, traceback=None, einfo=None, **_):
    """Log task failures with detailed information."""
    logger.error(
        f"Task {sender.name}[{task_id}] failed: {exception}\n"
        f"Args: {args}, Kwargs: {kwargs}\n"
        f"{einfo}"
    )

    # Optionally implement custom notification logic for critical task failures
    if sender.name in ['notifier_service.app.tasks.sort_and_notify_new_ads']:
        # Example: Send an alert to admin or log to a special channel
        logger.critical(f"CRITICAL TASK FAILURE: {sender.name}[{task_id}]")


@task_retry.connect
def handle_task_retry(sender=None, request=None, reason=None, einfo=None, **_):
    """Log task retries."""
    logger.warning(
        f"Task {sender.name}[{request.id}] being retried: {reason}\n"
        f"Args: {request.args}, Kwargs: {request.kwargs}\n"
        f"{einfo}"
    )


@worker_ready.connect
def worker_ready_handler(**_):
    """Log when a worker is ready to receive tasks."""
    logger.info("Celery worker is ready.")


@worker_shutdown.connect
def worker_shutdown_handler(**_):
    """Log when a worker is shutting down."""
    logger.warning("Celery worker is shutting down.")


@beat_init.connect
def beat_init_handler(sender, **_):
    """Log when the beat scheduler is initialized."""
    logger.info("Celery beat scheduler initialized.")