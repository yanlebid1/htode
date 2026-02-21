# tests/test_telegram_messaging.py

import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest

# Import real v3 exception classes
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramNotFound,
    TelegramBadRequest,
    TelegramAPIError,
)

# Force-reload the real module in case test_multibot_messaging pre-mocked it
import importlib
sys.modules.pop("common.messaging.telegram_messaging", None)
import common.messaging.telegram_messaging as _tm_mod
importlib.reload(_tm_mod)
from common.messaging.telegram_messaging import TelegramMessaging


def _make_telegram_error(cls, message="test error"):
    """Create a TelegramAPIError subclass instance with required method/message attrs."""
    # aiogram v3 TelegramAPIError requires method and message params
    try:
        return cls(method=MagicMock(), message=message)
    except TypeError:
        return cls(message)


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    return bot


@pytest.fixture
def messenger(mock_bot):
    return TelegramMessaging(mock_bot)


# ── Basic properties ─────────────────────────────────────────────────────


class TestTelegramMessagingProperties:
    def test_platform_name_is_telegram(self, messenger):
        assert messenger.platform_name == "telegram"

    @pytest.mark.asyncio
    async def test_format_user_id_returns_string(self, messenger):
        result = await messenger.format_user_id("123456789")
        assert result == "123456789"

    @pytest.mark.asyncio
    async def test_format_user_id_converts_int_to_string(self, messenger):
        result = await messenger.format_user_id(123456789)
        assert result == "123456789"


# ── send_text() ──────────────────────────────────────────────────────────


class TestSendText:
    @pytest.mark.asyncio
    async def test_sends_message_via_bot(self, messenger, mock_bot):
        mock_result = MagicMock()
        mock_result.message_id = 42
        mock_bot.send_message.return_value = mock_result

        result = await messenger.send_text("123", "Hello!")
        assert result is mock_result
        mock_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_on_bot_blocked(self, messenger, mock_bot):
        mock_bot.send_message.side_effect = _make_telegram_error(
            TelegramForbiddenError, "Forbidden: bot was blocked by the user"
        )
        result = await messenger.send_text("123", "Hello!")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_chat_not_found(self, messenger, mock_bot):
        mock_bot.send_message.side_effect = _make_telegram_error(
            TelegramNotFound, "Not Found: chat not found"
        )
        result = await messenger.send_text("123", "Hello!")
        assert result is None

    @pytest.mark.asyncio
    async def test_passes_reply_markup(self, messenger, mock_bot):
        mock_bot.send_message.return_value = MagicMock(message_id=1)
        markup = MagicMock()
        await messenger.send_text("123", "Text", reply_markup=markup)
        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert call_kwargs["reply_markup"] is markup


# ── send_media() ─────────────────────────────────────────────────────────


class TestSendMedia:
    @pytest.mark.asyncio
    async def test_sends_photo_via_bot(self, messenger, mock_bot):
        mock_result = MagicMock()
        mock_result.message_id = 55
        mock_bot.send_photo.return_value = mock_result

        result = await messenger.send_media("123", "https://cdn.example.com/img.jpg", caption="Photo")
        assert result is mock_result
        mock_bot.send_photo.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_user_id(self, messenger, mock_bot):
        result = await messenger.send_media("", "https://cdn.example.com/img.jpg")
        assert result is None
        mock_bot.send_photo.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_on_bot_blocked(self, messenger, mock_bot):
        mock_bot.send_photo.side_effect = _make_telegram_error(
            TelegramForbiddenError, "Forbidden: bot was blocked by the user"
        )
        result = await messenger.send_media("123", "https://cdn.example.com/img.jpg")
        assert result is None

    @pytest.mark.asyncio
    async def test_falls_back_to_text_on_bad_request_wrong_type(self, messenger, mock_bot):
        mock_bot.send_photo.side_effect = _make_telegram_error(
            TelegramBadRequest, "Wrong type of web page content"
        )
        mock_bot.send_message.return_value = MagicMock(message_id=66)

        result = await messenger.send_media(
            "123", "https://cdn.example.com/img.jpg", caption="Photo"
        )
        # Falls back to send_message
        mock_bot.send_message.assert_called_once()
        assert result is not None


# ── send_menu() ──────────────────────────────────────────────────────────


