# services/telegram_service/app/utils/message_utils.py

from typing import Optional, Union
from aiogram.types import Message, InputFile
import aiohttp
import asyncio
from urllib.parse import urlparse
import re
from io import BytesIO
from PIL import Image

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


# --- Asynchronous processing of image URLs (non-blocking) -------------------

@log_operation("async_process_image_url")
async def async_process_image_url(url: str) -> Union[str, InputFile, None]:
    """
    Asynchronously validate an image link and, when needed, download it.
    """
    with log_context(logger, url_length=len(url)):
        # Basic URL validation
        if not url or not isinstance(url, str):
            logger.warning("Invalid image URL", extra={"url_type": type(url).__name__ if url else "None"})
            return None

        # Parse URL to check format
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                logger.warning("Malformed image URL", extra={"url": url[:100]})
                return None

            # Check if URL already has image extension
            if re.search(r'\.(jpg|jpeg|png|gif|webp)(\?|$)', parsed.path.lower()):
                logger.debug("URL appears to be a direct image link", extra={"url": url[:100]})
                return url

            # For cloudfront URLs, try to use directly
            if 'cloudfront.net' in parsed.netloc:
                logger.info("Using cloudfront URL directly", extra={"url": url[:100]})
                return url

            # For other URLs, try to check with a HEAD request
            headers = {'User-Agent': 'Mozilla/5.0'}
            timeout = aiohttp.ClientTimeout(total=5)

            # HEAD request to confirm content-type
            try:
                async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                    async with session.head(url, allow_redirects=True) as resp:
                        if resp.status < 400:
                            content_type = resp.headers.get('Content-Type', '')
                            if 'image/' in content_type:
                                if 'image/webp' in content_type:
                                    # Telegram cannot fetch webp as photo; download and convert
                                    async with session.get(url) as img_resp:
                                        data = await img_resp.read()
                                    try:
                                        img_stream = BytesIO(data)
                                        im = Image.open(img_stream).convert('RGB')
                                        out_bytes = BytesIO()
                                        im.save(out_bytes, format='JPEG', quality=90)
                                        out_bytes.seek(0)
                                        out_bytes.name = 'photo.jpg'
                                        return InputFile(out_bytes)
                                    except Exception as e:
                                        logger.error("Failed to convert WEBP to JPEG", exc_info=True, extra={"error": str(e)})
                                        return None
                                logger.debug("URL confirmed as image through HEAD request", extra={
                                    "content_type": content_type
                                })
                                return url

                    # If not confirmed, try a GET to download first bytes
                    async with session.get(url) as img_resp:
                        if img_resp.status == 200 and 'image/' in img_resp.headers.get('Content-Type', ''):
                            data = await img_resp.read()
                            img_data = BytesIO(data)
                            img_data.name = "image.jpg"
                            return InputFile(img_data)

            except Exception as e:
                logger.error("Error processing image URL asynchronously", exc_info=True, extra={"error": str(e)})

            # If we get here, we couldn't process the URL
            return None

        except Exception as e:
            logger.error(f"Error parsing image URL: {str(e)}", exc_info=True)
            return None


# --- Public wrapper that remains backward compatible ------------------------

@log_operation("telegram_safe_send_photo")
async def safe_send_photo(
        chat_id: Union[int, str],
        photo: Union[str, InputFile],
        caption: Optional[str] = None,
        **kwargs
) -> Optional[Message]:
    """
    Telegram-specific function to send photos directly through the bot.

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
            # Process the image URL to ensure it's compatible with Telegram
            if isinstance(photo, str):
                processed_photo = await async_process_image_url(photo)
                if not processed_photo:
                    # Fallback to text message with image link if photo couldn't be processed
                    logger.warning("Invalid image URL, falling back to text message with link", extra={
                        "chat_id": chat_id
                    })

                    # Prepare text message with image link
                    full_text = caption or ""
                    if full_text:
                        full_text += "\n\n"
                    full_text += f"[Посилання на зображення]({photo})"

                    # Preserve original kwargs but ensure parse_mode is set for the markdown link
                    send_kwargs = kwargs.copy()
                    send_kwargs['parse_mode'] = 'Markdown'  # Force Markdown for the image link

                    return await safe_send_message(
                        chat_id=chat_id,
                        text=full_text,
                        **send_kwargs
                    )
                photo = processed_photo

            logger.debug("Sending photo via direct bot method", extra={
                "chat_id": chat_id,
                "photo_type": type(photo).__name__,
                "has_caption": bool(caption)
            })

            result = await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                **kwargs
            )

            if isinstance(result, Message) and result.photo:
                logger.info("Photo sent successfully", extra={
                    "chat_id": chat_id
                })

            return result

        except Exception as e:
            logger.error("Error sending photo", exc_info=True, extra={
                "chat_id": chat_id,
                "error": str(e)
            })

            # Fallback to sending as text with link
            try:
                if isinstance(photo, str) and caption:
                    full_text = caption + f"\n\n[Посилання на зображення]({photo})"

                    # Ensure parse_mode is set for the markdown link
                    send_kwargs = kwargs.copy()
                    send_kwargs['parse_mode'] = 'Markdown'  # Force Markdown for the image link

                    # If original parse_mode was HTML, add a note
                    if kwargs.get('parse_mode') == 'HTML':
                        full_text += "\n\n(Note: Original HTML formatting has been converted to Markdown)"

                    result = await safe_send_message(
                        chat_id=chat_id,
                        text=full_text,
                        **send_kwargs
                    )

                    if result:
                        logger.info("Fallback text message sent successfully", extra={
                            "chat_id": chat_id
                        })
                    return result
                else:
                    # If we don't have a string photo or caption, send a generic error message
                    result = await safe_send_message(
                        chat_id=chat_id,
                        text="Не вдалося відобразити зображення. Спробуйте пізніше.",
                        parse_mode=None  # No parse mode needed for this basic message
                    )
                    return result

            except Exception as e2:
                logger.error("Error sending fallback text message", exc_info=True, extra={
                    "chat_id": chat_id,
                    "error": str(e2)
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

