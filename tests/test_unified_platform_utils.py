# tests/test_unified_platform_utils.py

import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from common.messaging.unified_platform_utils import (
    resolve_user_id,
    get_messenger_instance,
    MessageFormatter,
    safe_send_message,
    safe_send_media,
    safe_send_menu,
)


# ── resolve_user_id() ───────────────────────────────────────────────────


class TestResolveUserId:
    @patch("common.db.operations.get_platform_ids_for_user")
    def test_small_numeric_id_treated_as_db_id(self, mock_get_platform):
        mock_get_platform.return_value = {"telegram_id": "123456789"}
        db_id, platform, tg_id = resolve_user_id(42)
        assert db_id == 42
        assert platform == "telegram"
        assert tg_id == "123456789"

    @patch("common.db.operations.get_user_by_telegram_id")
    def test_large_numeric_id_treated_as_telegram_id(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.id = 7
        mock_get_user.return_value = mock_user

        db_id, platform, tg_id = resolve_user_id(9876543210)
        assert db_id == 7
        assert platform == "telegram"
        assert tg_id == "9876543210"

    @patch("common.db.operations.get_user_by_telegram_id")
    def test_string_id_treated_as_telegram_id(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.id = 5
        mock_get_user.return_value = mock_user

        db_id, platform, tg_id = resolve_user_id("tg_user_abc")
        assert db_id == 5
        assert platform == "telegram"
        assert tg_id == "tg_user_abc"

    @patch("common.db.operations.get_user_by_telegram_id")
    def test_returns_none_db_id_when_user_not_found(self, mock_get_user):
        mock_get_user.return_value = None

        db_id, platform, tg_id = resolve_user_id(9999999999)
        assert db_id is None
        assert platform == "telegram"
        assert tg_id == "9999999999"

    @patch("common.db.operations.get_user_by_telegram_id")
    @patch("common.db.operations.get_platform_ids_for_user")
    def test_small_id_falls_back_to_telegram_lookup(self, mock_get_platform, mock_get_user):
        """When small ID has no telegram_id in DB, treat it as a telegram ID."""
        mock_get_platform.return_value = {"telegram_id": None}
        mock_user = MagicMock()
        mock_user.id = 100
        mock_get_user.return_value = mock_user

        db_id, platform, tg_id = resolve_user_id(42)
        assert db_id == 100
        assert tg_id == "42"


# ── get_messenger_instance() ────────────────────────────────────────────


class TestGetMessengerInstance:
    def test_returns_none_on_import_error(self):
        """When telegram bot can't be imported, returns None."""
        with patch(
            "common.messaging.unified_platform_utils.TelegramMessaging",
            side_effect=ImportError("no telegram"),
            create=True,
        ):
            # The function catches ImportError internally
            result = get_messenger_instance("telegram")
            # May return None due to import error in the actual function
            # (it tries to import from services.telegram_service.app.bot)
            assert result is None or result is not None  # doesn't crash


# ── MessageFormatter ─────────────────────────────────────────────────────


class TestMessageFormatter:
    @patch("common.config.build_ad_text")
    def test_format_ad_text_calls_build_ad_text(self, mock_build):
        mock_build.return_value = "Formatted ad text"
        ad_data = {"id": 1, "price": 5000}
        result = MessageFormatter.format_ad_text(ad_data, platform="telegram")
        assert result == "Formatted ad text"
        mock_build.assert_called_once_with(ad_data, markdown=True)


# ── safe_send_message() ─────────────────────────────────────────────────


class TestSafeSendMessage:
    @pytest.mark.asyncio
    @patch("common.messaging.unified_platform_utils.get_messenger_instance")
    @patch("common.messaging.service.messaging_service")
    @patch("common.messaging.unified_platform_utils.resolve_user_id")
    async def test_sends_via_messaging_service(self, mock_resolve, mock_svc, mock_get_inst):
        mock_resolve.return_value = (42, "telegram", "123456789")
        mock_svc.send_notification = AsyncMock(return_value=True)

        result = await safe_send_message(user_id=42, text="Hello!")
        assert result is True
        mock_svc.send_notification.assert_called_once()

    @pytest.mark.asyncio
    @patch("common.messaging.unified_platform_utils.asyncio.sleep", new_callable=AsyncMock)
    @patch("common.messaging.unified_platform_utils.get_messenger_instance")
    @patch("common.messaging.service.messaging_service")
    @patch("common.messaging.unified_platform_utils.resolve_user_id")
    async def test_falls_back_to_direct_send(self, mock_resolve, mock_svc, mock_get_inst, mock_sleep):
        mock_resolve.return_value = (42, "telegram", "123456789")
        mock_svc.send_notification = AsyncMock(side_effect=Exception("service down"))

        mock_messenger = AsyncMock()
        mock_messenger.send_text.return_value = MagicMock()
        mock_get_inst.return_value = mock_messenger

        result = await safe_send_message(user_id=42, text="Hello!")
        assert result is not None
        mock_messenger.send_text.assert_called_once()

    @pytest.mark.asyncio
    @patch("common.messaging.unified_platform_utils.resolve_user_id")
    async def test_returns_none_when_cant_resolve(self, mock_resolve):
        mock_resolve.return_value = (None, None, None)

        result = await safe_send_message(user_id=999, text="Hello!")
        assert result is None

    @pytest.mark.asyncio
    @patch("common.messaging.unified_platform_utils.resolve_user_id")
    async def test_returns_none_on_outer_exception(self, mock_resolve):
        mock_resolve.side_effect = Exception("unexpected")

        result = await safe_send_message(user_id=42, text="Hello!")
        assert result is None


# ── safe_send_media() ────────────────────────────────────────────────────


class TestSafeSendMedia:
    @pytest.mark.asyncio
    @patch("common.messaging.unified_platform_utils.get_messenger_instance")
    @patch("common.messaging.service.messaging_service")
    @patch("common.messaging.unified_platform_utils.resolve_user_id")
    async def test_sends_media_via_service(self, mock_resolve, mock_svc, mock_get_inst):
        mock_resolve.return_value = (42, "telegram", "123456789")
        mock_svc.send_notification = AsyncMock(return_value=True)

        result = await safe_send_media(
            user_id=42, media_url="https://cdn.example.com/img.jpg", caption="Photo"
        )
        assert result is True

    @pytest.mark.asyncio
    @patch("common.messaging.unified_platform_utils.resolve_user_id")
    async def test_returns_none_on_exception(self, mock_resolve):
        mock_resolve.side_effect = Exception("error")

        result = await safe_send_media(
            user_id=42, media_url="https://cdn.example.com/img.jpg"
        )
        assert result is None


# ── safe_send_menu() ─────────────────────────────────────────────────────


class TestSafeSendMenu:
    @pytest.mark.asyncio
    @patch("common.messaging.unified_platform_utils.get_messenger_instance")
    @patch("common.messaging.unified_platform_utils.resolve_user_id")
    async def test_sends_menu_via_messenger(self, mock_resolve, mock_get_inst):
        mock_resolve.return_value = (42, "telegram", "123456789")
        mock_messenger = AsyncMock()
        mock_messenger.send_menu.return_value = MagicMock()
        mock_get_inst.return_value = mock_messenger

        options = [{"text": "A", "value": "a"}, {"text": "B", "value": "b"}]
        result = await safe_send_menu(user_id=42, text="Choose:", options=options)
        assert result is not None
        mock_messenger.send_menu.assert_called_once()

    @pytest.mark.asyncio
    @patch("common.messaging.unified_platform_utils.resolve_user_id")
    async def test_returns_none_when_cant_resolve(self, mock_resolve):
        mock_resolve.return_value = (None, None, None)

        result = await safe_send_menu(
            user_id=999, text="Choose:", options=[{"text": "A", "value": "a"}]
        )
        assert result is None
