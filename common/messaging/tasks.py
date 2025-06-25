# common/messaging/tasks.py

import asyncio
from typing import Dict, Any, Optional, List


from common.celery_app import celery_app
from common.db.operations import Ad
from .service import messaging_service
from common.db.session import db_session
from common.utils.logging_config import log_operation, log_context

# Import the messaging logger
from . import logger


@celery_app.task(name="common.messaging.tasks.send_notification")
@log_operation("send_notification")
def send_notification(user_id: int, text: str, **kwargs):
    """
    Send a notification to a user via their preferred messaging platform.

    Args:
        user_id: Database user ID
        text: Notification text
        **kwargs: Additional parameters for the notification
    """
    with log_context(logger, user_id=user_id, text_length=len(text)):

        async def send():
            try:
                # Use the messaging service to send the notification
                success = await messaging_service.send_notification(
                    user_id=user_id, text=text, **kwargs
                )

                if not success:
                    logger.error(
                        "Failed to send notification",
                        extra={"user_id": user_id, "text_preview": text[:50]},
                    )
                    return False

                logger.info(
                    "Notification sent successfully",
                    extra={"user_id": user_id, "text_length": len(text)},
                )
                return True
            except Exception as e:
                logger.error(
                    "Error sending notification",
                    exc_info=True,
                    extra={"user_id": user_id, "error_type": type(e).__name__},
                )
                return False

        # Run the async function
        try:
            return asyncio.run(send())
        except RuntimeError as e:
            # Handle case where there's already an event loop
            logger.warning(
                "RuntimeError in send_notification",
                extra={"error_type": type(e).__name__},
            )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(send())
            finally:
                loop.close()


@celery_app.task(name="common.messaging.tasks.send_ad")
@log_operation("send_ad")
def send_ad(
    user_id: int, ad_data: Dict[str, Any], image_url: Optional[str] = None, **kwargs
):
    """
    Send an ad to a user via their preferred messaging platform.

    Args:
        user_id: Database user ID
        ad_data: Dictionary with ad data
        image_url: Optional URL for the primary ad image
        **kwargs: Additional parameters for the ad
    """
    with log_context(logger, user_id=user_id, ad_id=ad_data.get("id")):

        async def send():
            try:
                # Use the messaging service to send the ad
                success = await messaging_service.send_ad(
                    user_id=user_id, ad_data=ad_data, image_url=image_url, **kwargs
                )

                if not success:
                    logger.error(
                        "Failed to send ad",
                        extra={"user_id": user_id, "ad_id": ad_data.get("id")},
                    )
                    return False

                logger.info(
                    "Ad sent successfully",
                    extra={
                        "user_id": user_id,
                        "ad_id": ad_data.get("id"),
                        "has_image": bool(image_url),
                    },
                )
                return True
            except Exception as e:
                logger.error(
                    "Error sending ad",
                    exc_info=True,
                    extra={
                        "user_id": user_id,
                        "ad_id": ad_data.get("id"),
                        "error_type": type(e).__name__,
                    },
                )
                return False

        # Run the async function
        try:
            return asyncio.run(send())
        except RuntimeError as e:
            # Handle case where there's already an event loop
            logger.warning(
                "RuntimeError in send_ad", extra={"error_type": type(e).__name__}
            )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(send())
            finally:
                loop.close()


@celery_app.task(name="common.messaging.tasks.send_menu")
@log_operation("send_menu")
def send_menu(user_id: int, text: str, options: List[Dict[str, str]], **kwargs):
    """
    Send a menu with options to a user via their preferred messaging platform.

    Args:
        user_id: Database user ID
        text: Menu title/description text
        options: List of option dictionaries with at least 'text' and 'value' keys
        **kwargs: Additional parameters for the menu
    """
    with log_context(logger, user_id=user_id, options_count=len(options)):

        async def send():
            try:
                # Get the platform-specific messenger
                platform, platform_id, messenger = (
                    await messaging_service.get_messenger_for_user(user_id)
                )

                if not platform or not platform_id or not messenger:
                    logger.error(
                        "No messaging platform found", extra={"user_id": user_id}
                    )
                    return False

                # Format user ID for the platform
                formatted_id = await messenger.format_user_id(platform_id)

                # Send the menu
                await messenger.send_menu(
                    user_id=formatted_id, text=text, options=options, **kwargs
                )

                logger.info(
                    "Menu sent successfully",
                    extra={
                        "user_id": user_id,
                        "platform": platform,
                        "options_count": len(options),
                    },
                )
                return True
            except Exception as e:
                logger.error(
                    "Error sending menu",
                    exc_info=True,
                    extra={"user_id": user_id, "error_type": type(e).__name__},
                )
                return False

        # Run the async function
        try:
            return asyncio.run(send())
        except RuntimeError as e:
            # Handle case where there's already an event loop
            logger.warning(
                "RuntimeError in send_menu", extra={"error_type": type(e).__name__}
            )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(send())
            finally:
                loop.close()


# --- New Consolidated Tasks ---


