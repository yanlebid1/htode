# common/messaging/consolidated_tasks.py

import asyncio

from typing import Dict, Any, List, Union

from common.celery_app import celery_app
from common.db.session import db_session
from common.db.models.ad import Ad
from common.db.repositories.ad_repository import AdRepository
from common.messaging.unified_platform_utils import safe_send_message
from common.messaging.service import messaging_service
from common.utils.logging_config import log_operation, log_context, LogAggregator

# Import the messaging logger
from . import logger


@celery_app.task(name='common.messaging.consolidated_tasks.send_notification')
@log_operation("send_notification_task")
def send_notification(user_id: Union[int, str], template: str, data: Dict[str, Any] = None,
                      platform: str = None, **kwargs):
    """
    Send a notification using a template.

    Args:
        user_id: User ID (database ID or platform-specific ID)
        template: Template name or direct text
        data: Data to format the template with
        platform: Optional platform override
        **kwargs: Additional options for the message
    """

    async def send():
        with log_context(logger, user_id=user_id, platform=platform, template=template[:50]):
            try:
                # Format template if data is provided
                text = template
                if data:
                    try:
                        # Try to interpolate using format() method
                        text = template.format(**data)
                    except (KeyError, ValueError):
                        # Fall back to direct template
                        logger.warning(f"Unable to format template", extra={
                            'template': template[:100],
                            'data': str(data)[:100]
                        })

                # Send the notification
                success = await safe_send_message(
                    user_id=user_id,
                    text=text,
                    platform=platform,
                    **kwargs
                )

                logger.info("Notification sent", extra={
                    'user_id': user_id,
                    'platform': platform,
                    'success': success
                })

                return success
            except Exception as e:
                logger.error(f"Error sending notification", exc_info=True, extra={
                    'user_id': user_id,
                    'platform': platform,
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


@celery_app.task(name='common.messaging.consolidated_tasks.send_property_notification')
@log_operation("send_property_notification_task")
def send_property_notification(user_id: Union[int, str], ad_id: int, platform: str = None):
    """
    Send a property notification with all necessary data and buttons.

    Args:
        user_id: User ID (database ID or platform-specific ID)
        ad_id: Database ID of the ad
        platform: Optional platform override
    """

    async def send():
        with log_context(logger, user_id=user_id, ad_id=ad_id, platform=platform):
            try:
                # Get complete ad data using repository
                with db_session() as db:
                    ad_data = AdRepository.get_full_ad_data(db, ad_id)

                if not ad_data:
                    logger.error(f"Ad data not found", extra={
                        'ad_id': ad_id
                    })
                    return False

                # Get the primary image
                with db_session() as db:
                    images = AdRepository.get_ad_images(db, ad_id)

                primary_image = images[0] if images else None

                # Send via the unified messaging service
                if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()):
                    # This is a database user ID, we can use the messaging service directly
                    db_user_id = int(user_id)
                    success = await messaging_service.send_ad(
                        user_id=db_user_id,
                        ad_data=ad_data,
                        image_url=primary_image
                    )
                else:
                    # This is a platform-specific ID
                    platform_name = platform or "telegram"  # Default to telegram if not specified

                    # Get the messenger for this platform
                    messenger = messaging_service.get_messenger(platform_name)
                    if not messenger:
                        logger.error(f"No messenger available", extra={
                            'platform': platform_name
                        })
                        return False

                    # Format the user ID
                    formatted_id = await messenger.format_user_id(user_id)

                    # Send the ad
                    await messenger.send_ad(
                        user_id=formatted_id,
                        ad_data=ad_data,
                        image_url=primary_image
                    )
                    success = True

                logger.info("Property notification sent", extra={
                    'user_id': user_id,
                    'ad_id': ad_id,
                    'platform': platform,
                    'success': success
                })

                return success
            except Exception as e:
                logger.error(f"Error sending property notification", exc_info=True, extra={
                    'user_id': user_id,
                    'ad_id': ad_id,
                    'platform': platform,
                    'error_type': type(e).__name__
                })
                return False

    # Run the async function
    try:
        return asyncio.run(send())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in send_property_notification", extra={
            'error_type': type(e).__name__
        })
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send())
        finally:
            loop.close()