class TestSendMenu:
    @pytest.mark.asyncio
    @patch("common.messaging.telegram_messaging.InlineKeyboardMarkup")
    @patch("common.messaging.telegram_messaging.InlineKeyboardButton")
    async def test_sends_text_with_keyboard(self, mock_btn, mock_kb, messenger, mock_bot):
        mock_bot.send_message.return_value = MagicMock(message_id=77)

        options = [
            {"text": "Option A", "value": "a"},
            {"text": "Option B", "value": "b"},
        ]
        result = await messenger.send_menu("123", "Choose:", options)
        assert result is not None
        mock_bot.send_message.assert_called_once()
        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert call_kwargs["reply_markup"] is not None


# ── send_ad() ────────────────────────────────────────────────────────────


class TestSendAd:
    @pytest.mark.asyncio
    @patch("common.config.build_ad_text", return_value="Ad text")
    @patch("common.messaging.telegram_messaging.InlineKeyboardMarkup")
    @patch("common.messaging.telegram_messaging.InlineKeyboardButton")
    @patch("common.messaging.telegram_messaging.WebAppInfo")
    async def test_sends_ad_with_image(self, mock_wai, mock_btn, mock_kb, mock_build, messenger, mock_bot):
        mock_bot.send_photo.return_value = MagicMock(message_id=88)

        ad_data = {"id": 1, "resource_url": "https://example.com/ad/1"}
        result = await messenger.send_ad(
            "123", ad_data, image_url="https://cdn.example.com/img.jpg"
        )
        assert result is not None
        mock_bot.send_photo.assert_called_once()

    @pytest.mark.asyncio
    @patch("common.config.build_ad_text", return_value="Ad text")
    @patch("common.messaging.telegram_messaging.InlineKeyboardMarkup")
    @patch("common.messaging.telegram_messaging.InlineKeyboardButton")
    @patch("common.messaging.telegram_messaging.WebAppInfo")
    async def test_sends_ad_without_image_as_text(self, mock_wai, mock_btn, mock_kb, mock_build, messenger, mock_bot):
        mock_bot.send_message.return_value = MagicMock(message_id=99)

        ad_data = {"id": 2, "resource_url": "https://example.com/ad/2"}
        result = await messenger.send_ad("123", ad_data, image_url=None)
        assert result is not None
        mock_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    @patch("common.config.build_ad_text", return_value="Ad text")
    @patch("common.messaging.telegram_messaging.InlineKeyboardMarkup")
    @patch("common.messaging.telegram_messaging.InlineKeyboardButton")
    @patch("common.messaging.telegram_messaging.WebAppInfo")
    async def test_sends_ad_with_images_and_phones(self, mock_wai, mock_btn, mock_kb, mock_build, messenger, mock_bot):
        mock_bot.send_photo.return_value = MagicMock(message_id=100)

        ad_data = {
            "id": 3,
            "resource_url": "https://example.com/ad/3",
            "images": ["img1.jpg", "img2.jpg"],
            "phones": ["+380501234567"],
        }
        result = await messenger.send_ad(
            "123", ad_data, image_url="https://cdn.example.com/img.jpg"
        )
        assert result is not None
        # Should create gallery and phone buttons
        assert mock_wai.call_count >= 1


# ── create_keyboard() ───────────────────────────────────────────────────


class TestCreateKeyboard:
    @patch("common.messaging.telegram_messaging.InlineKeyboardMarkup")
    @patch("common.messaging.telegram_messaging.InlineKeyboardButton")
    def test_creates_keyboard_with_callback_buttons(self, mock_btn, mock_kb):
        options = [
            {"text": "A", "value": "callback_a"},
            {"text": "B", "value": "callback_b"},
        ]
        keyboard = TelegramMessaging.create_keyboard(options)
        assert mock_kb.called
        assert mock_btn.call_count == 2

    @patch("common.messaging.telegram_messaging.InlineKeyboardMarkup")
    @patch("common.messaging.telegram_messaging.InlineKeyboardButton")
    def test_creates_keyboard_with_url_button(self, mock_btn, mock_kb):
        options = [{"text": "Visit", "url": "https://example.com"}]
        keyboard = TelegramMessaging.create_keyboard(options)
        mock_btn.assert_called_once_with(text="Visit", url="https://example.com")

    @patch("common.messaging.telegram_messaging.InlineKeyboardMarkup")
    @patch("common.messaging.telegram_messaging.InlineKeyboardButton")
    @patch("common.messaging.telegram_messaging.WebAppInfo")
    def test_creates_keyboard_with_webapp_button(self, mock_wai, mock_btn, mock_kb):
        options = [{"text": "Open App", "web_app": "https://app.example.com"}]
        keyboard = TelegramMessaging.create_keyboard(options)
        mock_wai.assert_called_once_with(url="https://app.example.com")
