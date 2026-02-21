# common/messaging/unified_platform_utils.py

import asyncio
import random
from typing import Dict, Any, Optional, Tuple, Union, List
from common.utils.logging_config import log_operation, log_context

# Import the messaging logger
from . import logger


# ===== Platform Detection and Resolution =====


@log_operation("resolve_user_id")
def resolve_user_id(
    user_id: Union[int, str], *_ignored, **_kw
) -> Tuple[Optional[int], str, str]:
    """Simplified Telegram-only resolver.

    Returns (db_user_id, "telegram", telegram_id).
    If the incoming ID is already the Telegram ID (string, not purely digits) we look up DB id.
    If it looks like a DB id (int or numeric str) we fetch the user's telegram_id.
    """
    from common.db.operations import get_user_by_telegram_id, get_platform_ids_for_user

    with log_context(logger, user_id=str(user_id)[:20]):
        # Heuristic:
        # 1) If the ID is small (likely auto-increment DB id) treat as DB id.
        # 2) If it is large (e.g., typical Telegram chat IDs are > 1e9) treat as telegram id directly.
        # 3) As a fallback, attempt DB lookup – if the user exists by DB id, keep it, otherwise
        #    treat the numeric value as a telegram id.

        # Numeric? could be DB id or telegram id
        if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()):
            numeric_id = int(user_id)

            # Threshold to distinguish DB id vs telegram id (DB ids are usually small)
            DB_ID_THRESHOLD = 1_000_000_000  # adjust if your DB ids can exceed this

            if numeric_id < DB_ID_THRESHOLD:
                # Treat as DB id first
                db_user_id = numeric_id
                platform_ids = get_platform_ids_for_user(db_user_id)

                # If we didn't find a telegram_id in DB, fall back to treating numeric_id as telegram_id
                if not platform_ids.get("telegram_id"):
                    # The numeric value is actually a telegram id
                    user = get_user_by_telegram_id(str(numeric_id))
                    db_user_id = user.id if user else None
                    return db_user_id, "telegram", str(numeric_id)

                telegram_id = str(platform_ids.get("telegram_id"))
                return db_user_id, "telegram", telegram_id

            # Large number – more likely a telegram id directly
            telegram_id = str(numeric_id)
            user = get_user_by_telegram_id(telegram_id)
            db_user_id = user.id if user else None
            return db_user_id, "telegram", telegram_id

        # Otherwise assume it is a telegram id string
        telegram_id = str(user_id)
        user = get_user_by_telegram_id(telegram_id)
        db_user_id = user.id if user else None
        return db_user_id, "telegram", telegram_id


@log_operation("get_messenger_for_user")
async def get_messenger_for_user(
    user_id: Union[int, str]
) -> Tuple[Optional[str], Optional[str], Optional[Any]]:
    """
    Determine the messenger type and platform-specific ID for a user.
    Can handle either database user ID or platform-specific ID.

    Args:
        user_id: Database user ID or platform-specific ID

    Returns:
        Tuple of (platform_name, platform_id, messenger_instance)
    """
    with log_context(logger, user_id=str(user_id)[:20]):
        db_user_id, platform_name, platform_id = resolve_user_id(user_id)

        if platform_name and platform_id:
            messenger = get_messenger_instance(platform_name)
            logger.info(
                "Found messenger for user",
                extra={"platform": platform_name, "has_messenger": bool(messenger)},
            )
            return platform_name, platform_id, messenger

        logger.warning(
            "Could not determine messenger for user",
            extra={"user_id": str(user_id)[:20]},
        )
        return None, None, None


