# services/telegram_service/app/tasks.py
from common.celery_app import celery_app
from aiogram.types import CallbackQuery

# Import service logger and logging utilities
from . import logger
from common.utils.logging_config import log_operation, log_context

# Import the bot for the callback handler
from .bot import dp, bot

# Import utility to send messages safely
from .utils.message_utils import safe_send_message


@celery_app.task(name="telegram_service.app.tasks.send_ad_with_extra_buttons")
def send_ad_with_extra_buttons(
    user_id, text, s3_image_url, resource_url, ad_id, ad_external_id
):
    # Just delegate to the common task
    from common.messaging.tasks import send_ad_with_extra_buttons as common_send_ad

    return common_send_ad(
        user_id,
        text,
        s3_image_url,
        resource_url,
        ad_id,
        ad_external_id,
        platform="telegram",
    )


@celery_app.task(name="telegram_service.app.tasks.send_subscription_notification")
def send_subscription_notification(
    telegram_id: int, notification_type: str, data: dict
):
    """Send subscription notification to Telegram user"""
    # Import messaging_service here to avoid circular import
    from common.messaging.service import messaging_service

    return messaging_service.send_subscription_notification(
        user_id=telegram_id,
        platform="telegram",
        notification_type=notification_type,
        data=data,
    )


# Add the missing tasks that Celery is looking for
@celery_app.task(name="telegram_service.app.tasks.send_subscription_reminders")
def send_subscription_reminders():
    """Send subscription reminders to users"""
    with log_context(logger, task_name="send_subscription_reminders"):
        logger.info("Starting subscription reminders task")

        # Import here to avoid circular dependencies
        from common.db.operations import get_users_for_reminders
        from common.messaging.service import messaging_service

        try:
            # Get users who need reminders
            users = get_users_for_reminders()
            logger.info(f"Found {len(users)} users for reminders")

            for user in users:
                telegram_id = user.get("telegram_id")
                if telegram_id:
                    reminder_text = (
                        "Ваша підписка закінчується незабаром. Не забудьте поновити!"
                    )

                    messaging_service.send_subscription_notification(
                        user_id=telegram_id,
                        platform="telegram",
                        notification_type="subscription_reminder",
                        data={"text": reminder_text},
                    )

            return {"status": "success", "users_notified": len(users)}

        except Exception as e:
            logger.error("Error in send_subscription_reminders", exc_info=True)
            return {"status": "error", "error": str(e)}


@celery_app.task(name="telegram_service.app.tasks.check_expiring_subscriptions")
def check_expiring_subscriptions():
    """Check for expiring subscriptions and notify users"""
    with log_context(logger, task_name="check_expiring_subscriptions"):
        logger.info("Starting check for expiring subscriptions")

        # Import here to avoid circular dependencies
        from common.db.operations import get_expiring_subscriptions
        from common.messaging.service import messaging_service

        try:
            # Get subscriptions expiring soon
            expiring_subscriptions = get_expiring_subscriptions()
            logger.info(f"Found {len(expiring_subscriptions)} expiring subscriptions")

            for subscription in expiring_subscriptions:
                subscription.get("user_id")
                telegram_id = subscription.get("telegram_id")

                if telegram_id:
                    days_left = subscription.get("days_left", 0)

                    if days_left <= 1:
                        notification_text = "Ваша підписка закінчується сьогодні! Поновіть зараз, щоб не втратити доступ."
                    elif days_left <= 3:
                        notification_text = f"Ваша підписка закінчується через {days_left} дні. Рекомендуємо поновити."
                    elif days_left <= 7:
                        notification_text = (
                            f"Ваша підписка закінчується через {days_left} днів."
                        )
                    else:
                        continue  # Don't notify for subscriptions expiring in more than 7 days

                    messaging_service.send_subscription_notification(
                        user_id=telegram_id,
                        platform="telegram",
                        notification_type="subscription_expiring",
                        data={"text": notification_text},
                    )

            return {
                "status": "success",
                "subscriptions_checked": len(expiring_subscriptions),
            }

        except Exception as e:
            logger.error("Error in check_expiring_subscriptions", exc_info=True)
            return {"status": "error", "error": str(e)}


# This handler needs to remain in the Telegram service as it's tied to the callback query handler
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("show_more:"))
@log_operation("show_more_description")
async def handle_show_more(callback_query: CallbackQuery):
    """
    Handle the show_more callback query and delegate to the unified task.
    This remains in the Telegram service as it's tied to the callback query handler.
    """
    with log_context(
        logger, user_id=callback_query.from_user.id, callback_data=callback_query.data
    ):
        # Extract the resource_url from the callback data
        try:
            _, resource_url = callback_query.data.split("show_more:")
        except Exception as e:
            logger.warning("Invalid callback data format", extra={"error": str(e)})
            await callback_query.answer("Невірні дані.", show_alert=True)
            return

        await callback_query.answer("Завантаження опису…")

        # Fetch description (cache/db) similar to favorites logic
        from common.utils.cache import get_entity_cache_key
        from common.db.operations import get_full_ad_description
        from common.utils.cache_managers import AdCacheManager

        cache_key = get_entity_cache_key("ad_description", resource_url)
        full_description = AdCacheManager.get(cache_key)
        if not full_description:
            full_description = get_full_ad_description(resource_url)
            if full_description:
                AdCacheManager.set(cache_key, full_description, 3600)

        if not full_description:
            await callback_query.answer("Немає додаткового опису.", show_alert=True)
            return

        original_caption = callback_query.message.caption or ""
        new_caption = (
            original_caption + "\n\n" + full_description if original_caption else None
        )

        try:
            if new_caption:
                await bot.edit_message_caption(
                    chat_id=callback_query.message.chat.id,
                    message_id=callback_query.message.message_id,
                    caption=new_caption,
                    parse_mode="Markdown",
                    reply_markup=callback_query.message.reply_markup,
                )
            else:
                # message had no caption (text), edit text
                new_text = (
                    (callback_query.message.text or "") + "\n\n" + full_description
                )
                await bot.edit_message_text(
                    chat_id=callback_query.message.chat.id,
                    message_id=callback_query.message.message_id,
                    text=new_text,
                    parse_mode="Markdown",
                    reply_markup=callback_query.message.reply_markup,
                )
            await callback_query.answer("Повний опис показано!")
        except Exception:
            # if edit fails send separate message
            await safe_send_message(
                chat_id=callback_query.from_user.id, text=full_description
            )
            await callback_query.answer("Повний опис надіслано окремим повідомленням!")
