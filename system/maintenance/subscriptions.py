# system/maintenance/subscriptions.py

from ._common import (
    celery_app,
    db_session,
    User,
    func,
    time,
    datetime,
    timedelta,
    timezone,
    logger,
    log_operation,
    log_context,
    LogAggregator,
    SUBSCRIPTION_REMINDER_DAYS,
    Dict,
    Any,
)


@celery_app.task(name="system.maintenance.check_expiring_subscriptions")
@log_operation("check_expiring_subscriptions")
def check_expiring_subscriptions() -> Dict[str, Any]:
    """
    Check for expiring subscriptions and send reminders.
    """
    start_time = time.time()
    aggregator = LogAggregator(logger, "check_expiring_subscriptions")

    with log_context(logger, task="check_expiring_subscriptions"):
        try:
            with db_session() as db:
                # Get users with subscriptions expiring in the next few days
                reminders_sent = 0

                # Check for subscriptions expiring in 3, 2, and 1 days
                for days in SUBSCRIPTION_REMINDER_DAYS:
                    with log_context(logger, days_until_expiry=days):
                        future_date = datetime.now(timezone.utc) + timedelta(days=days, hours=1)
                        past_date = datetime.now(timezone.utc) + timedelta(days=days - 1)

                        # Get users whose subscription expires in the specified time window
                        users = (
                            db.query(User)
                            .filter(
                                User.subscription_until.isnot(None),
                                User.subscription_until > datetime.now(timezone.utc),
                                User.subscription_until < future_date,
                                User.subscription_until > past_date,
                            )
                            .all()
                        )

                        logger.info(
                            "Found users with expiring subscriptions",
                            extra={"days_until_expiry": days, "user_count": len(users)},
                        )

                        for user in users:
                            # Determine template based on days remaining
                            days_word = (
                                "день" if days == 1 else "дні" if days < 5 else "днів"
                            )
                            end_date = user.subscription_until.strftime("%d.%m.%Y")

                            # Build the appropriate template
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

                            # Send notification
                            from common.messaging.tasks import send_notification

                            send_notification.delay(
                                user_id=user.id,
                                template=template,
                                data={
                                    "days": days,
                                    "days_word": days_word,
                                    "end_date": end_date,
                                },
                            )
                            reminders_sent += 1
                            aggregator.add_item(
                                {"user_id": user.id, "days": days}, success=True
                            )

                # Also notify on the day of expiration
                today = datetime.now(timezone.utc).date()
                users_today = (
                    db.query(User)
                    .filter(
                        User.subscription_until.isnot(None),
                        func.date(User.subscription_until) == today,
                    )
                    .all()
                )

                logger.info(
                    "Found users with subscriptions expiring today",
                    extra={"user_count": len(users_today)},
                )

                for user in users_today:
                    end_date = user.subscription_until.strftime("%d.%m.%Y %H:%M")

                    # Send notification
                    from common.messaging.tasks import send_notification

                    send_notification.delay(
                        user_id=user.id,
                        template=(
                            "⚠️ Ваша підписка закінчується сьогодні!\n\n"
                            "Час закінчення: {end_date}\n\n"
                            "Щоб не втратити доступ до сервісу, оновіть підписку зараз."
                        ),
                        data={"end_date": end_date},
                    )
                    reminders_sent += 1
                    aggregator.add_item({"user_id": user.id, "days": 0}, success=True)

            execution_time = time.time() - start_time
            aggregator.log_summary()

            logger.info(
                "Checked expiring subscriptions",
                extra={
                    "reminders_sent": reminders_sent,
                    "execution_time": execution_time,
                },
            )

            return {
                "status": "success",
                "reminders_sent": reminders_sent,
                "execution_time_seconds": execution_time,
            }
        except Exception as e:
            logger.error(
                "Error checking expiring subscriptions",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            aggregator.add_error(str(e), {})
            aggregator.log_summary()
            return {
                "status": "error",
                "error": str(e),
                "execution_time_seconds": time.time() - start_time,
            }
