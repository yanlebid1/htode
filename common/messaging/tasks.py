# common/messaging/tasks.py

import asyncio
from typing import Dict, Any, Optional, List


from common.celery_app import celery_app
from common.db.operations import get_platform_ids_for_user, get_db_user_id_by_telegram_id, Ad
from .service import messaging_service
from common.db.session import db_session
from ..db.models import User
from common.utils.logging_config import log_operation, log_context, LogAggregator

# Import the messaging logger
from . import logger


@celery_app.task(name='common.messaging.tasks.send_notification')
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
                    user_id=user_id,
                    text=text,
                    **kwargs
                )

                if not success:
                    logger.error(f"Failed to send notification", extra={
                        'user_id': user_id,
                        'text_preview': text[:50]
                    })
                    return False

                logger.info("Notification sent successfully", extra={
                    'user_id': user_id,
                    'text_length': len(text)
                })
                return True
            except Exception as e:
                logger.error(f"Error sending notification", exc_info=True, extra={
                    'user_id': user_id,
                    'error_type': type(e).__name__
                })
                return False

        # Run the async function
        try:
            return asyncio.run(send())
        except RuntimeError as e:
            # Handle case where there's already an event loop
            logger.warning(f"RuntimeError in send_notification", extra={
                'error_type': type(e).__name__
            })
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(send())
            finally:
                loop.close()


@celery_app.task(name='common.messaging.tasks.send_ad')
@log_operation("send_ad")
def send_ad(user_id: int, ad_data: Dict[str, Any], image_url: Optional[str] = None, **kwargs):
    """
    Send an ad to a user via their preferred messaging platform.

    Args:
        user_id: Database user ID
        ad_data: Dictionary with ad data
        image_url: Optional URL for the primary ad image
        **kwargs: Additional parameters for the ad
    """
    with log_context(logger, user_id=user_id, ad_id=ad_data.get('id')):
        async def send():
            try:
                # Use the messaging service to send the ad
                success = await messaging_service.send_ad(
                    user_id=user_id,
                    ad_data=ad_data,
                    image_url=image_url,
                    **kwargs
                )

                if not success:
                    logger.error(f"Failed to send ad", extra={
                        'user_id': user_id,
                        'ad_id': ad_data.get('id')
                    })
                    return False

                logger.info("Ad sent successfully", extra={
                    'user_id': user_id,
                    'ad_id': ad_data.get('id'),
                    'has_image': bool(image_url)
                })
                return True
            except Exception as e:
                logger.error(f"Error sending ad", exc_info=True, extra={
                    'user_id': user_id,
                    'ad_id': ad_data.get('id'),
                    'error_type': type(e).__name__
                })
                return False

        # Run the async function
        try:
            return asyncio.run(send())
        except RuntimeError as e:
            # Handle case where there's already an event loop
            logger.warning(f"RuntimeError in send_ad", extra={
                'error_type': type(e).__name__
            })
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(send())
            finally:
                loop.close()


@celery_app.task(name='common.messaging.tasks.send_menu')
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
                platform, platform_id, messenger = await messaging_service.get_messenger_for_user(user_id)

                if not platform or not platform_id or not messenger:
                    logger.error(f"No messaging platform found", extra={'user_id': user_id})
                    return False

                # Format user ID for the platform
                formatted_id = await messenger.format_user_id(platform_id)

                # Send the menu
                await messenger.send_menu(
                    user_id=formatted_id,
                    text=text,
                    options=options,
                    **kwargs
                )

                logger.info("Menu sent successfully", extra={
                    'user_id': user_id,
                    'platform': platform,
                    'options_count': len(options)
                })
                return True
            except Exception as e:
                logger.error(f"Error sending menu", exc_info=True, extra={
                    'user_id': user_id,
                    'error_type': type(e).__name__
                })
                return False

        # Run the async function
        try:
            return asyncio.run(send())
        except RuntimeError as e:
            # Handle case where there's already an event loop
            logger.warning(f"RuntimeError in send_menu", extra={
                'error_type': type(e).__name__
            })
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(send())
            finally:
                loop.close()


