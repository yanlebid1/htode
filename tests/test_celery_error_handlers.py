# tests/test_celery_error_handlers.py

import sys
from unittest.mock import patch, MagicMock

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from common.celery_error_handlers import (
    handle_task_failure,
    handle_task_retry,
    worker_ready_handler,
    worker_shutdown_handler,
    beat_init_handler,
)


# ── handle_task_failure() ────────────────────────────────────────────────


class TestHandleTaskFailure:
    @patch("common.celery_error_handlers.logger")
    def test_logs_task_failure(self, mock_logger):
        sender = MagicMock()
        sender.name = "test_task"
        sender.request.retries = 0
        sender.max_retries = 3

        handle_task_failure(
            sender=sender,
            task_id="task-123",
            exception=ValueError("something broke"),
            args=(1, 2),
            kwargs={"key": "val"},
        )
        mock_logger.error.assert_called()
        call_args = mock_logger.error.call_args
        assert "Task failed" in call_args[0][0]

    @patch("common.celery_app.celery_app")
    @patch("common.celery_error_handlers.logger")
    def test_routes_to_dead_letter_queue_on_max_retries(self, mock_logger, mock_celery):
        sender = MagicMock()
        sender.name = "test_task"
        sender.request.retries = 3
        sender.max_retries = 3

        handle_task_failure(
            sender=sender,
            task_id="task-123",
            exception=RuntimeError("exhausted"),
            args=(),
            kwargs={},
        )
        mock_celery.send_task.assert_called_once()
        call_kwargs = mock_celery.send_task.call_args
        assert call_kwargs.kwargs.get("queue") == "dead_letter" or call_kwargs[1].get("queue") == "dead_letter"

    @patch("common.celery_error_handlers.logger")
    def test_logs_critical_for_critical_tasks(self, mock_logger):
        sender = MagicMock()
        sender.name = "notifier_service.app.tasks.sort_and_notify_new_ads"
        sender.request.retries = 0
        sender.max_retries = 3

        handle_task_failure(
            sender=sender,
            task_id="task-456",
            exception=Exception("critical fail"),
            args=(),
            kwargs={},
        )
        mock_logger.critical.assert_called_once()

    @patch("common.celery_error_handlers.logger")
    def test_does_not_log_critical_for_non_critical_tasks(self, mock_logger):
        sender = MagicMock()
        sender.name = "some_other_task"
        sender.request.retries = 0
        sender.max_retries = 3

        handle_task_failure(
            sender=sender,
            task_id="task-789",
            exception=Exception("non-critical"),
            args=(),
            kwargs={},
        )
        mock_logger.critical.assert_not_called()


# ── handle_task_retry() ──────────────────────────────────────────────────


class TestHandleTaskRetry:
    @patch("common.celery_error_handlers.logger")
    def test_logs_retry_warning(self, mock_logger):
        sender = MagicMock()
        sender.name = "test_task"
        request = MagicMock()
        request.id = "task-retry-1"
        request.args = (1,)
        request.kwargs = {}

        handle_task_retry(sender=sender, request=request, reason="timeout")
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "retried" in call_args[0][0]


# ── worker_ready_handler() ───────────────────────────────────────────────


class TestWorkerReadyHandler:
    @patch("common.celery_error_handlers.logger")
    def test_logs_worker_ready(self, mock_logger):
        worker_ready_handler()
        mock_logger.info.assert_called_once()
        assert "ready" in mock_logger.info.call_args[0][0].lower()


# ── worker_shutdown_handler() ────────────────────────────────────────────


class TestWorkerShutdownHandler:
    @patch("common.utils.redis_cluster_manager.redis_cluster")
    @patch("common.celery_error_handlers.logger")
    def test_logs_shutdown_and_closes_redis(self, mock_logger, mock_redis):
        worker_shutdown_handler()
        mock_logger.warning.assert_called()
        mock_redis.close_connections.assert_called_once()

    @patch("common.celery_error_handlers.logger")
    def test_handles_redis_close_error(self, mock_logger):
        with patch(
            "common.utils.redis_cluster_manager.redis_cluster",
        ) as mock_redis:
            mock_redis.close_connections.side_effect = Exception("conn error")
            worker_shutdown_handler()
            # Should log error but not raise
            mock_logger.error.assert_called()


# ── beat_init_handler() ──────────────────────────────────────────────────


class TestBeatInitHandler:
    @patch("common.celery_error_handlers.logger")
    def test_logs_beat_init(self, mock_logger):
        beat_init_handler(sender=MagicMock())
        mock_logger.info.assert_called_once()
        assert "beat" in mock_logger.info.call_args[0][0].lower()
