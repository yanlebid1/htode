# common/messaging/unified_platform_utils.py

import asyncio
import random
from typing import Dict, Any, Optional, Tuple, Union, List, TypeVar
from common.utils.logging_config import log_operation, log_context

# Import the messaging logger
from . import logger

# Type variable for return value
T = TypeVar('T')


# ===== Platform Detection and Resolution =====

@log_operation("detect_platform_from_id")
def detect_platform_from_id(user_id: str) -> Tuple[str, str]:
    """
    Detect messaging platform from user ID format.

    Args:
        user_id: Platform-specific user ID

    Returns:
        Tuple of (platform_name, clean_user_id)
    """
    with log_context(logger, user_id=user_id[:20]):
        user_id_str = str(user_id)

        if user_id_str.startswith("whatsapp:"):
            result = ("whatsapp", user_id_str)
        elif len(user_id_str) > 20:  # Viber IDs are typically long UUIDs
            result = ("viber", user_id_str)
        else:
            # Default to Telegram for numeric IDs and other formats
            result = ("telegram", user_id_str)

        logger.info("Detected platform from ID", extra={
            'platform': result[0],
            'id_length': len(user_id_str)
        })
        return result


def format_user_id_for_platform(user_id: str, platform: str) -> str:
    """
    Format a user ID according to platform requirements.
    Centralized implementation to avoid duplication.

    Args:
        user_id: Raw user identifier
        platform: Target platform (telegram, viber, whatsapp)

    Returns:
        Formatted user identifier
    """
    if platform == "whatsapp" and not user_id.startswith("whatsapp:"):
        return f"whatsapp:{user_id}"

    # Other platforms don't need special formatting
    return user_id


@log_operation("resolve_user_id")
def resolve_user_id(user_id: Union[int, str], platform: Optional[str] = None) -> Tuple[
    Optional[int], Optional[str], Optional[str]]:
    """
    Resolve a user ID to get database ID and platform information.

    Args:
        user_id: Either a database user ID or platform-specific ID
        platform: Optional platform hint

    Returns:
        Tuple of (database_user_id, platform_name, platform_id)
    """
    from common.db.operations import get_db_user_id_by_telegram_id, get_platform_ids_for_user

    with log_context(logger, user_id=str(user_id)[:20], platform=platform):
        # Case 1: Database user ID
        logger.info(f'Resolving user ID {user_id}')
        if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()):
            db_user_id = int(user_id)

            # Get platform IDs for this user
            platform_ids = get_platform_ids_for_user(db_user_id)

            # Determine which platform to use (priority order)
            if platform_ids.get("telegram_id"):
                result = (db_user_id, "telegram", str(platform_ids["telegram_id"]))
            elif platform_ids.get("viber_id"):
                result = (db_user_id, "viber", platform_ids["viber_id"])
            elif platform_ids.get("whatsapp_id"):
                result = (db_user_id, "whatsapp", platform_ids["whatsapp_id"])
            else:
                # Default to telegram if no platform information is found
                # This prevents the "No messenger implementation registered for platform" error
                logger.warning("No platform information found for user, defaulting to telegram", extra={
                    'db_user_id': db_user_id
                })
                result = (db_user_id, "telegram", str(db_user_id))  # Use DB ID as telegram_id as fallback

            logger.info("Resolved database user ID", extra={
                'db_user_id': db_user_id,
                'platform': result[1]
            })
            return result

        # Case 2: Platform-specific ID

        # If platform is provided, use it
        if platform:
            platform_name = platform
            platform_id = user_id
            logger.info(f'Resolving user ID for platform {platform_name}')
        else:
            # Detect platform from ID format
            logger.info('Detecting platform from user ID')
            platform_name, platform_id = detect_platform_from_id(user_id)
            logger.info(f'Detected platform {platform_name}, {platform_id[:20]}...')

        # Get database user ID
        logger.info(f'Resolving database user ID for platform {platform_name}, {platform_id[:20]}...')
        db_user_id = get_db_user_id_by_telegram_id(platform_id, messenger_type=platform_name)

        logger.info("Resolved platform user ID", extra={
            'platform': platform_name,
            'db_user_id': db_user_id,
            'platform_id': platform_id[:20] if platform_id else None
        })
        return (db_user_id, platform_name, platform_id)


@log_operation("get_messenger_for_user")
async def get_messenger_for_user(user_id: Union[int, str]) -> Tuple[Optional[str], Optional[str], Optional[Any]]:
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
            logger.info("Found messenger for user", extra={
                'platform': platform_name,
                'has_messenger': bool(messenger)
            })
            return platform_name, platform_id, messenger

        logger.warning("Could not determine messenger for user", extra={
            'user_id': str(user_id)[:20]
        })
        return None, None, None