@celery_app.task(name='common.messaging.tasks.send_cross_platform_message')
@log_operation("send_cross_platform_message")
def send_cross_platform_message(user_id: int, text: str, platforms: Optional[List[str]] = None, **kwargs):
    """
    Send a message to a user across multiple platforms.

    Args:
        user_id: Database user ID
        text: Message text
        platforms: Optional list of platforms to target (e.g., ["telegram"])
                  If None, will send to all available platforms for the user
        **kwargs: Additional parameters for the message
    """
    with log_context(logger, user_id=user_id, platforms=platforms, text_length=len(text)):
        async def send():
            aggregator = LogAggregator(logger, f"send_cross_platform_{user_id}")

            try:
                # Get all platform IDs for the user
                platform_ids = get_platform_ids_for_user(user_id)

                if not platform_ids:
                    logger.error(f"No platform IDs found", extra={'user_id': user_id})
                    return False

                # Determine which platforms to send to
                target_platforms = platforms or ["telegram"]
                sent_count = 0

                # Send to each platform that the user has an ID for
                for platform in target_platforms:
                    platform_id_key = f"{platform}_id"
                    if platform_ids.get(platform_id_key):
                        platform_id = platform_ids[platform_id_key]

                        # Get the messenger for this platform
                        messenger = messaging_service.get_messenger(platform)
                        if not messenger:
                            logger.warning(f"No messenger available", extra={'platform': platform})
                            aggregator.add_error("No messenger", {'platform': platform})
                            continue

                        # Format the user ID
                        formatted_id = await messenger.format_user_id(str(platform_id))

                        # Send the message
                        try:
                            await messenger.send_text(
                                user_id=formatted_id,
                                text=text,
                                **kwargs
                            )
                            sent_count += 1
                            aggregator.add_item({'platform': platform}, success=True)
                        except Exception as e:
                            logger.error(f"Error sending to platform", exc_info=True, extra={
                                'platform': platform,
                                'error_type': type(e).__name__
                            })
                            aggregator.add_error(str(e), {'platform': platform})

                aggregator.log_summary()

                logger.info("Cross-platform message sending completed", extra={
                    'user_id': user_id,
                    'sent_count': sent_count,
                    'total_platforms': len(target_platforms)
                })
                return sent_count > 0
            except Exception as e:
                logger.error(f"Error in send_cross_platform_message", exc_info=True, extra={
                    'user_id': user_id,
                    'error_type': type(e).__name__
                })
                return False

        # Run the async function
        try:
            return asyncio.run(send())
        except RuntimeError as e:
            # Handle case where there's already an event loop
            logger.warning(f"RuntimeError in send_cross_platform_message", extra={
                'error_type': type(e).__name__
            })
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(send())
            finally:
                loop.close()


# --- New Consolidated Tasks ---

