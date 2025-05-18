# services/telegram_service/app/utils/message_utils.py

from typing import Optional, Union
from aiogram.types import Message, InputFile

from common.messaging.unified_platform_utils import (
    safe_send_message as unified_send_message,
    safe_send_media as unified_send_media,
    safe_edit_message_telegram,
    safe_answer_callback_query_telegram,
    delete_message_safe_telegram
)

# Import service logger and logging utilities
from .. import logger
from common.utils.logging_config import log_operation, log_context


# Re-export the centralized utilities with Telegram-specific defaults
@log_operation("telegram_safe_send_message")
async def safe_send_message(
        chat_id: Union[int, str],
        text: str,
        **kwargs
) -> Optional[Message]:
    """
    Telegram-specific function to send text messages directly through the bot.
    Bypasses the unified messaging infrastructure to avoid user resolution issues.

    Args:
        chat_id: Telegram chat ID
        text: Message text
        **kwargs: Additional parameters

    Returns:
        The message object or None if failed
    """
    with log_context(logger, chat_id=chat_id, text_length=len(text)):
        logger.debug("Sending message directly through Telegram bot", extra={
            "chat_id": chat_id,
            "text_length": len(text),
            "kwargs_keys": list(kwargs.keys())
        })

        from ..bot import bot
        try:
            return await bot.send_message(
                chat_id=chat_id,
                text=text,
                **kwargs
            )
        except Exception as e:
            logger.error("Error sending message", exc_info=True, extra={
                "chat_id": chat_id,
                "error": str(e)
            })
            return None


@log_operation("telegram_safe_send_photo")
async def safe_send_photo(
        chat_id: Union[int, str],
        photo: Union[str, InputFile],
        caption: Optional[str] = None,
        **kwargs
) -> Optional[Message]:
    """
    Telegram-specific wrapper for sending photos directly through the bot.
    Bypasses the unified messaging infrastructure to avoid user resolution issues.

    Args:
        chat_id: Telegram chat ID
        photo: Photo URL or InputFile
        caption: Optional photo caption
        **kwargs: Additional parameters

    Returns:
        The message object or None if failed
    """
    with log_context(logger, chat_id=chat_id, photo_type=type(photo).__name__):
        # Always use the bot directly
        from ..bot import bot
        try:
            logger.debug("Sending photo via direct bot method", extra={
                "chat_id": chat_id,
                "photo_type": type(photo).__name__,
                "has_caption": bool(caption)
            })
            return await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                **kwargs
            )
        except Exception as e:
            logger.error("Error sending photo", exc_info=True, extra={
                "chat_id": chat_id,
                "error": str(e)
            })
            return None


# Re-export other utility functions
async def safe_edit_message(
        chat_id: Union[int, str],
        message_id: int,
        text: str,
        **kwargs
) -> Optional[Message]:
    """Telegram-specific wrapper for edit_message utility."""
    with log_context(logger, chat_id=chat_id, message_id=message_id):
        logger.debug("Editing message", extra={
            "chat_id": chat_id,
            "message_id": message_id,
            "text_length": len(text)
        })
        return await safe_edit_message_telegram(chat_id, message_id, text, **kwargs)


async def safe_answer_callback_query(
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False
) -> bool:
    """Telegram-specific wrapper for answer_callback_query utility."""
    with log_context(logger, callback_query_id=callback_query_id):
        logger.debug("Answering callback query", extra={
            "callback_query_id": callback_query_id,
            "has_text": bool(text),
            "show_alert": show_alert
        })
        return await safe_answer_callback_query_telegram(callback_query_id, text, show_alert)


async def delete_message_safe(
        chat_id: Union[int, str],
        message_id: int
) -> bool:
    """Telegram-specific wrapper for delete_message utility."""
    with log_context(logger, chat_id=chat_id, message_id=message_id):
        logger.debug("Deleting message", extra={
            "chat_id": chat_id,
            "message_id": message_id
        })
        return await delete_message_safe_telegram(chat_id, message_id)