@celery_app.task(name='common.messaging.consolidated_tasks.send_subscription_reminder')
@log_operation("send_subscription_reminder_task")
def send_subscription_reminder():
    """
    Check for expiring subscriptions and send reminders.
    Replaces platform-specific implementations.
    """
    with log_context(logger, task="subscription_reminder"):
        try:
            reminders_sent = 0
            aggregator = LogAggregator(logger, "send_subscription_reminder")

            # Check for subscriptions expiring in 3, 2, and 1 days
            for days in [3, 2, 1]:
                with log_context(logger, days_until_expiry=days):
                    # Find users whose subscription expires in exactly `days` days
                    with db_session() as db:
                        # Use repository to find users with expiring subscriptions
                        from sqlalchemy import func
                        from datetime import datetime, timedelta
                        from common.db.models.user import User

                        future_date = datetime.now() + timedelta(days=days, hours=1)
                        past_date = datetime.now() + timedelta(days=days - 1)

                        users = db.query(User.id, User.subscription_until).filter(
                            User.subscription_until.isnot(None),
                            User.subscription_until > datetime.now(),
                            User.subscription_until < future_date,
                            User.subscription_until > past_date
                        ).all()

                    logger.info(f"Found users with expiring subscriptions", extra={
                        'days_until_expiry': days,
                        'user_count': len(users)
                    })

                    for user in users:
                        user_id = user.id
                        end_date = user.subscription_until.strftime("%d.%m.%Y")

                        # Determine the template based on days remaining
                        if days == 1:
                            template = (
                                "⚠️ Ваша підписка закінчується завтра!\n\n"
                                "Дата закінчення: {end_date}\n\n"
                                "Щоб не втратити доступ до сервісу, оновіть підписку зараз."
                            )
                        else:
                            template = (
                                "⚠️ Нагадування про підписку\n\n"
                                "Ваша підписка закінчується через {days} "
                                "{days_word}.\n"
                                "Дата закінчення: {end_date}\n\n"
                                "Щоб продовжити користуватися сервісом, оновіть підписку."
                            )

                        # Determine plural form
                        days_word = "день" if days == 1 else "дні" if days < 5 else "днів"

                        # Send notification using the consolidated task
                        send_notification.delay(
                            user_id=user_id,
                            template=template,
                            data={
                                "days": days,
                                "days_word": days_word,
                                "end_date": end_date
                            }
                        )
                        reminders_sent += 1
                        aggregator.add_item({
                            'user_id': user_id,
                            'days': days,
                            'end_date': end_date
                        }, success=True)

            # Also notify on the day of expiration
            with db_session() as db:
                from datetime import date
                users_today = db.query(User.id, User.subscription_until).filter(
                    User.subscription_until.isnot(None),
                    func.date(User.subscription_until) == date.today()
                ).all()

            logger.info("Found users with subscriptions expiring today", extra={
                'user_count': len(users_today)
            })

            for user in users_today:
                user_id = user.id
                end_date = user.subscription_until.strftime("%d.%m.%Y %H:%M")

                # Send notification
                send_notification.delay(
                    user_id=user_id,
                    template=(
                        "⚠️ Ваша підписка закінчується сьогодні!\n\n"
                        "Час закінчення: {end_date}\n\n"
                        "Щоб не втратити доступ до сервісу, оновіть підписку зараз."
                    ),
                    data={"end_date": end_date}
                )
                reminders_sent += 1
                aggregator.add_item({
                    'user_id': user_id,
                    'type': 'same_day',
                    'end_date': end_date
                }, success=True)

            aggregator.log_summary()

            logger.info("Subscription reminder task completed", extra={
                'reminders_sent': reminders_sent
            })

            return {"status": "success", "reminders_sent": reminders_sent}
        except Exception as e:
            logger.error(f"Error sending subscription reminders", exc_info=True, extra={
                'error_type': type(e).__name__
            })
            return {"status": "error", "error": str(e)}


@celery_app.task(name='common.messaging.consolidated_tasks.send_batch_notifications')
@log_operation("send_batch_notifications_task")
def send_batch_notifications(user_ids: List[int], template: str, data: Dict[str, Any] = None,
                             batch_size: int = 50, **kwargs):
    """
    Send notifications to a batch of users.

    Args:
        user_ids: List of database user IDs
        template: Template name or direct text
        data: Data to format the template with
        batch_size: How many users to process in each batch
        **kwargs: Additional options for the messages
    """
    with log_context(logger, user_count=len(user_ids), batch_size=batch_size):
        results = {
            "total": len(user_ids),
            "success": 0,
            "failed": 0
        }

        aggregator = LogAggregator(logger, f"send_batch_notifications_{len(user_ids)}_users")

        # Process in batches to avoid overwhelming the system
        for i in range(0, len(user_ids), batch_size):
            batch = user_ids[i:i + batch_size]

            logger.info(f"Processing notification batch", extra={
                'batch_number': i // batch_size + 1,
                'batch_size': len(batch),
                'total_users': len(user_ids)
            })

            for user_id in batch:
                try:
                    send_notification.delay(
                        user_id=user_id,
                        template=template,
                        data=data,
                        **kwargs
                    )
                    results["success"] += 1
                    aggregator.add_item({'user_id': user_id}, success=True)
                except Exception as e:
                    logger.error(f"Error sending notification", exc_info=True, extra={
                        'user_id': user_id,
                        'error_type': type(e).__name__
                    })
                    results["failed"] += 1
                    aggregator.add_error(str(e), {'user_id': user_id})

        aggregator.log_summary()

        logger.info("Batch notifications completed", extra=results)
        return results


