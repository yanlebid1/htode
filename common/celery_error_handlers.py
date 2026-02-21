# common/celery_error_handlers.py
import logging
from celery.signals import (
    task_failure,
    task_retry,
    worker_ready,
    worker_shutdown,
    beat_init,
)

logger = logging.getLogger(__name__)


@task_failure.connect
def handle_task_failure(
    sender=None,
    task_id=None,
    exception=None,
    args=None,
    kwargs=None,
    traceback=None,
    einfo=None,
    **_,
):
    """Log task failures with detailed information."""
    logger.error(
        "Task failed",
        extra={
            "task_name": sender.name,
            "task_id": task_id,
            "error_type": type(exception).__name__,
            "error": str(exception),
            "args": str(args)[:200],
            "kwargs": str(kwargs)[:200],
        },
    )

    # Route to dead letter queue if max retries exhausted
    retries = getattr(sender.request, "retries", 0) if hasattr(sender, "request") else 0
    max_retries = getattr(sender, "max_retries", 3) or 3
    if retries >= max_retries:
        try:
            from common.celery_app import celery_app
            celery_app.send_task(
                "system.maintenance.dead_letter_log",
                queue="dead_letter",
                kwargs={
                    "original_task": sender.name,
                    "task_id": task_id,
                    "error": str(exception),
                    "args": str(args)[:500],
                    "kwargs": str(kwargs)[:500],
                },
            )
        except Exception as dlq_err:
            logger.error("Failed to send to dead letter queue", extra={"error": str(dlq_err)})

    if sender.name in ["notifier_service.app.tasks.sort_and_notify_new_ads"]:
        logger.critical(
            "CRITICAL TASK FAILURE",
            extra={"task_name": sender.name, "task_id": task_id},
        )


@task_retry.connect
def handle_task_retry(sender=None, request=None, reason=None, einfo=None, **_):
    """Log task retries."""
    logger.warning(
        "Task being retried",
        extra={
            "task_name": sender.name,
            "task_id": request.id,
            "reason": str(reason),
            "args": str(request.args)[:200],
            "kwargs": str(request.kwargs)[:200],
        },
    )


@worker_ready.connect
def worker_ready_handler(**_):
    """Log when a worker is ready to receive tasks."""
    logger.info("Celery worker is ready.")


@worker_shutdown.connect
def worker_shutdown_handler(**_):
    """Log when a worker is shutting down."""
    logger.warning("Celery worker is shutting down.")
    try:
        from common.utils.redis_cluster_manager import redis_cluster
        redis_cluster.close_connections()
        logger.info("Redis cluster connections closed on shutdown")
    except Exception as e:
        logger.error("Error closing Redis connections on shutdown", extra={"error": str(e)})


@beat_init.connect
def beat_init_handler(sender, **_):
    """Log when the beat scheduler is initialized."""
    logger.info("Celery beat scheduler initialized.")
