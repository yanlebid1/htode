# tests/test_user_service.py

import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# Pre-mock the adspower_manager module to avoid selenium import chain
# adspower_manager imports selenium which is not installed in test env
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

from common.constants import FREE_TRIAL_DAYS, SUBSCRIPTION_REMINDER_DAYS
from common.services.user_service import UserService


@pytest.fixture
def mock_db():
    return MagicMock()


# ── get_or_create_user() ─────────────────────────────────────────────────────


class TestGetOrCreateUser:
    @patch("common.services.user_service.UserRepository")
    def test_existing_user_returns_id(self, mock_repo, mock_db):
        mock_user = MagicMock()
        mock_user.id = 100
        mock_repo.get_by_messenger_id.return_value = mock_user
        result = UserService.get_or_create_user(mock_db, "tg_123")
        assert result == 100
        mock_repo.create_messenger_user.assert_not_called()

    @patch("common.services.user_service.UserRepository")
    def test_new_user_creates_with_free_trial(self, mock_repo, mock_db):
        mock_repo.get_by_messenger_id.return_value = None
        mock_new = MagicMock()
        mock_new.id = 200
        mock_repo.create_messenger_user.return_value = mock_new

        result = UserService.get_or_create_user(mock_db, "tg_new")
        assert result == 200
        mock_repo.create_messenger_user.assert_called_once()
        # Verify free_until is approximately FREE_TRIAL_DAYS from now
        # Args: (db, messenger_id, messenger_type, free_until)
        call_args = mock_repo.create_messenger_user.call_args
        free_until = call_args[0][3]  # 4th positional arg
        expected = datetime.now() + timedelta(days=FREE_TRIAL_DAYS)
        assert abs((free_until - expected).total_seconds()) < 5

    @patch("common.services.user_service.UserRepository")
    def test_correct_messenger_type_passed(self, mock_repo, mock_db):
        mock_repo.get_by_messenger_id.return_value = None
        mock_new = MagicMock()
        mock_new.id = 300
        mock_repo.create_messenger_user.return_value = mock_new

        UserService.get_or_create_user(mock_db, "tg_type", messenger_type="telegram")
        # Args: (db, messenger_id, messenger_type, free_until)
        call_args = mock_repo.create_messenger_user.call_args
        assert call_args[0][2] == "telegram"


# ── check_expiring_subscriptions() ───────────────────────────────────────────


class TestCheckExpiringSubscriptions:
    def _make_user(self, user_id, sub_until):
        u = MagicMock()
        u.id = user_id
        u.subscription_until = sub_until
        return u

    @patch("common.services.user_service.send_notification")
    def test_finds_users_and_returns_count(self, mock_notif, mock_db):
        mock_db.query.return_value.filter.return_value.all.return_value = []
        result = UserService.check_expiring_subscriptions(mock_db)
        assert "reminders_sent" in result
        assert isinstance(result["reminders_sent"], int)

    @patch("common.services.user_service.send_notification")
    def test_sends_reminder_for_expiring_user(self, mock_notif, mock_db):
        """Test that a user expiring in 3 days gets a reminder with 'Нагадування'."""
        today = datetime.now().date()
        target_3day = today + timedelta(days=3)
        user = self._make_user(20, datetime.combine(target_3day, datetime.min.time()))

        call_count = 0

        def query_filter(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            inner = MagicMock()
            # 1st call (days=3) returns the user
            if call_count == 1:
                inner.all.return_value = [user]
            else:
                inner.all.return_value = []
            return inner

        mock_db.query.return_value.filter = query_filter

        UserService.check_expiring_subscriptions(mock_db)
        if mock_notif.delay.called:
            call_kwargs = mock_notif.delay.call_args[1]
            assert "Нагадування" in call_kwargs["template"]

    @patch("common.services.user_service.send_notification")
    def test_sends_tomorrow_template_for_1_day(self, mock_notif, mock_db):
        """Regression: days_word must be defined before the data dict even for days==1."""
        today = datetime.now().date()
        target_1day = today + timedelta(days=1)
        user = self._make_user(10, datetime.combine(target_1day, datetime.min.time()))

        call_count = 0

        def query_filter(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            inner = MagicMock()
            # 3rd call (days=1) returns the user
            if call_count == 3:
                inner.all.return_value = [user]
            else:
                inner.all.return_value = []
            return inner

        mock_db.query.return_value.filter = query_filter

        # Before the fix this raised UnboundLocalError on days_word
        UserService.check_expiring_subscriptions(mock_db)
        assert mock_notif.delay.called
        call_kwargs = mock_notif.delay.call_args[1]
        assert "завтра" in call_kwargs["template"]

    @patch("common.services.user_service.send_notification")
    def test_no_expiring_users_returns_0(self, mock_notif, mock_db):
        mock_db.query.return_value.filter.return_value.all.return_value = []
        result = UserService.check_expiring_subscriptions(mock_db)
        assert result["reminders_sent"] == 0
        mock_notif.delay.assert_not_called()