@celery_app.task(name='common.messaging.consolidated_tasks.get_description_and_notify')
@log_operation("get_description_and_notify_task")
def get_description_and_notify(user_id: Union[int, str], resource_url: str, platform: str = None):
    """
    Get the full description of an ad and send it to the user.

    Args:
        user_id: User ID (database ID or platform-specific ID)
        resource_url: URL of the ad to get description for
        platform: Optional platform override
    """

    async def process():
        with log_context(logger, user_id=user_id, resource_url=resource_url, platform=platform):
            try:
                # Get the full description using repository
                with db_session() as db:
                    # First get the ad by resource URL
                    ad = AdRepository.get_by_resource_url(db, resource_url)
                    description = ad.description if ad else None

                if not description:
                    logger.warning(f"No description found", extra={
                        'resource_url': resource_url
                    })
                    await safe_send_message(
                        user_id=user_id,
                        text="Немає додаткового опису.",
                        platform=platform
                    )
                    return False

                # Send the description
                success = await safe_send_message(
                    user_id=user_id,
                    text=description,
                    platform=platform
                )

                logger.info("Description sent", extra={
                    'user_id': user_id,
                    'resource_url': resource_url,
                    'platform': platform,
                    'success': success
                })

                return success
            except Exception as e:
                logger.error(f"Error getting and sending description", exc_info=True, extra={
                    'user_id': user_id,
                    'resource_url': resource_url,
                    'platform': platform,
                    'error_type': type(e).__name__
                })
                return False

    # Run the async function
    try:
        return asyncio.run(process())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in get_description_and_notify", extra={
            'error_type': type(e).__name__
        })
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(process())
        finally:
            loop.close()


@celery_app.task(name='common.messaging.consolidated_tasks.process_new_listings')
@log_operation("process_new_listings_task")
def process_new_listings(ad_ids: List[int], max_notifications_per_user: int = 5):
    """
    Process new listings and send notifications to matching users.

    Args:
        ad_ids: List of new ad IDs
        max_notifications_per_user: Maximum notifications to send to each user
    """
    with log_context(logger, ad_count=len(ad_ids), max_notifications_per_user=max_notifications_per_user):
        try:
            aggregator = LogAggregator(logger, f"process_new_listings_{len(ad_ids)}_ads")

            # Find matching users for all ads
            matching_users = {}

            with db_session() as db:
                for ad_id in ad_ids:
                    ad = db.query(Ad).get(ad_id)
                    if ad:
                        # Use the repository to find users for this ad
                        matching_users[ad_id] = AdRepository.find_users_for_ad(db, ad)
                        aggregator.add_item({'ad_id': ad_id, 'matching_users': len(matching_users[ad_id])},
                                            success=True)

            # Track notifications sent to each user to avoid spamming
            notifications_sent = {}
            sent_count = 0

            # Process each ad
            for ad_id in ad_ids:
                user_ids = matching_users.get(ad_id, [])

                for user_id in user_ids:
                    # Check if user has reached maximum notifications
                    if notifications_sent.get(user_id, 0) >= max_notifications_per_user:
                        logger.debug("User reached notification limit", extra={
                            'user_id': user_id,
                            'notifications_sent': notifications_sent[user_id],
                            'limit': max_notifications_per_user
                        })
                        continue

                    # Send notification
                    send_property_notification.delay(user_id=user_id, ad_id=ad_id)

                    # Increment counter
                    notifications_sent[user_id] = notifications_sent.get(user_id, 0) + 1
                    sent_count += 1

            aggregator.log_summary()

            results = {
                "status": "success",
                "ads_processed": len(ad_ids),
                "notifications_sent": sent_count,
                "users_notified": len(notifications_sent)
            }

            logger.info("New listings processed", extra=results)
            return results

        except Exception as e:
            logger.error(f"Error processing new listings", exc_info=True, extra={
                'ad_count': len(ad_ids),
                'error_type': type(e).__name__
            })
            return {"status": "error", "error": str(e)}