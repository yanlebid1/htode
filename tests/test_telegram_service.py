# tests/test_telegram_service.py

import pytest
import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Mock the bot module to avoid aiogram.contrib import error
_mock_bot = AsyncMock()
_mock_bot_module = MagicMock()
_mock_bot_module.bot = _mock_bot
sys.modules.setdefault("services.telegram_service.app.bot", _mock_bot_module)

from services.telegram_service.app.utils.message_utils import (
    safe_send_message,
    safe_send_photo,
    safe_answer_callback_query,
)


async def test_safe_send_message_success():
    """Test that safe_send_message works correctly when API call succeeds."""
    _mock_bot.send_message = AsyncMock(return_value=MagicMock())

    result = await safe_send_message(chat_id=123456789, text="Test message")

    assert result is not None
    _mock_bot.send_message.assert_called_once_with(
        chat_id=123456789, text="Test message"
    )


async def test_safe_send_message_failure_returns_none():
    """Test that safe_send_message returns None on error."""
    _mock_bot.send_message = AsyncMock(side_effect=Exception("Network error"))

    result = await safe_send_message(chat_id=123456789, text="Test message")

    assert result is None


async def test_safe_send_photo_success():
    """Test that safe_send_photo sends photo when image is valid."""
    _mock_bot.send_photo = AsyncMock(return_value=MagicMock())

    with patch(
        "services.telegram_service.app.utils.message_utils.async_process_image_url",
        new_callable=AsyncMock,
        return_value="https://example.com/image.jpg",
    ):
        result = await safe_send_photo(
            chat_id=123456789,
            photo="https://example.com/image.jpg",
            caption="Test caption",
        )

    assert result is not None


async def test_safe_send_photo_fallback_on_invalid_image():
    """Test that safe_send_photo falls back to text when image processing fails."""
    _mock_bot.send_message = AsyncMock(return_value=MagicMock())

    with patch(
        "services.telegram_service.app.utils.message_utils.async_process_image_url",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await safe_send_photo(
            chat_id=123456789,
            photo="https://example.com/bad.webp",
            caption="Test caption",
        )

    # Should fallback to safe_send_message with link
    assert _mock_bot.send_message.called


async def test_safe_answer_callback_query():
    """Test that safe_answer_callback_query delegates correctly."""
    with patch(
        "services.telegram_service.app.utils.message_utils.safe_answer_callback_query_telegram",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_answer:
        result = await safe_answer_callback_query(
            callback_query_id="test_callback_id", text="Test text", show_alert=True
        )

        assert result is True
        mock_answer.assert_called_once_with("test_callback_id", "Test text", True)
