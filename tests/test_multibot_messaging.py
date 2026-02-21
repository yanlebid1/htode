# tests/test_multibot_messaging.py

import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

# Pre-mock telegram_messaging to avoid aiogram v2/v3 import issues
_mock_tg_messaging = MagicMock()
sys.modules.setdefault("common.messaging.telegram_messaging", _mock_tg_messaging)

# Inject get_db_session into common.db.database before multibot_messaging imports it
import common.db.database as _db_mod
if not hasattr(_db_mod, "get_db_session"):
    _db_mod.get_db_session = MagicMock()

import pytest

# Now import the module
import common.messaging.multibot_messaging as _mbm
from common.messaging.multibot_messaging import (
    get_bot_instance,
    MultiBotMessaging,
    _bot_instances,
)


# ── get_bot_instance() ─────────────────────────────────────────────────────


class TestGetBotInstance:
    def setup_method(self):
        _bot_instances.clear()

    @patch.object(_mbm, "multibot_config")
    @patch.object(_mbm, "Bot")
    def test_creates_bot_with_correct_token(self, mock_bot_cls, mock_config):
        bot_cfg = MagicMock()
        bot_cfg.token = "test_token_123"
        mock_config.get_bot_by_name.return_value = bot_cfg
        mock_bot_cls.return_value = MagicMock()

        result = get_bot_instance("orchid")
        mock_bot_cls.assert_called_once_with(token="test_token_123")
        assert result is not None

    @patch.object(_mbm, "multibot_config")
    @patch.object(_mbm, "Bot")
    def test_caches_instances(self, mock_bot_cls, mock_config):
        bot_cfg = MagicMock()
        bot_cfg.token = "tok"
        mock_config.get_bot_by_name.return_value = bot_cfg
        mock_bot_cls.return_value = MagicMock()

        bot1 = get_bot_instance("orchid")
        bot2 = get_bot_instance("orchid")
        # Bot constructor only called once (cached)
        mock_bot_cls.assert_called_once()
        assert bot1 is bot2

    @patch.object(_mbm, "multibot_config")
    def test_returns_none_for_unknown_bot(self, mock_config):
        mock_config.get_bot_by_name.return_value = None
        assert get_bot_instance("nonexistent") is None

    @patch.object(_mbm, "multibot_config")
    @patch.object(_mbm, "Bot")
    def test_handles_bot_creation_error(self, mock_bot_cls, mock_config):
        bot_cfg = MagicMock()
        bot_cfg.token = "bad_token"
        mock_config.get_bot_by_name.return_value = bot_cfg
        mock_bot_cls.side_effect = Exception("Invalid token")

        assert get_bot_instance("broken") is None


# ── MultiBotMessaging.send_to_users() ──────────────────────────────────────


class TestMultiBotMessagingSendToUsers:
    @pytest.mark.asyncio
    @patch.object(_mbm.MultiBotMessaging, "_send_batch_to_bot", new_callable=AsyncMock)
    @patch.object(_mbm, "get_db_session")
    async def test_groups_users_by_assigned_bot(self, mock_get_session, mock_send_batch):
        user1 = MagicMock(id=1, telegram_id=111, assigned_bot_name="orchid")
        user2 = MagicMock(id=2, telegram_id=222, assigned_bot_name="tulip")
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [user1, user2]
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_send_batch.return_value = {"success": 1, "failed": 0}

        result = await MultiBotMessaging.send_to_users([1, 2], "Hello")
        assert mock_send_batch.call_count == 2

    @pytest.mark.asyncio
    @patch.object(_mbm.MultiBotMessaging, "_send_batch_to_bot", new_callable=AsyncMock)
    @patch.object(_mbm, "get_db_session")
    async def test_tracks_success_failed_counts(self, mock_get_session, mock_send_batch):
        user1 = MagicMock(id=1, telegram_id=111, assigned_bot_name="orchid")
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [user1]
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_send_batch.return_value = {"success": 1, "failed": 0}

        result = await MultiBotMessaging.send_to_users([1], "Hello")
        assert result["success"] == 1
        assert result["failed"] == 0

    @pytest.mark.asyncio
    @patch.object(_mbm.MultiBotMessaging, "_send_batch_to_bot", new_callable=AsyncMock)
    @patch.object(_mbm, "get_db_session")
    async def test_handles_send_exception_per_bot(self, mock_get_session, mock_send_batch):
        user1 = MagicMock(id=1, telegram_id=111, assigned_bot_name="orchid")
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [user1]
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_send_batch.side_effect = Exception("Bot offline")

        result = await MultiBotMessaging.send_to_users([1], "Hello")
        assert result["failed"] == 1


# ── MultiBotMessaging._send_batch_to_bot() ─────────────────────────────────


class TestSendBatchToBot:
    @pytest.mark.asyncio
    @patch.object(_mbm, "TelegramMessaging")
    @patch.object(_mbm, "get_bot_instance", return_value=None)
    async def test_returns_all_failed_when_bot_none(self, mock_get_bot, mock_tg):
        users = [{"user_id": 1, "telegram_id": 111}, {"user_id": 2, "telegram_id": 222}]
        result = await MultiBotMessaging._send_batch_to_bot("bad_bot", users, "Hello")
        assert result["success"] == 0
        assert result["failed"] == 2

    @pytest.mark.asyncio
    @patch.object(_mbm, "TelegramMessaging")
    @patch.object(_mbm, "get_bot_instance")
    async def test_handles_individual_send_failures(self, mock_get_bot, mock_tg_cls):
        mock_get_bot.return_value = MagicMock()
        mock_messaging = MagicMock()
        # First send succeeds, second fails
        mock_messaging.send_text = AsyncMock(side_effect=[MagicMock(), Exception("blocked")])
        mock_tg_cls.return_value = mock_messaging

        users = [
            {"user_id": 1, "telegram_id": 111},
            {"user_id": 2, "telegram_id": 222},
        ]
        result = await MultiBotMessaging._send_batch_to_bot("orchid", users, "Hello")
        assert result["success"] == 1
        assert result["failed"] == 1


# ── MultiBotMessaging.send_ad_to_users() ───────────────────────────────────


class TestSendAdToUsers:
    @pytest.mark.asyncio
    @patch.object(_mbm.MultiBotMessaging, "_send_ad_batch_to_bot", new_callable=AsyncMock)
    @patch.object(_mbm, "get_db_session")
    async def test_groups_users_by_bot_and_dispatches(self, mock_get_session, mock_send_batch):
        user1 = MagicMock(id=1, telegram_id=111, assigned_bot_name="orchid")
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [user1]
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_send_batch.return_value = {"success": 1, "failed": 0}

        ad_data = {"id": 42, "price": 5000}
        result = await MultiBotMessaging.send_ad_to_users([1], ad_data, image_url="img.jpg")
        assert result["success"] == 1
        mock_send_batch.assert_called_once()
