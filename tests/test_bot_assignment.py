# tests/test_bot_assignment.py

import pytest
import sys
from unittest.mock import patch, MagicMock
from common.utils.distributed_lock import LockNotAcquired


def _make_bot_config(name, username, max_users=5000, token="tok"):
    """Helper to create a mock bot config object."""
    bot = MagicMock()
    bot.name = name
    bot.username = username
    bot.max_users = max_users
    bot.token = token
    return bot


# Pre-mock the modules that fail to import
# bot_assignment_service imports get_db_session which doesn't exist
_mock_db_database = MagicMock()
sys.modules.setdefault("common.db.database", _mock_db_database)
# Also mock the multibot config
_mock_config_multibot = MagicMock()
sys.modules.setdefault("common.config_multibot", _mock_config_multibot)

# Now import the module under test
from common.services.bot_assignment_service import BotAssignmentService


@pytest.fixture
def mock_multibot():
    """Mock the multibot_config module."""
    with patch("common.services.bot_assignment_service.multibot_config") as mock:
        yield mock


@pytest.fixture
def mock_session():
    """Provide a mock DB session."""
    return MagicMock()


class TestFindAvailableBot:
    """Tests for BotAssignmentService.find_available_bot."""

    def test_returns_least_loaded_bot(self, mock_multibot, mock_session):
        bots = [
            _make_bot_config("orchid", "@hto_de_orchid_bot", max_users=100),
            _make_bot_config("tulip", "@hto_de_tulip_bot", max_users=100),
        ]
        mock_multibot.get_active_bots.return_value = bots

        # Mock get_bot_user_counts to avoid querying User.is_active
        with patch.object(
            BotAssignmentService, "get_bot_user_counts",
            return_value={"orchid": 80, "tulip": 20},
        ):
            result = BotAssignmentService.find_available_bot(mock_session)
        assert result == "tulip"

    def test_all_at_capacity_returns_none(self, mock_multibot, mock_session):
        bots = [_make_bot_config("orchid", "@orchid", max_users=100)]
        mock_multibot.get_active_bots.return_value = bots

        with patch.object(
            BotAssignmentService, "get_bot_user_counts",
            return_value={"orchid": 100},
        ):
            result = BotAssignmentService.find_available_bot(mock_session)
        assert result is None

    def test_no_active_bots_returns_none(self, mock_multibot, mock_session):
        mock_multibot.get_active_bots.return_value = []

        with patch.object(
            BotAssignmentService, "get_bot_user_counts",
            return_value={},
        ):
            result = BotAssignmentService.find_available_bot(mock_session)
        assert result is None


class TestAssignUserToBot:
    """Tests for BotAssignmentService.assign_user_to_bot."""

    @patch("common.services.bot_assignment_service.DistributedLock")
    @patch("common.services.bot_assignment_service.redis_client", create=True)
    def test_assign_success(self, mock_redis, MockLock, mock_multibot, mock_session):
        # Setup lock to succeed
        mock_lock_instance = MagicMock()
        mock_lock_instance.__enter__ = MagicMock(return_value=mock_lock_instance)
        mock_lock_instance.__exit__ = MagicMock(return_value=False)
        MockLock.return_value = mock_lock_instance

        bot_config = _make_bot_config("orchid", "@orchid_bot", token="orchid_token")
        mock_multibot.get_bot_by_name.return_value = bot_config

        with patch.object(
            BotAssignmentService, "find_available_bot", return_value="orchid"
        ):
            mock_user = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = mock_user

            result = BotAssignmentService.assign_user_to_bot(
                mock_session, user_id=1, dispatcher_chat_id="chat_123"
            )

        assert result is not None
        assert result["bot_name"] == "orchid"
        assert result["bot_username"] == "@orchid_bot"

    @patch("common.services.bot_assignment_service.DistributedLock")
    @patch("common.services.bot_assignment_service.redis_client", create=True)
    def test_assign_no_available_bot(self, mock_redis, MockLock, mock_multibot, mock_session):
        mock_lock_instance = MagicMock()
        mock_lock_instance.__enter__ = MagicMock(return_value=mock_lock_instance)
        mock_lock_instance.__exit__ = MagicMock(return_value=False)
        MockLock.return_value = mock_lock_instance

        with patch.object(
            BotAssignmentService, "find_available_bot", return_value=None
        ):
            result = BotAssignmentService.assign_user_to_bot(
                mock_session, user_id=1, dispatcher_chat_id="chat_123"
            )

        assert result is None

    @patch("common.services.bot_assignment_service.DistributedLock")
    @patch("common.services.bot_assignment_service.redis_client", create=True)
    def test_assign_lock_not_acquired(self, mock_redis, MockLock, mock_multibot, mock_session):
        mock_lock_instance = MagicMock()
        mock_lock_instance.__enter__ = MagicMock(side_effect=LockNotAcquired("locked"))
        mock_lock_instance.__exit__ = MagicMock(return_value=False)
        MockLock.return_value = mock_lock_instance

        result = BotAssignmentService.assign_user_to_bot(
            mock_session, user_id=1, dispatcher_chat_id="chat_123"
        )

        assert result is None


class TestGetUserBotAssignment:
    """Tests for BotAssignmentService.get_user_bot_assignment."""

    def test_user_with_assignment(self, mock_multibot, mock_session):
        mock_user = MagicMock()
        mock_user.assigned_bot_name = "tulip"
        mock_user.assigned_bot_username = "@tulip_bot"
        mock_user.assignment_date = "2025-01-01"
        mock_session.query.return_value.filter.return_value.first.return_value = mock_user

        bot_config = _make_bot_config("tulip", "@tulip_bot", token="tulip_token")
        mock_multibot.get_bot_by_name.return_value = bot_config

        result = BotAssignmentService.get_user_bot_assignment(mock_session, "tg_123")
        assert result is not None
        assert result["bot_name"] == "tulip"

    def test_user_without_assignment(self, mock_multibot, mock_session):
        mock_user = MagicMock()
        mock_user.assigned_bot_name = None
        mock_session.query.return_value.filter.return_value.first.return_value = mock_user

        result = BotAssignmentService.get_user_bot_assignment(mock_session, "tg_999")
        assert result is None


class TestGetBotStatistics:
    """Tests for BotAssignmentService.get_bot_statistics."""

    def test_correct_structure(self, mock_multibot, mock_session):
        bots = [
            _make_bot_config("orchid", "@orchid_bot", max_users=1000),
            _make_bot_config("tulip", "@tulip_bot", max_users=1000),
        ]
        mock_multibot.get_active_bots.return_value = bots
        mock_multibot.get_total_capacity.return_value = 2000

        with patch.object(
            BotAssignmentService, "get_bot_user_counts",
            return_value={"orchid": 500, "tulip": 300},
        ):
            stats = BotAssignmentService.get_bot_statistics(mock_session)

        assert stats["total_capacity"] == 2000
        assert stats["total_users"] == 800
        assert len(stats["bots"]) == 2
        assert "overall_utilization" in stats
        assert "utilization" in stats["bots"][0]
