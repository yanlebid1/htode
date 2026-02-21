# tests/test_task_registry.py

import sys
from unittest.mock import patch, MagicMock

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest

# We need to import after the adspower mock is in place
import common.messaging.task_registry as task_registry_module
from common.messaging.task_registry import register_platform_tasks, task_mappings


# ── register_platform_tasks() ────────────────────────────────────────────


class TestRegisterPlatformTasks:
    def setup_method(self):
        """Clear task_mappings before each test."""
        task_mappings.clear()

    @patch("common.messaging.task_registry.celery_app")
    @patch("common.messaging.tasks.send_ad_with_extra_buttons", create=True)
    @patch("common.messaging.tasks.send_subscription_notification", create=True)
    def test_returns_dict_with_registered_tasks(self, mock_send_notif, mock_send_ad, mock_celery):
        # Make celery_app.task return a passthrough decorator
        mock_celery.task = MagicMock(side_effect=lambda **kw: lambda f: f)

        result = register_platform_tasks("telegram", "telegram_service.app.tasks")
        assert isinstance(result, dict)
        assert "send_ad_with_extra_buttons" in result
        assert "send_subscription_notification" in result

    @patch("common.messaging.task_registry.celery_app")
    @patch("common.messaging.tasks.send_ad_with_extra_buttons", create=True)
    @patch("common.messaging.tasks.send_subscription_notification", create=True)
    def test_registers_send_ad_and_send_notification(self, mock_send_notif, mock_send_ad, mock_celery):
        mock_celery.task = MagicMock(side_effect=lambda **kw: lambda f: f)

        result = register_platform_tasks("telegram", "telegram_service.app.tasks")
        assert "send_ad_with_extra_buttons" in result
        assert "send_subscription_notification" in result

    @patch("common.messaging.task_registry.celery_app")
    @patch("common.messaging.tasks.send_ad_with_extra_buttons", create=True)
    @patch("common.messaging.tasks.send_subscription_notification", create=True)
    def test_uses_correct_task_name_format(self, mock_send_notif, mock_send_ad, mock_celery):
        task_names_registered = []
        mock_celery.task = MagicMock(
            side_effect=lambda **kw: (task_names_registered.append(kw.get("name")), lambda f: f)[1]
        )

        register_platform_tasks("telegram", "telegram_service.app.tasks")
        assert "telegram_service.app.tasks.send_ad_with_extra_buttons" in task_names_registered
        assert "telegram_service.app.tasks.send_subscription_notification" in task_names_registered

    @patch("common.messaging.task_registry.celery_app")
    @patch("common.messaging.tasks.send_ad_with_extra_buttons", create=True)
    @patch("common.messaging.tasks.send_subscription_notification", create=True)
    def test_stores_in_global_task_mappings(self, mock_send_notif, mock_send_ad, mock_celery):
        mock_celery.task = MagicMock(side_effect=lambda **kw: lambda f: f)

        register_platform_tasks("telegram", "telegram_service.app.tasks")
        assert "telegram_service.app.tasks.send_ad_with_extra_buttons" in task_mappings
        assert "telegram_service.app.tasks.send_subscription_notification" in task_mappings

    def test_handles_import_error_gracefully(self):
        with patch(
            "common.messaging.task_registry.celery_app"
        ), patch.dict(sys.modules, {"common.messaging.tasks": None}):
            # Importing from a None module entry raises ImportError
            result = register_platform_tasks("bad_platform", "bad.module.path")
            assert result == {}

    @patch("common.messaging.task_registry.celery_app")
    @patch("common.messaging.tasks.send_ad_with_extra_buttons", create=True)
    @patch("common.messaging.tasks.send_subscription_notification", create=True)
    def test_handles_generic_exception_gracefully(self, mock_send_notif, mock_send_ad, mock_celery):
        mock_celery.task = MagicMock(side_effect=RuntimeError("unexpected"))

        result = register_platform_tasks("telegram", "telegram_service.app.tasks")
        assert result == {}

    @patch("common.messaging.task_registry.celery_app")
    @patch("common.messaging.tasks.send_ad_with_extra_buttons", create=True)
    @patch("common.messaging.tasks.send_subscription_notification", create=True)
    def test_multiple_platforms_dont_conflict(self, mock_send_notif, mock_send_ad, mock_celery):
        mock_celery.task = MagicMock(side_effect=lambda **kw: lambda f: f)

        r1 = register_platform_tasks("telegram", "telegram_service.app.tasks")
        r2 = register_platform_tasks("viber", "viber_service.app.tasks")

        assert len(r1) == 2
        assert len(r2) == 2
        # All 4 entries in global mappings
        assert len(task_mappings) == 4

    @patch("common.messaging.task_registry.celery_app")
    @patch("common.messaging.tasks.send_ad_with_extra_buttons", create=True)
    @patch("common.messaging.tasks.send_subscription_notification", create=True)
    def test_registered_tasks_are_callable(self, mock_send_notif, mock_send_ad, mock_celery):
        mock_celery.task = MagicMock(side_effect=lambda **kw: lambda f: f)

        result = register_platform_tasks("telegram", "telegram_service.app.tasks")
        for task_func in result.values():
            assert callable(task_func)