@log_operation("get_messenger_instance")
def get_messenger_instance(_platform: str = "telegram"):
    """Always returns the Telegram messenger instance now."""
    with log_context(logger, platform="telegram"):
        try:
            from common.messaging.telegram_messaging import TelegramMessaging
            from services.telegram_service.app.bot import bot

            return TelegramMessaging(bot)
        except ImportError as e:
            logger.error(
                "Failed to import TelegramMessaging",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            return None
        except Exception as e:
            logger.error(
                "Error creating Telegram messenger",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            return None


# ===== Messaging Utilities =====


class MessageFormatter:
    """
    Utility class for formatting messages based on platform.
    Provides consistent formatting across different messaging platforms.
    """

    @staticmethod
    @log_operation("format_ad_text")
    def format_ad_text(ad_data: Dict[str, Any], platform: str = "default") -> str:
        """
        Format ad text based on platform-specific requirements.

        Args:
            ad_data: Dictionary with ad information
            platform: Target platform (telegram,)

        Returns:
            Formatted ad text string
        """
        from common.config import build_ad_text

        with log_context(logger, platform=platform, ad_id=ad_data.get("id")):
            text = build_ad_text(ad_data, markdown=True)

            logger.info(
                "Formatted ad text",
                extra={"platform": platform, "text_length": len(text)},
            )
            return text


# ===== Unified Message Sending Functions =====


@log_operation("safe_send_message")
async def safe_send_message(
    user_id: Union[str, int],
    text: str,
    platform: Optional[str] = None,
    retry_count: int = 3,
    retry_delay: int = 1,
    **kwargs,
) -> Union[Any, bool, None]:
    """
    Unified function to safely send a text message across any platform.

    Args:
        user_id: Platform-specific user ID or database user ID
        text: Message text
        platform: Optional platform override ("telegram",)
        retry_count: Number of retry attempts
        retry_delay: Initial delay between retries
        **kwargs: Platform-specific parameters (parse_mode, reply_markup, keyboard, etc.)

    Returns:
        Response from the messaging platform or boolean success status
    """
    from common.messaging.service import messaging_service

    with log_context(
        logger, user_id=str(user_id)[:20], platform=platform, retry_count=retry_count
    ):
        try:
            # Get database user ID, platform and messenger
            db_user_id, platform_name, platform_id = resolve_user_id(user_id)

            # If we have a database user ID, try to use the unified messaging service
            if db_user_id:
                try:
                    success = await messaging_service.send_notification(
                        user_id=db_user_id, text=text, **kwargs
                    )
                    if success:
                        logger.info(
                            "Message sent via messaging service",
                            extra={"user_id": db_user_id, "platform": platform_name},
                        )
                        return True
                except Exception as e:
                    logger.warning(
                        "Error using messaging service",
                        exc_info=True,
                        extra={"error_type": type(e).__name__},
                    )

            # If we have platform info, try direct send
            if platform_name and platform_id:
                messenger = get_messenger_instance(platform_name)
                if messenger:
                    # Send the message with retry logic
                    for attempt in range(retry_count):
                        try:
                            result = await messenger.send_text(
                                platform_id, text, **kwargs
                            )
                            logger.info(
                                "Message sent directly",
                                extra={
                                    "platform": platform_name,
                                    "attempt": attempt + 1,
                                },
                            )
                            return result
                        except Exception as e:
                            if attempt < retry_count - 1:
                                current_delay = retry_delay * (2**attempt)
                                jitter = random.uniform(0.8, 1.2)
                                final_delay = current_delay * jitter
                                logger.warning(
                                    "Failed to send message, retrying",
                                    extra={
                                        "attempt": attempt + 1,
                                        "retry_count": retry_count,
                                        "delay": final_delay,
                                        "error_type": type(e).__name__,
                                    },
                                )
                                await asyncio.sleep(final_delay)
                            else:
                                logger.error(
                                    "Failed to send message after retries",
                                    exc_info=True,
                                    extra={
                                        "attempts": retry_count,
                                        "error_type": type(e).__name__,
                                    },
                                )
                                return None

            logger.error(
                "Could not send message - unable to resolve user ID or platform",
                extra={"user_id": str(user_id)[:20]},
            )
            return None
        except Exception as e:
            logger.error(
                "Error in safe_send_message",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            return None


@log_operation("safe_send_media")
async def safe_send_media(
    user_id: Union[str, int],
    media_url: str,
    caption: Optional[str] = None,
    platform: Optional[str] = None,
    retry_count: int = 3,
    retry_delay: int = 1,
    **kwargs,
) -> Union[Any, bool, None]:
    """
    Unified function to safely send a media message across any platform.

    Args:
        user_id: Platform-specific user ID or database user ID
        media_url: URL of the media to send
        caption: Optional caption text
        platform: Optional platform override ("telegram",)
        retry_count: Number of retry attempts
        retry_delay: Initial delay between retries
        **kwargs: Platform-specific parameters (parse_mode, reply_markup, keyboard, etc.)

    Returns:
        Response from the messaging platform or boolean success status
    """
    from common.messaging.service import messaging_service

    with log_context(
        logger, user_id=str(user_id)[:20], platform=platform, media_url=media_url[:50]
    ):
        try:
            # Get database user ID, platform and messenger
            db_user_id, platform_name, platform_id = resolve_user_id(user_id)

            # If we have a database user ID, try to use the unified messaging service
            if db_user_id:
                try:
                    success = await messaging_service.send_notification(
                        user_id=db_user_id, text=caption, image_url=media_url, **kwargs
                    )
                    if success:
                        logger.info(
                            "Media sent via messaging service",
                            extra={"user_id": db_user_id, "platform": platform_name},
                        )
                        return True
                except Exception as e:
                    logger.warning(
                        "Error using messaging service",
                        exc_info=True,
                        extra={"error_type": type(e).__name__},
                    )

            # If we have platform info, try direct send
            if platform_name and platform_id:
                messenger = get_messenger_instance(platform_name)
                if messenger:
                    # Send the media with retry logic
                    for attempt in range(retry_count):
                        try:
                            result = await messenger.send_media(
                                platform_id, media_url, caption=caption, **kwargs
                            )
                            logger.info(
                                "Media sent directly",
                                extra={
                                    "platform": platform_name,
                                    "attempt": attempt + 1,
                                },
                            )
                            return result
                        except Exception as e:
                            if attempt < retry_count - 1:
                                current_delay = retry_delay * (2**attempt)
                                jitter = random.uniform(0.8, 1.2)
                                final_delay = current_delay * jitter
                                logger.warning(
                                    "Failed to send media, retrying",
                                    extra={
                                        "attempt": attempt + 1,
                                        "retry_count": retry_count,
                                        "delay": final_delay,
                                        "error_type": type(e).__name__,
                                    },
                                )
                                await asyncio.sleep(final_delay)
                            else:
                                logger.error(
                                    "Failed to send media after retries",
                                    exc_info=True,
                                    extra={
                                        "attempts": retry_count,
                                        "error_type": type(e).__name__,
                                    },
                                )
                                # Try sending just text if media fails
                                if caption:
                                    try:
                                        return await safe_send_message(
                                            user_id=user_id,
                                            text=f"{caption}\n\n[Media URL: {media_url}]",
                                            platform=platform_name,
                                            **kwargs,
                                        )
                                    except Exception:
                                        logger.debug("Fallback text send also failed",
                                                     extra={"user_id": str(user_id)[:20]})
                                return None

            logger.error(
                "Could not send media - unable to resolve user ID or platform",
                extra={"user_id": str(user_id)[:20]},
            )
            return None
        except Exception as e:
            logger.error(
                "Error in safe_send_media",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            return None


@log_operation("safe_send_menu")
async def safe_send_menu(
    user_id: Union[str, int],
    text: str,
    options: List[Dict[str, str]],
    platform: Optional[str] = None,
    **kwargs,
) -> Union[Any, bool, None]:
    """
    Unified function to safely send a menu across any platform.

    Args:
        user_id: Platform-specific user ID or database user ID
        text: Menu title/description text
        options: List of option dictionaries with at least 'text' and 'value' keys
        platform: Optional platform override ("telegram",)
        **kwargs: Platform-specific parameters

    Returns:
        Response from the messaging platform or boolean success status
    """
    with log_context(
        logger, user_id=str(user_id)[:20], platform=platform, options_count=len(options)
    ):
        try:
            # Get database user ID, platform and messenger
            db_user_id, platform_name, platform_id = resolve_user_id(user_id)

            # If we have platform info, send the menu
            if platform_name and platform_id:
                messenger = get_messenger_instance(platform_name)
                if messenger:
                    # Send the menu
                    result = await messenger.send_menu(
                        platform_id, text, options, **kwargs
                    )
                    logger.info(
                        "Menu sent",
                        extra={
                            "platform": platform_name,
                            "options_count": len(options),
                        },
                    )
                    return result

            logger.error(
                "Could not send menu - unable to resolve user ID or platform",
                extra={"user_id": str(user_id)[:20]},
            )
            return None
        except Exception as e:
            logger.error(
                "Error in safe_send_menu",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            return None


# ===== Platform-Specific Helper Functions =====

# Telegram-specific helpers


@log_operation("safe_edit_message_telegram")
async def safe_edit_message_telegram(
    chat_id: Union[int, str],
    message_id: int,
    text: str,
    parse_mode: Optional[str] = None,
    reply_markup: Any = None,
    disable_web_page_preview: bool = False,
) -> Optional[Any]:
    """
    Telegram-specific function to safely edit a message.

    Args:
        chat_id: Telegram chat ID
        message_id: Message ID to edit
        text: New message text
        parse_mode: Optional parse mode (Markdown or HTML)
        reply_markup: Optional reply markup (keyboard)
        disable_web_page_preview: Whether to disable web page preview

    Returns:
        Response from Telegram or None if failed
    """
    with log_context(logger, chat_id=chat_id, message_id=message_id):
        try:
            from services.telegram_service.app.bot import bot
            from aiogram.exceptions import TelegramBadRequest, TelegramAPIError

            try:
                result = await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                    disable_web_page_preview=disable_web_page_preview,
                )
                logger.info("Message edited successfully")
                return result
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    logger.info("Message not modified (content is the same)")
                    return None
                logger.error(
                    "Failed to edit message",
                    exc_info=True,
                    extra={"error_type": type(e).__name__},
                )
                return None
            except TelegramAPIError as e:
                logger.error(
                    "Failed to edit message",
                    exc_info=True,
                    extra={"error_type": type(e).__name__},
                )
                return None
        except ImportError as e:
            logger.error(
                "Telegram dependencies not available",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            return None


@log_operation("safe_answer_callback_query_telegram")
async def safe_answer_callback_query_telegram(
    callback_query_id: str, text: Optional[str] = None, show_alert: bool = False
) -> bool:
    """
    Telegram-specific function to safely answer a callback query.

    Args:
        callback_query_id: Callback query ID
        text: Optional text to show to the user
        show_alert: Whether to show as alert (vs. toast)

    Returns:
        True if succeeded, False otherwise
    """
    with log_context(logger, callback_query_id=callback_query_id):
        try:
            from services.telegram_service.app.bot import bot
            from aiogram.exceptions import TelegramBadRequest, TelegramAPIError

            try:
                await bot.answer_callback_query(
                    callback_query_id=callback_query_id,
                    text=text,
                    show_alert=show_alert,
                )
                logger.info("Callback query answered successfully")
                return True
            except TelegramBadRequest as e:
                if "query is too old" in str(e) or "query_id_invalid" in str(e).lower():
                    logger.warning("Invalid query ID (callback is too old)")
                    return False
                logger.error(
                    "Failed to answer callback query",
                    exc_info=True,
                    extra={"error_type": type(e).__name__},
                )
                return False
            except TelegramAPIError as e:
                logger.error(
                    "Failed to answer callback query",
                    exc_info=True,
                    extra={"error_type": type(e).__name__},
                )
                return False
        except ImportError as e:
            logger.error(
                "Telegram dependencies not available",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            return False


@log_operation("delete_message_safe_telegram")
async def delete_message_safe_telegram(
    chat_id: Union[int, str], message_id: int
) -> bool:
    """
    Telegram-specific function to safely delete a message.

    Args:
        chat_id: Telegram chat ID
        message_id: Message ID to delete

    Returns:
        True if succeeded or already deleted, False otherwise
    """
    with log_context(logger, chat_id=chat_id, message_id=message_id):
        try:
            from services.telegram_service.app.bot import bot
            from aiogram.exceptions import TelegramBadRequest, TelegramAPIError

            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
                logger.info("Message deleted successfully")
                return True
            except TelegramBadRequest as e:
                if "message to delete not found" in str(e).lower():
                    logger.info("Message to delete not found (already deleted)")
                    return True
                logger.error(
                    "Failed to delete message",
                    exc_info=True,
                    extra={"error_type": type(e).__name__},
                )
                return False
            except TelegramAPIError as e:
                logger.error(
                    "Failed to delete message",
                    exc_info=True,
                    extra={"error_type": type(e).__name__},
                )
                return False
        except ImportError as e:
            logger.error(
                "Telegram dependencies not available",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            return False
