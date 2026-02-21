# tests/test_log_management.py

import logging
import os
import tempfile
import shutil

import pytest
from common.utils.log_management import setup_file_logging, setup_log_aggregation


# ── setup_file_logging() ────────────────────────────────────────────────


class TestSetupFileLogging:
    def test_creates_log_directory(self):
        tmpdir = tempfile.mkdtemp()
        log_dir = os.path.join(tmpdir, "test_logs")
        logger = logging.getLogger("test_file_logging_1")
        logger._service_name = "test_svc"

        try:
            setup_file_logging(logger, log_dir=log_dir)
            assert os.path.isdir(log_dir)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_adds_error_and_general_handlers(self):
        tmpdir = tempfile.mkdtemp()
        logger = logging.getLogger("test_file_logging_2")
        logger._service_name = "test_svc"
        initial_handler_count = len(logger.handlers)

        try:
            setup_file_logging(logger, log_dir=tmpdir)
            # Should add exactly 2 handlers (error + general)
            assert len(logger.handlers) == initial_handler_count + 2
        finally:
            # Clean up handlers to avoid leaks
            for h in logger.handlers[initial_handler_count:]:
                h.close()
                logger.removeHandler(h)
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_error_handler_is_error_level(self):
        tmpdir = tempfile.mkdtemp()
        logger = logging.getLogger("test_file_logging_3")
        logger._service_name = "test_svc"
        initial_count = len(logger.handlers)

        try:
            setup_file_logging(logger, log_dir=tmpdir)
            new_handlers = logger.handlers[initial_count:]
            error_handlers = [h for h in new_handlers if h.level == logging.ERROR]
            assert len(error_handlers) >= 1
        finally:
            for h in logger.handlers[initial_count:]:
                h.close()
                logger.removeHandler(h)
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_uses_service_name_in_filenames(self):
        tmpdir = tempfile.mkdtemp()
        logger = logging.getLogger("test_file_logging_4")
        logger._service_name = "my_service"
        initial_count = len(logger.handlers)

        try:
            setup_file_logging(logger, log_dir=tmpdir)
            files = os.listdir(tmpdir)
            assert any("my_service" in f for f in files)
        finally:
            for h in logger.handlers[initial_count:]:
                h.close()
                logger.removeHandler(h)
            shutil.rmtree(tmpdir, ignore_errors=True)


# ── setup_log_aggregation() ─────────────────────────────────────────────


class TestSetupLogAggregation:
    def test_does_not_raise_for_elk(self):
        logger = logging.getLogger("test_agg_elk")
        setup_log_aggregation(logger, aggregation_backend="elk")

    def test_does_not_raise_for_none(self):
        logger = logging.getLogger("test_agg_none")
        setup_log_aggregation(logger, aggregation_backend=None)
