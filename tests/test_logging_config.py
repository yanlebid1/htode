# tests/test_logging_config.py

import json
import logging
import io

import pytest
from common.utils.logging_config import (
    JSONFormatter,
    setup_logging,
    log_context,
    log_operation,
    LogAggregator,
)


# ── JSONFormatter ────────────────────────────────────────────────────────


class TestJSONFormatter:
    def test_formats_record_as_json(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello"
        assert parsed["level"] == "INFO"

    def test_includes_timestamp_level_message_service(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="", lineno=0,
            msg="warn msg", args=(), exc_info=None,
        )
        record.service = "my_service"
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "timestamp" in parsed
        assert parsed["level"] == "WARNING"
        assert parsed["message"] == "warn msg"
        assert parsed["service"] == "my_service"

    def test_handles_extra_fields(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="with extras", args=(), exc_info=None,
        )
        record.user_id = 42
        record.action = "login"
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["user_id"] == 42
        assert parsed["action"] == "login"

    def test_handles_exception_info(self):
        formatter = JSONFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=0,
            msg="error occurred", args=(), exc_info=exc_info,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]


# ── setup_logging() ─────────────────────────────────────────────────────


class TestSetupLogging:
    def test_returns_configured_logger(self):
        logger = setup_logging("test_service_1")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_service_1"

    def test_sets_correct_log_level(self):
        logger = setup_logging("test_service_2", log_level="DEBUG")
        assert logger.level == logging.DEBUG

    def test_adds_json_handler_when_json_format(self):
        logger = setup_logging("test_service_3", log_format="json")
        assert len(logger.handlers) >= 1
        assert isinstance(logger.handlers[0].formatter, JSONFormatter)

    def test_adds_text_handler_when_text_format(self):
        logger = setup_logging("test_service_4", log_format="text")
        assert len(logger.handlers) >= 1
        assert not isinstance(logger.handlers[0].formatter, JSONFormatter)


# ── log_context() ────────────────────────────────────────────────────────


class TestLogContext:
    def test_injects_fields_into_log_records(self):
        logger = setup_logging("test_ctx_1", log_format="text")

        with log_context(logger, request_id="abc123"):
            assert logger._context.get("request_id") == "abc123"

    def test_cleans_up_fields_on_exit(self):
        logger = setup_logging("test_ctx_2", log_format="text")
        logger._context = {}

        with log_context(logger, temp_key="value"):
            assert "temp_key" in logger._context

        assert "temp_key" not in logger._context

    def test_handles_nested_contexts(self):
        logger = setup_logging("test_ctx_3", log_format="text")
        logger._context = {}

        with log_context(logger, outer="a"):
            assert logger._context == {"outer": "a"}
            with log_context(logger, inner="b"):
                assert logger._context == {"outer": "a", "inner": "b"}
            # Inner context is cleaned up
            assert logger._context == {"outer": "a"}
        assert logger._context == {}


# ── log_operation() ──────────────────────────────────────────────────────


class TestLogOperation:
    def test_decorator_logs_sync_function(self):
        @log_operation("test_op")
        def add(a, b):
            return a + b

        result = add(2, 3)
        assert result == 5

    @pytest.mark.asyncio
    async def test_decorator_works_with_async_functions(self):
        @log_operation("async_op")
        async def async_add(a, b):
            return a + b

        result = await async_add(2, 3)
        assert result == 5

    def test_decorator_logs_exception_on_failure(self):
        @log_operation("failing_op")
        def fail():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            fail()

    @pytest.mark.asyncio
    async def test_async_decorator_logs_exception_on_failure(self):
        @log_operation("async_fail_op")
        async def async_fail():
            raise ValueError("async boom")

        with pytest.raises(ValueError, match="async boom"):
            await async_fail()


# ── LogAggregator ────────────────────────────────────────────────────────


class TestLogAggregator:
    def test_accumulates_items_and_errors(self):
        logger = setup_logging("test_agg_1", log_format="text")
        agg = LogAggregator(logger, "test_batch")

        agg.add_item({"id": 1}, success=True)
        agg.add_item({"id": 2}, success=False)
        agg.add_error("something failed", {"id": 3})

        assert len(agg.items) == 2
        assert len(agg.errors) == 1

    def test_log_summary_logs_and_resets_not_items(self):
        """log_summary logs the summary; items remain for inspection."""
        logger = setup_logging("test_agg_2", log_format="text")
        agg = LogAggregator(logger, "test_batch")

        agg.add_item({"id": 1}, success=True)
        agg.add_item({"id": 2}, success=True)
        agg.add_error("err1")

        # log_summary should not raise
        agg.log_summary()

        # Items still available (LogAggregator doesn't clear on summary)
        assert len(agg.items) == 2

    def test_tracks_count_correctly(self):
        logger = setup_logging("test_agg_3", log_format="text")
        agg = LogAggregator(logger, "count_op")

        for i in range(10):
            agg.add_item({"idx": i}, success=(i % 3 != 0))

        successful = [it for it in agg.items if it["success"]]
        failed = [it for it in agg.items if not it["success"]]
        assert len(successful) + len(failed) == 10
        # i=0,3,6,9 → 4 failed
        assert len(failed) == 4
        assert len(successful) == 6
