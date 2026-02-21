# tests/test_task_versioning.py

import sys
from unittest.mock import patch, MagicMock
from datetime import timedelta

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from common.utils.task_versioning import (
    TaskVersionManager,
    DeploymentConfig,
    migrate_task_data,
    get_deployment_status,
    safe_task_transition,
    version_manager,
)


# ── TaskVersionManager ─────────────────────────────────────────────────────


class TestTaskVersionManager:
    def test_register_version(self):
        mgr = TaskVersionManager()
        handler = MagicMock()
        mgr.register_version("my_task", "v1", handler)
        assert "my_task" in mgr.versions
        assert mgr.versions["my_task"]["v1"] is handler

    def test_register_creates_task_name_entry(self):
        mgr = TaskVersionManager()
        mgr.register_version("new_task", "v2", MagicMock())
        assert "new_task" in mgr.versions

    def test_get_handler_specific_version(self):
        mgr = TaskVersionManager()
        handler_v1 = MagicMock()
        handler_v2 = MagicMock()
        mgr.register_version("task", "v1", handler_v1)
        mgr.register_version("task", "v2", handler_v2)

        result = mgr.get_handler("task", version="v2")
        assert result is handler_v2

    def test_get_handler_default_from_rollout_config(self):
        mgr = TaskVersionManager()
        handler_v1 = MagicMock()
        handler_v2 = MagicMock()
        mgr.register_version("task", "v1", handler_v1)
        mgr.register_version("task", "v2", handler_v2)
        mgr.set_rollout("task", {"default_version": "v2", "canary_enabled": False})

        result = mgr.get_handler("task")
        assert result is handler_v2

    @patch("random.randint", return_value=5)
    def test_get_handler_canary_version(self, mock_rand):
        mgr = TaskVersionManager()
        handler_v1 = MagicMock()
        handler_v2 = MagicMock()
        mgr.register_version("task", "v1", handler_v1)
        mgr.register_version("task", "v2", handler_v2)
        mgr.set_rollout("task", {
            "canary_enabled": True,
            "canary_version": "v2",
            "canary_percentage": 10,
            "default_version": "v1",
        })

        # random.randint returns 5, which is <= 10 → canary
        result = mgr.get_handler("task")
        assert result is handler_v2

    @patch("random.randint", return_value=50)
    def test_get_handler_returns_default_when_canary_not_hit(self, mock_rand):
        mgr = TaskVersionManager()
        handler_v1 = MagicMock()
        handler_v2 = MagicMock()
        mgr.register_version("task", "v1", handler_v1)
        mgr.register_version("task", "v2", handler_v2)
        mgr.set_rollout("task", {
            "canary_enabled": True,
            "canary_version": "v2",
            "canary_percentage": 10,
            "default_version": "v1",
        })

        # random.randint returns 50, which is > 10 → default
        result = mgr.get_handler("task")
        assert result is handler_v1

    def test_get_handler_unregistered_task(self):
        mgr = TaskVersionManager()
        with pytest.raises(KeyError):
            mgr.get_handler("nonexistent")


# ── DeploymentConfig ───────────────────────────────────────────────────────


class TestDeploymentConfig:
    def test_enable_canary(self):
        mgr = TaskVersionManager()
        # Temporarily replace global
        original = version_manager.rollout_config
        with patch.object(version_manager, "rollout_config", {}):
            with patch.object(version_manager, "set_rollout") as mock_set:
                DeploymentConfig.enable_canary("task", "v2", percentage=15)
                config = mock_set.call_args[0][1]
                assert config["canary_enabled"] is True
                assert config["canary_version"] == "v2"
                assert config["canary_percentage"] == 15

    def test_increase_canary(self):
        mgr = TaskVersionManager()
        with patch.object(version_manager, "rollout_config", {
            "task": {"canary_enabled": True, "canary_percentage": 10}
        }):
            with patch.object(version_manager, "set_rollout") as mock_set:
                DeploymentConfig.increase_canary("task", 50)
                config = mock_set.call_args[0][1]
                assert config["canary_percentage"] == 50

    def test_promote_version(self):
        with patch.object(version_manager, "set_rollout") as mock_set:
            DeploymentConfig.promote_version("task", "v2")
            config = mock_set.call_args[0][1]
            assert config["default_version"] == "v2"
            assert config["canary_enabled"] is False

    def test_rollback(self):
        with patch.object(version_manager, "set_rollout") as mock_set:
            DeploymentConfig.rollback("task", "v1")
            config = mock_set.call_args[0][1]
            assert config["default_version"] == "v1"
            assert config["canary_enabled"] is False


# ── migrate_task_data() ────────────────────────────────────────────────────


class TestMigrateTaskData:
    def test_v1_to_v2_adds_extraction_enabled(self):
        data = {"ad_id": 1, "price": 5000}
        result = migrate_task_data(data, "v1", "v2")
        assert result["extraction_enabled"] is True
        assert result["ad_id"] == 1

    def test_v2_to_v1_removes_extraction_enabled(self):
        data = {"ad_id": 1, "extraction_enabled": True}
        result = migrate_task_data(data, "v2", "v1")
        assert "extraction_enabled" not in result
        assert result["ad_id"] == 1

    def test_unknown_migration_returns_data_unchanged(self):
        data = {"ad_id": 1}
        result = migrate_task_data(data, "v3", "v4")
        assert result == data


# ── get_deployment_status() ────────────────────────────────────────────────


class TestGetDeploymentStatus:
    def test_returns_status_for_registered_tasks(self):
        # Use the global version_manager which has tasks registered at import time
        status = get_deployment_status()
        # At minimum, the module registers extract_phones_for_ad and notify_user_batch
        assert isinstance(status, dict)
        # Check structure of any entry
        for task_name, info in status.items():
            assert "default_version" in info
            assert "canary_enabled" in info
            assert "available_versions" in info


# ── safe_task_transition() ─────────────────────────────────────────────────


class TestSafeTaskTransition:
    @patch.object(DeploymentConfig, "enable_canary")
    def test_enables_canary_at_first_step(self, mock_enable):
        result = safe_task_transition("task", "v2")
        mock_enable.assert_called_once_with("task", "v2", 10)

    @patch.object(DeploymentConfig, "enable_canary")
    def test_returns_deployment_plan(self, mock_enable):
        result = safe_task_transition("task", "v2", canary_steps=[5, 20, 50, 100])
        assert result["task_name"] == "task"
        assert result["new_version"] == "v2"
        assert result["steps"] == [5, 20, 50, 100]
        assert "started_at" in result

    @patch.object(DeploymentConfig, "enable_canary")
    def test_default_canary_steps(self, mock_enable):
        result = safe_task_transition("task", "v3")
        assert result["steps"] == [10, 25, 50, 100]
