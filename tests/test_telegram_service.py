# tests/test_telegram_service.py

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from services.telegram_service.app.utils.message_utils import (
    safe_send_message, safe_send_photo, safe_answer_callback_query
)


@pytest.mark.asyncio
async def test_safe_send_message_success():
    """Test that safe_send_message works correctly when API call succeeds."""
    with patch("services.telegram_service.app.bot.bot.send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = MagicMock()

        result = await safe_send_message(
            chat_id=123456789,
            text="Test message"
        )

        assert result is not None
        mock_send.assert_called_once_with(
            chat_id=123456789,
            text="Test message",
            parse_mode=None,
            reply_markup=None,
            disable_web_page_preview=False
        )


@pytest.mark.asyncio
async def test_safe_send_message_retry():
    """Test that safe_send_message retries on transient errors."""
    with patch("services.telegram_service.app.bot.bot.send_message", new_callable=AsyncMock) as mock_send:
        # First call raises error, second succeeds
        mock_send.side_effect = [
            Exception("Network error"),
            MagicMock()
        ]

        result = await safe_send_message(
            chat_id=123456789,
            text="Test message",
            retry_count=2,
            retry_delay=0.1  # Low delay for tests
        )

        assert result is not None


@pytest.mark.asyncio
async def test_safe_send_message_all_retries_fail():
    """Test that safe_send_message returns None when all retries fail."""
    with patch("services.telegram_service.app.bot.bot.send_message", new_callable=AsyncMock) as mock_send:
        # All calls raise exceptions
        mock_send.side_effect = Exception("Network error")

        result = await safe_send_message(
            chat_id=123456789,
            text="Test message",
            retry_count=3,
            retry_delay=0.1  # Low delay for tests
        )

        assert result is None
        assert mock_send.call_count == 3


@pytest.mark.asyncio
async def test_safe_send_photo():
    """Test that safe_send_photo works correctly."""
    with patch("services.telegram_service.app.bot.bot.send_photo", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = MagicMock()

        result = await safe_send_photo(
            chat_id=123456789,
            photo="https://example.com/image.jpg",
            caption="Test caption"
        )

        assert result is not None
        mock_send.assert_called_once_with(
            chat_id=123456789,
            photo="https://example.com/image.jpg",
            caption="Test caption",
            parse_mode=None,
            reply_markup=None
        )


@pytest.mark.asyncio
async def test_safe_answer_callback_query():
    """Test that safe_answer_callback_query works correctly."""
    with patch("services.telegram_service.app.bot.bot.answer_callback_query", new_callable=AsyncMock) as mock_answer:
        mock_answer.return_value = True

        result = await safe_answer_callback_query(
            callback_query_id="test_callback_id",
            text="Test text",
            show_alert=True
        )

        assert result is True
        mock_answer.assert_called_once_with(
            callback_query_id="test_callback_id",
            text="Test text",
            show_alert=True
        )


# Integration tests
@pytest.mark.asyncio
async def test_telegram_handler_start(test_telegram_message):
    """Test the /start command handler."""
    with patch("services.telegram_service.app.utils.message_utils.safe_send_message",
               new_callable=AsyncMock) as mock_send:
        from services.telegram_service.app.handlers.basic_handlers import start_command

        await start_command(test_telegram_message, MagicMock())

        # Verify message was sent
        assert mock_send.called
        # Check that the welcome message was sent
        call_args = mock_send.call_args[1]
        assert "Привіт" in call_args["text"]


@pytest.mark.asyncio
async def test_send_ad_with_extra_buttons():
    """Test the send_ad_with_extra_buttons task."""
    from services.telegram_service.app.tasks import send_ad_with_extra_buttons

    with patch("services.telegram_service.app.tasks.safe_send_photo", new_callable=AsyncMock) as mock_send_photo, \
            patch("services.telegram_service.app.tasks.safe_send_message", new_callable=AsyncMock) as mock_send_message, \
            patch("asyncio.run") as mock_run:
        # Force asyncio.run to just call the coroutine directly
        mock_run.side_effect = lambda coro: asyncio.get_event_loop().run_until_complete(coro)

        # Call the task with test data
        send_ad_with_extra_buttons(
            user_id=123456789,
            text="Test ad text",
            s3_image_url="https://example.com/image.jpg",
            resource_url="https://example.com/ad/123",
            ad_id=1,
            ad_external_id="test_external_id"
        )

        # Verify photo was sent with the correct keyboard
        assert mock_send_photo.called
        call_args = mock_send_photo.call_args[1]
        assert call_args["chat_id"] == 123456789
        assert call_args["photo"] == "https://example.com/image.jpg"
        assert call_args["caption"] == "Test ad text"

        # Verify keyboard has the expected buttons
        keyboard = call_args["reply_markup"]
        assert keyboard is not None
        # Check for button text containing expected strings
        button_texts = [button.text for row in keyboard.inline_keyboard for button in row]
        assert any("фото" in text.lower() for text in button_texts)
        assert any("обран" in text.lower() for text in button_texts)