@celery_app.task(name='common.messaging.tasks.send_ad_with_extra_buttons')
@log_operation("send_ad_with_extra_buttons")
def send_ad_with_extra_buttons(user_id, text, s3_image_url, resource_url, ad_id, ad_external_id, platform=None):
    """
    Consolidated task to send an ad with platform-specific buttons.
    Can be called directly with a platform-specific ID or database user ID.

    If a database ID is provided, it will send the ad to ALL platforms the user is registered on.

    Args:
        user_id: User's platform-specific ID or database user ID
        text: Ad description text
        s3_image_url: URL to the primary image
        resource_url: Original ad URL
        ad_id: Database ID of the ad
        ad_external_id: External ID of the ad
        platform: Optional platform override if user_id is platform-specific
    """
    with log_context(logger, user_id=user_id, ad_id=ad_id, platform=platform):
        # If platform is not specified, try to determine it
        if not platform:
            platform = "telegram"
                
        logger.info(f"Processing ad with platform: {platform}", extra={
            'user_id': user_id,
            'ad_id': ad_id,
            'platform': platform
        })
        
        async def send():
            # Make the platform variable from the outer scope accessible
            nonlocal platform

            logger.info(f"Sending ad with extra buttons", extra={
                'user_id': user_id,
                'ad_id': ad_id,
                'platform': platform
            })

            # First, determine the database user ID
            db_user_id = None
            
            # Check if user_id is a database ID or platform-specific ID
            if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()):
                # Treat it as a potential database user ID first
                db_user_id = int(user_id)

                # Verify if this db_user_id actually exists
                with db_session() as db:
                    user = db.query(User).get(db_user_id)
                    if not user:
                        # Doesn't exist as db_user_id, might be a platform ID
                        db_user_id = None

                if not db_user_id:
                    # Try to find the user by platform ID
                    db_user_id = get_db_user_id_by_telegram_id(user_id, messenger_type=platform)
                    logger.info(f"Resolved db_user_id from platform ID", extra={
                        'db_user_id': db_user_id,
                        'platform_id': user_id,
                        'platform': platform
                    })
            else:
                # This is definitely a platform-specific ID
                db_user_id = get_db_user_id_by_telegram_id(user_id, messenger_type=platform)
                logger.info(f"Resolved db_user_id from platform ID", extra={
                    'db_user_id': db_user_id,
                    'platform_id': user_id,
                    'platform': platform
                })

            # Fetch images, phones for the ad using the repository
            with db_session() as db:
                ad = db.query(Ad).get(ad_id)
                if not ad:
                    logger.error(f"Ad not found", extra={'ad_id': ad_id})
                    return

                image_urls = [img.image_url for img in ad.images]
                phone_list = [phone.phone for phone in ad.phones if phone.phone]

            # Prepare the ad data
            ad_data = {
                "id": ad_id,
                "external_id": ad_external_id,
                "resource_url": resource_url,
                "images": image_urls,
                "phones": phone_list,
                # Parse the text to extract other ad properties
                "price": int(text.split("Ціна: ")[1].split(" ")[0]) if "Ціна: " in text else 0,
                "city": text.split("Місто: ")[1].split("\n")[0] if "Місто: " in text else "",
                "address": text.split("Адреса: ")[1].split("\n")[0] if "Адреса: " in text else "",
                "rooms_count": text.split("Кіл-сть кімнат: ")[1].split("\n")[0] if "Кіл-сть кімнат: " in text else "",
                "square_feet": text.split("Площа: ")[1].split(" ")[0] if "Площа: " in text else "",
                "floor": text.split("Поверх: ")[1].split(" ")[0] if "Поверх: " in text else "",
                "total_floors": text.split("з ")[1].split("\n")[0] if "з " in text else ""
            }

            # Track if we successfully sent the message to any platform
            success = False

            # If we have a database user ID, try to send to all the user's platforms
            if db_user_id:
                # Get all platform IDs for this user
                platform_ids = get_platform_ids_for_user(db_user_id)
                logger.info(f"Retrieved platform IDs for user", extra={
                    'db_user_id': db_user_id,
                    'platforms': list(platform_ids.keys()) if platform_ids else []
                })

                if platform_ids:
                    # Send to each platform the user is registered on
                    for platform_name, platform_id_key in [
                        ("telegram", "telegram_id"),
                    ]:
                        if platform_ids.get(platform_id_key):
                            platform_id = platform_ids[platform_id_key]

                            logger.info(f"Attempting to send ad to platform", extra={
                                'db_user_id': db_user_id,
                                'platform': platform_name,
                                'platform_id': platform_id
                            })

                            # Get the messenger for this platform
                            try:
                                if platform_name == "telegram":
                                    from .telegram_messaging import TelegramMessaging
                                    from services.telegram_service.app.bot import bot
                                    messenger = TelegramMessaging(bot)
                                
                                else:
                                    logger.warning(f"Unknown platform", extra={'platform': platform_name})
                                    continue

                                # Send the ad using platform-specific formatting and buttons
                                if platform_name == "telegram":
                                    # Create Telegram-specific buttons
                                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

                                    markup = InlineKeyboardMarkup(row_width=2)

                                    # Process images for gallery button
                                    gallery_url = None
                                    if image_urls:
                                        image_str = ",".join(image_urls)
                                        gallery_url = f"https://f3cc-178-150-42-6.ngrok-free.app/gallery?images={image_str}"

                                    # Process phone numbers for call button
                                    phone_webapp_url = None
                                    if phone_list:
                                        phone_str = ",".join(phone_list)
                                        phone_webapp_url = f"https://f3cc-178-150-42-6.ngrok-free.app/phones?numbers={phone_str}"

                                    if gallery_url:
                                        markup.add(InlineKeyboardButton(
                                            text="🖼 Більше фото",
                                            web_app=WebAppInfo(url=gallery_url)
                                        ))

                                    if phone_webapp_url:
                                        markup.add(InlineKeyboardButton(
                                            text="📲 Подзвонити",
                                            web_app=WebAppInfo(url=phone_webapp_url)
                                        ))

                                    markup.add(
                                        InlineKeyboardButton("❤️ Додати в обрані", callback_data=f"add_fav:{ad_id}"),
                                        InlineKeyboardButton("ℹ️ Повний опис", callback_data=f"show_more:{resource_url}")
                                    )

                                    # Send media message with buttons
                                    await messenger.send_media(
                                        user_id=platform_id,
                                        media_url=s3_image_url,
                                        caption=text,
                                        keyboard=markup,
                                        parse_mode="Markdown"
                                    )
                                else:
                                    # For other platforms, use a simpler approach
                                    caption_with_link = f"{text}\n\n🔗 {resource_url}"
                                    await messenger.send_media(
                                        user_id=platform_id,
                                        media_url=s3_image_url,
                                        caption=caption_with_link
                                    )

                                logger.info(f"Media message sent successfully to platform", extra={
                                    'platform': platform_name,
                                    'platform_id': platform_id,
                                    'ad_id': ad_id
                                })

                                success = True

                            except Exception as e:
                                logger.error(f"Error sending ad to platform", exc_info=True, extra={
                                    'platform': platform_name,
                                    'platform_id': platform_id,
                                    'error_type': type(e).__name__,
                                    'error_message': str(e)
                                })

                                if platform_name == "telegram":
                                    # For Telegram, try sending as a fallback text message
                                    try:
                                        fallback_text = f"{text}\n\n🔗 {resource_url}"
                                        await messenger.send_text(
                                            user_id=platform_id,
                                            text=fallback_text,
                                            parse_mode="Markdown"
                                        )
                                        logger.info(f"Fallback text message sent successfully", extra={
                                            'platform': platform_name,
                                            'platform_id': platform_id
                                        })
                                        success = True
                                    except Exception as text_err:
                                        logger.error(f"Failed to send fallback text", exc_info=True, extra={
                                            'error_type': type(text_err).__name__
                                        })
                else:
                    logger.warning(f"No platform IDs found for user", extra={'db_user_id': db_user_id})

            # If we failed to resolve user or couldn't send to any platform, try direct approach
            if not success and platform == "telegram":
                # Use the direct telegram ID approach as a last resort
                telegram_id = user_id
                try:
                    from .telegram_messaging import TelegramMessaging
                    from services.telegram_service.app.bot import bot
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
                    
                    messenger = TelegramMessaging(bot)
                    
                    # Create buttons for the ad
                    markup = InlineKeyboardMarkup(row_width=2)
                    
                    # Process images for gallery button
                    gallery_url = None
                    if image_urls:
                        image_str = ",".join(image_urls)
                        gallery_url = f"https://f3cc-178-150-42-6.ngrok-free.app/gallery?images={image_str}"

                    # Process phone numbers for call button
                    phone_webapp_url = None
                    if phone_list:
                        phone_str = ",".join(phone_list)
                        phone_webapp_url = f"https://f3cc-178-150-42-6.ngrok-free.app/phones?numbers={phone_str}"

                    if gallery_url:
                        markup.add(InlineKeyboardButton(
                            text="🖼 Більше фото",
                            web_app=WebAppInfo(url=gallery_url)
                        ))

                    if phone_webapp_url:
                        markup.add(InlineKeyboardButton(
                            text="📲 Подзвонити",
                            web_app=WebAppInfo(url=phone_webapp_url)
                        ))

                    markup.add(
                        InlineKeyboardButton("❤️ Додати в обрані", callback_data=f"add_fav:{ad_id}"),
                        InlineKeyboardButton("ℹ️ Повний опис", callback_data=f"show_more:{resource_url}")
                    )
                    
                    # Add detailed logging for debugging the image URL
                    logger.info(f"DEBUGGING: Attempting to send media with URL", extra={
                        'user_id': user_id,
                        'telegram_id': telegram_id,
                        'ad_id': ad_id,
                        'image_url': s3_image_url,
                        'image_url_type': type(s3_image_url).__name__,
                        'image_url_length': len(s3_image_url) if isinstance(s3_image_url, str) else None
                    })

                    # If the URL starts with http, log more details
                    if isinstance(s3_image_url, str) and (s3_image_url.startswith('http://') or s3_image_url.startswith('https://')):
                        try:
                            # Log URL components
                            from urllib.parse import urlparse
                            parsed = urlparse(s3_image_url)
                            logger.info(f"DEBUGGING: Image URL components", extra={
                                'scheme': parsed.scheme,
                                'netloc': parsed.netloc,
                                'path': parsed.path,
                                'query': parsed.query
                            })
                            
                            # Try to get headers without downloading the full image
                            import requests
                            try:
                                response = requests.head(s3_image_url, timeout=3)
                                logger.info(f"DEBUGGING: Image URL HEAD response", extra={
                                    'status_code': response.status_code,
                                    'content_type': response.headers.get('Content-Type'),
                                    'content_length': response.headers.get('Content-Length')
                                })
                            except Exception as e:
                                logger.info(f"DEBUGGING: Failed to get HEAD response", extra={
                                    'error': str(e),
                                    'error_type': type(e).__name__
                                })
                        except Exception as e:
                            logger.info(f"DEBUGGING: Error parsing URL", extra={
                                'error': str(e)
                            })

                    # Check for cloudfront URLs and handle special cases
                    if isinstance(s3_image_url, str) and 'cloudfront.net' in s3_image_url:
                        logger.info(f"Processing cloudfront URL", extra={
                            'image_url': s3_image_url
                        })

                    # Send text with first image
                    await messenger.send_media(
                        user_id=telegram_id,
                        media_url=s3_image_url,
                        caption=text,
                        keyboard=markup,
                        parse_mode="Markdown"
                    )
                    
                    logger.info(f"Media message sent successfully", extra={
                        'ad_id': ad_id,
                        'telegram_id': telegram_id
                    })
                    logger.info(f"Successfully sent ad directly", extra={
                        'ad_id': ad_id,
                        'telegram_id': telegram_id
                    })
                    success = True
                except Exception as e:
                    logger.error(f"Error sending ad directly", exc_info=True, extra={
                        'ad_id': ad_id,
                        'telegram_id': telegram_id,
                        'error_type': type(e).__name__,
                        'error_message': str(e)
                    })

                    # Try sending as text only as a last resort
                    try:
                        from .telegram_messaging import TelegramMessaging
                        from services.telegram_service.app.bot import bot
                        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

                        messenger = TelegramMessaging(bot)

                        # Create buttons for the ad
                        markup = InlineKeyboardMarkup(row_width=2)
                        markup.add(
                            InlineKeyboardButton("❤️ Додати в обрані", callback_data=f"add_fav:{ad_id}"),
                            InlineKeyboardButton("ℹ️ Повний опис", callback_data=f"show_more:{resource_url}")
                        )

                        fallback_text = f"{text}\n\n🔗 {resource_url}"
                        await messenger.send_text(
                            user_id=telegram_id,
                            text=fallback_text,
                            keyboard=markup,
                            parse_mode="Markdown"
                        )

                        logger.info(f"Fallback text message sent successfully", extra={
                            'ad_id': ad_id,
                            'telegram_id': telegram_id
                        })
                        success = True
                    except Exception as text_e:
                        logger.error(f"Failed to send fallback text message", exc_info=True, extra={
                            'ad_id': ad_id,
                            'telegram_id': telegram_id,
                            'error_type': type(text_e).__name__
                        })

            if not success:
                logger.error(f"Failed to send ad through any method", extra={
                    'ad_id': ad_id,
                    'user_id': user_id
                })

        # Improved way to handle asyncio with Celery
        try:
            # First try to get the existing loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    raise RuntimeError("Loop is closed")
            except RuntimeError:
                # Create a new loop if no loop is available or if it's closed
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Run the async function and return the result
            if loop.is_running():
                # If loop is already running, we need to use a future
                future = asyncio.run_coroutine_threadsafe(send(), loop)
                return future.result()
            else:
                return loop.run_until_complete(send())
        except Exception as e:
            logger.error(f"Error in event loop handling", exc_info=True, extra={
                'error_type': type(e).__name__,
                'error_message': str(e)
            })
            # As a last resort, try asyncio.run()
            try:
                return asyncio.run(send())
            except Exception as run_error:
                logger.error(f"Failed with asyncio.run()", exc_info=True, extra={
                    'error_type': type(run_error).__name__
                })
                return False


@celery_app.task(name='common.messaging.tasks.process_show_more_description')
@log_operation("process_show_more_description")
def process_show_more_description(user_id: int, resource_url: str, message_id: int = None, platform: str = "telegram"):
    """Fetch full description and send/edit message to user."""
    from common.messaging.unified_platform_utils import safe_send_message, safe_edit_message_telegram
    from common.db.operations import get_full_ad_description

    with log_context(logger, user_id=user_id, resource_url=resource_url[:100], platform=platform):
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