@celery_app.task(name="common.messaging.tasks.send_ad_with_extra_buttons")
@log_operation("send_ad_with_extra_buttons")
def send_ad_with_extra_buttons(
    user_id, text, s3_image_url, resource_url, ad_id, ad_external_id
):
    """Telegram-only implementation – sends an ad with inline buttons."""
    from common.messaging.unified_platform_utils import (
        resolve_user_id,
        get_messenger_instance,
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

    with log_context(logger, user_id=user_id, ad_id=ad_id):

        async def _async_send():
            # Resolve IDs (db_user_id may be None – that is fine)
            db_user_id, _, telegram_id = resolve_user_id(user_id)

            # Gather extra data (images/phones) from DB for button URLs
            with db_session() as db:
                ad_obj = db.query(Ad).get(ad_id)
                if not ad_obj:
                    logger.error("Ad not found", extra={"ad_id": ad_id})
                    return False

                image_urls = [img.image_url for img in ad_obj.images]
                phone_list = [p.phone for p in ad_obj.phones if p.phone]

            messenger = get_messenger_instance("telegram")
            if not messenger:
                logger.error("Telegram messenger unavailable")
                return False

            # Build inline keyboard
            markup = InlineKeyboardMarkup(row_width=2)
            if image_urls:
                imgs = ",".join(image_urls)
                markup.add(
                    InlineKeyboardButton(
                        "🖼 Більше фото",
                        web_app=WebAppInfo(
                            url=f"https://f3cc-178-150-42-6.ngrok-free.app/gallery?images={imgs}"
                        ),
                    )
                )

            if phone_list:
                phones = ",".join(phone_list)
                markup.add(
                    InlineKeyboardButton(
                        "📲 Подзвонити",
                        web_app=WebAppInfo(
                            url=f"https://f3cc-178-150-42-6.ngrok-free.app/phones?numbers={phones}"
                        ),
                    )
                )

            markup.add(
                InlineKeyboardButton(
                    "❤️ Додати в обрані", callback_data=f"add_fav:{ad_id}"
                ),
                InlineKeyboardButton(
                    "ℹ️ Повний опис", callback_data=f"show_more:{resource_url}"
                ),
            )

            try:
                await messenger.send_media(
                    user_id=telegram_id,
                    media_url=s3_image_url,
                    caption=text,
                    keyboard=markup,
                    parse_mode="Markdown",
                )
                logger.info(
                    "Ad sent successfully",
                    extra={"telegram_id": telegram_id, "ad_id": ad_id},
                )
                return True
            except Exception as e:
                logger.error(
                    "Failed to send ad",
                    exc_info=True,
                    extra={"error_type": type(e).__name__},
                )
                return False

        # Run the coroutine safely inside Celery worker
        try:
            import asyncio

            return asyncio.run(_async_send())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(_async_send())
            finally:
                loop.close()


@celery_app.task(name="common.messaging.tasks.process_show_more_description")
@log_operation("process_show_more_description")
def process_show_more_description(
    user_id: int, resource_url: str, message_id: int = None, platform: str = "telegram"
):
    """Fetch full description and send/edit message to user."""
    from common.messaging.unified_platform_utils import (
        safe_send_message,
        safe_edit_message_telegram,
    )
    from common.db.operations import get_full_ad_description

    with log_context(
        logger, user_id=user_id, resource_url=resource_url[:100], platform=platform
    ):

        async def run():
            # Fetch description
            description = get_full_ad_description(resource_url)
            if not description:
                description = "Повний опис недоступний. Спробуйте пізніше."

            text = f"ℹ️ Повний опис оголошення:\n\n{description}"

            if platform == "telegram" and message_id:
                # Try to edit original message first
                try:
                    await safe_edit_message_telegram(user_id, message_id, text)
                    return
                except Exception:
                    pass
            # Fallback: send new message
            await safe_send_message(user_id, text, platform=platform)

        try:
            return asyncio.run(run())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(run())
            finally:
                loop.close()


@celery_app.task(name="common.messaging.tasks.send_ad_multibot")
@log_operation("send_ad_multibot")
def send_ad_multibot(
    telegram_id: str,
    text: str,
    s3_image_url: str,
    resource_url: str,
    ad_id: int,
    external_id: str,
    bot_name: str,
    platform: str = "telegram"
):
    """
    Send ad notification via specific pool bot.
    This task runs in bot-specific queues for parallel processing.
    """
    from common.config_multibot import multibot_config
    from aiogram import Bot
    from common.messaging.telegram_messaging import TelegramMessaging
    import asyncio
    
    # Get bot configuration
    bot_config = multibot_config.get_bot_by_name(bot_name)
    if not bot_config:
        logger.error(f"Bot configuration not found: {bot_name}")
        return False
    
    try:
        # Create bot instance for this specific bot
        bot = Bot(token=bot_config.token)
        messaging = TelegramMessaging(bot)
        
        # Build ad data for send_ad method
        ad_data = {
            'id': ad_id,
            'external_id': external_id,
            'resource_url': resource_url
        }
        
        # Run async send in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(
            messaging.send_ad(
                user_id=telegram_id,
                ad_data=ad_data,
                image_url=s3_image_url
            )
        )
        
        loop.close()
        
        logger.info(
            "Ad sent via pool bot",
            extra={
                "telegram_id": telegram_id,
                "ad_id": ad_id,
                "bot_name": bot_name,
                "success": bool(result)
            }
        )
        
        return bool(result)
        
    except Exception as e:
        logger.error(
            "Failed to send ad via pool bot",
            exc_info=True,
            extra={
                "telegram_id": telegram_id,
                "ad_id": ad_id,
                "bot_name": bot_name,
                "error": str(e)
            }
        )
        return False
    finally:
        # Clean up bot session
        if 'bot' in locals():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(bot.close())
                loop.close()
            except:
                pass