@log_operation("get_messenger_instance")
def get_messenger_instance(platform: str):
    """
    Get the appropriate messenger instance for a platform.

    Args:
        platform: Platform name (telegram, viber, whatsapp)

    Returns:
        Messenger instance or None if not found
    """
    with log_context(logger, platform=platform):
        try:
            if platform == "telegram":
                from common.messaging.telegram_messaging import TelegramMessaging
                from services.telegram_service.app.bot import bot
                return TelegramMessaging(bot)
            elif platform == "viber":
                from common.messaging.viber_messaging import ViberMessaging
                from services.viber_service.app.bot import viber
                return ViberMessaging(viber)
            elif platform == "whatsapp":
                from common.messaging.whatsapp_messaging import WhatsAppMessaging
                from services.whatsapp_service.app.bot import client
                return WhatsAppMessaging(client)
            else:
                logger.warning(f"Unknown platform", extra={'platform': platform})
                return None
        except ImportError as e:
            logger.error(f"Error importing messenger", exc_info=True, extra={
                'platform': platform,
                'error_type': type(e).__name__
            })
            return None
        except Exception as e:
            logger.error(f"Error getting messenger instance", exc_info=True, extra={
                'platform': platform,
                'error_type': type(e).__name__
            })
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
            platform: Target platform (telegram, viber, whatsapp)

        Returns:
            Formatted ad text string
        """
        from common.config import GEO_ID_MAPPING

        with log_context(logger, platform=platform, ad_id=ad_data.get('id')):
            # Extract ad data with defaults
            city_id = ad_data.get('city')
            city_name = GEO_ID_MAPPING.get(city_id, "Невідомо")
            price = ad_data.get('price', 0)
            address = ad_data.get('address', "Невідомо")
            rooms_count = ad_data.get('rooms_count', "Невідомо")
            square_feet = ad_data.get('square_feet', "Невідомо")
            floor = ad_data.get('floor', "Невідомо")
            total_floors = ad_data.get('total_floors', "Невідомо")

            # Apply platform-specific formatting
            if platform == "telegram":
                # Telegram supports markdown
                text = (
                    f"💰 Ціна: *{int(price)}* грн.\n"
                    f"🏙️ Місто: *{city_name}*\n"
                    f"📍 Адреса: *{address}*\n"
                    f"🛏️ Кіл-сть кімнат: *{rooms_count}*\n"
                    f"📐 Площа: *{square_feet}* кв.м.\n"
                    f"🏢 Поверх: *{floor}* з *{total_floors}*\n"
                )
            elif platform in ["viber", "whatsapp"]:
                # Standard text formatting for platforms without markdown
                text = (
                    f"💰 Ціна: {int(price)} грн.\n"
                    f"🏙️ Місто: {city_name}\n"
                    f"📍 Адреса: {address}\n"
                    f"🛏️ Кіл-сть кімнат: {rooms_count}\n"
                    f"📐 Площа: {square_feet} кв.м.\n"
                    f"🏢 Поверх: {floor} з {total_floors}\n"
                )
            else:
                # Default format for unknown platforms
                text = (
                    f"💰 Ціна: {int(price)} грн.\n"
                    f"🏙️ Місто: {city_name}\n"
                    f"📍 Адреса: {address}\n"
                    f"🛏️ Кіл-сть кімнат: {rooms_count}\n"
                    f"📐 Площа: {square_feet} кв.м.\n"
                    f"🏢 Поверх: {floor} з {total_floors}\n"
                )

            logger.info("Formatted ad text", extra={
                'platform': platform,
                'text_length': len(text)
            })
            return text


# ===== Unified Message Sending Functions =====

@log_operation("safe_send_message")
async def safe_send_message(
        user_id: Union[str, int],
        text: str,
        platform: Optional[str] = None,
        retry_count: int = 3,
        retry_delay: int = 1,
        **kwargs
) -> Union[Any, bool, None]:
    """
    Unified function to safely send a text message across any platform.

    Args:
        user_id: Platform-specific user ID or database user ID
        text: Message text
        platform: Optional platform override ("telegram", "viber", "whatsapp")
        retry_count: Number of retry attempts
        retry_delay: Initial delay between retries
        **kwargs: Platform-specific parameters (parse_mode, reply_markup, keyboard, etc.)

    Returns:
        Response from the messaging platform or boolean success status
    """
    from common.messaging.service import messaging_service

    with log_context(logger, user_id=str(user_id)[:20], platform=platform, retry_count=retry_count):
        try:
            # Get database user ID, platform and messenger
            db_user_id, platform_name, platform_id = resolve_user_id(user_id, platform)

            # If we have a database user ID, try to use the unified messaging service
            if db_user_id:
                try:
                    success = await messaging_service.send_notification(
                        user_id=db_user_id,
                        text=text,
                        **kwargs
                    )
                    if success:
                        logger.info("Message sent via messaging service", extra={
                            'user_id': db_user_id,
                            'platform': platform_name
                        })
                        return True
                except Exception as e:
                    logger.warning("Error using messaging service", exc_info=True, extra={
                        'error_type': type(e).__name__
                    })

            # If we have platform info, try direct send
            if platform_name and platform_id:
                messenger = get_messenger_instance(platform_name)
                if messenger:
                    # Format user ID for this platform
                    formatted_id = format_user_id_for_platform(platform_id, platform_name)

                    # Send the message with retry logic
                    for attempt in range(retry_count):
                        try:
                            result = await messenger.send_text(formatted_id, text, **kwargs)
                            logger.info("Message sent directly", extra={
                                'platform': platform_name,
                                'attempt': attempt + 1
                            })
                            return result
                        except Exception as e:
                            if attempt < retry_count - 1:
                                current_delay = retry_delay * (2 ** attempt)
                                jitter = random.uniform(0.8, 1.2)
                                final_delay = current_delay * jitter
                                logger.warning(
                                    f"Failed to send message, retrying", extra={
                                        'attempt': attempt + 1,
                                        'retry_count': retry_count,
                                        'delay': final_delay,
                                        'error_type': type(e).__name__
                                    }
                                )
                                await asyncio.sleep(final_delay)
                            else:
                                logger.error(f"Failed to send message after retries", exc_info=True, extra={
                                    'attempts': retry_count,
                                    'error_type': type(e).__name__
                                })
                                return None

            logger.error(f"Could not send message - unable to resolve user ID or platform", extra={
                'user_id': str(user_id)[:20]
            })
            return None
        except Exception as e:
            logger.error(f"Error in safe_send_message", exc_info=True, extra={
                'error_type': type(e).__name__
            })
            return None


@log_operation("safe_send_media")
async def safe_send_media(
        user_id: Union[str, int],
        media_url: str,
        caption: Optional[str] = None,
        platform: Optional[str] = None,
        retry_count: int = 3,
        retry_delay: int = 1,
        **kwargs
) -> Union[Any, bool, None]:
    """
    Unified function to safely send a media message across any platform.

    Args:
        user_id: Platform-specific user ID or database user ID
        media_url: URL of the media to send
        caption: Optional caption text
        platform: Optional platform override ("telegram", "viber", "whatsapp")
        retry_count: Number of retry attempts
        retry_delay: Initial delay between retries
        **kwargs: Platform-specific parameters (parse_mode, reply_markup, keyboard, etc.)

    Returns:
        Response from the messaging platform or boolean success status
    """
    from common.messaging.service import messaging_service

    with log_context(logger, user_id=str(user_id)[:20], platform=platform, media_url=media_url[:50]):
        try:
            # Get database user ID, platform and messenger
            db_user_id, platform_name, platform_id = resolve_user_id(user_id, platform)

            # If we have a database user ID, try to use the unified messaging service
            if db_user_id:
                try:
                    success = await messaging_service.send_notification(
                        user_id=db_user_id,
                        text=caption,
                        image_url=media_url,
                        **kwargs
                    )
                    if success:
                        logger.info("Media sent via messaging service", extra={
                            'user_id': db_user_id,
                            'platform': platform_name
                        })
                        return True
                except Exception as e:
                    logger.warning("Error using messaging service", exc_info=True, extra={
                        'error_type': type(e).__name__
                    })

            # If we have platform info, try direct send
            if platform_name and platform_id:
                messenger = get_messenger_instance(platform_name)
                if messenger:
                    # Format user ID for this platform
                    formatted_id = format_user_id_for_platform(platform_id, platform_name)

                    # Send the media with retry logic
                    for attempt in range(retry_count):
                        try:
                            result = await messenger.send_media(formatted_id, media_url, caption=caption, **kwargs)
                            logger.info("Media sent directly", extra={
                                'platform': platform_name,
                                'attempt': attempt + 1
                            })
                            return result
                        except Exception as e:
                            if attempt < retry_count - 1:
                                current_delay = retry_delay * (2 ** attempt)
                                jitter = random.uniform(0.8, 1.2)
                                final_delay = current_delay * jitter
                                logger.warning(
                                    f"Failed to send media, retrying", extra={
                                        'attempt': attempt + 1,
                                        'retry_count': retry_count,
                                        'delay': final_delay,
                                        'error_type': type(e).__name__
                                    }
                                )
                                await asyncio.sleep(final_delay)
                            else:
                                logger.error(f"Failed to send media after retries", exc_info=True, extra={
                                    'attempts': retry_count,
                                    'error_type': type(e).__name__
                                })
                                # Try sending just text if media fails
                                if caption:
                                    try:
                                        return await safe_send_message(
                                            user_id=user_id,
                                            text=f"{caption}\n\n[Media URL: {media_url}]",
                                            platform=platform_name,
                                            **kwargs
                                        )
                                    except Exception:
                                        pass
                                return None

            logger.error(f"Could not send media - unable to resolve user ID or platform", extra={
                'user_id': str(user_id)[:20]
            })
            return None
        except Exception as e:
            logger.error(f"Error in safe_send_media", exc_info=True, extra={
                'error_type': type(e).__name__
            })
            return None


@log_operation("safe_send_menu")
async def safe_send_menu(
        user_id: Union[str, int],
        text: str,
        options: List[Dict[str, str]],
        platform: Optional[str] = None,
        **kwargs
) -> Union[Any, bool, None]:
    """
    Unified function to safely send a menu across any platform.

    Args:
        user_id: Platform-specific user ID or database user ID
        text: Menu title/description text
        options: List of option dictionaries with at least 'text' and 'value' keys
        platform: Optional platform override ("telegram", "viber", "whatsapp")
        **kwargs: Platform-specific parameters

    Returns:
        Response from the messaging platform or boolean success status
    """
    with log_context(logger, user_id=str(user_id)[:20], platform=platform, options_count=len(options)):
        try:
            # Get database user ID, platform and messenger
            db_user_id, platform_name, platform_id = resolve_user_id(user_id, platform)

            # If we have platform info, send the menu
            if platform_name and platform_id:
                messenger = get_messenger_instance(platform_name)
                if messenger:
                    # Format user ID for this platform
                    formatted_id = format_user_id_for_platform(platform_id, platform_name)

                    # Send the menu
                    result = await messenger.send_menu(formatted_id, text, options, **kwargs)
                    logger.info("Menu sent", extra={
                        'platform': platform_name,
                        'options_count': len(options)
                    })
                    return result

            logger.error(f"Could not send menu - unable to resolve user ID or platform", extra={
                'user_id': str(user_id)[:20]
            })
            return None
        except Exception as e:
            logger.error(f"Error in safe_send_menu", exc_info=True, extra={
                'error_type': type(e).__name__
            })
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
        disable_web_page_preview: bool = False
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
            from aiogram.utils.exceptions import MessageNotModified, TelegramAPIError

            try:
                result = await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                    disable_web_page_preview=disable_web_page_preview
                )
                logger.info("Message edited successfully")
                return result
            except MessageNotModified:
                logger.info("Message not modified (content is the same)")
                return None
            except TelegramAPIError as e:
                logger.error(f"Failed to edit message", exc_info=True, extra={
                    'error_type': type(e).__name__
                })
                return None
        except ImportError as e:
            logger.error(f"Telegram dependencies not available", exc_info=True, extra={
                'error_type': type(e).__name__
            })
            return None


@log_operation("safe_answer_callback_query_telegram")
async def safe_answer_callback_query_telegram(
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False
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
            from aiogram.utils.exceptions import InvalidQueryID, TelegramAPIError

            try:
                await bot.answer_callback_query(
                    callback_query_id=callback_query_id,
                    text=text,
                    show_alert=show_alert
                )
                logger.info("Callback query answered successfully")
                return True
            except InvalidQueryID:
                logger.warning("Invalid query ID (callback is too old)")
                return False
            except TelegramAPIError as e:
                logger.error(f"Failed to answer callback query", exc_info=True, extra={
                    'error_type': type(e).__name__
                })
                return False
        except ImportError as e:
            logger.error(f"Telegram dependencies not available", exc_info=True, extra={
                'error_type': type(e).__name__
            })
            return False


@log_operation("delete_message_safe_telegram")
async def delete_message_safe_telegram(
        chat_id: Union[int, str],
        message_id: int
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
            from aiogram.utils.exceptions import MessageToDeleteNotFound, TelegramAPIError

            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
                logger.info("Message deleted successfully")
                return True
            except MessageToDeleteNotFound:
                logger.info("Message to delete not found (already deleted)")
                return True
            except TelegramAPIError as e:
                logger.error(f"Failed to delete message", exc_info=True, extra={
                    'error_type': type(e).__name__
                })
                return False
        except ImportError as e:
            logger.error(f"Telegram dependencies not available", exc_info=True, extra={
                'error_type': type(e).__name__
            })
            return False

