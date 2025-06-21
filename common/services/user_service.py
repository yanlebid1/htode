# common/services/user_service.py

from typing import Dict
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session
from common.db.models.user import User
from common.db.repositories.user_repository import UserRepository
from common.messaging.tasks import send_notification
from common.utils.logging_config import log_operation, log_context, LogAggregator

# Import the common services logger
from . import logger


class UserService:
    @staticmethod
    @log_operation("get_or_create_user")
    def get_or_create_user(
        db: Session, messenger_id: str, messenger_type: str = "telegram"
    ) -> int:
        """
        Get or create a user with the specified messenger ID.

        Args:
            db: Database session
            messenger_id: Messenger-specific ID
            messenger_type: Type of messenger (telegram,)

        Returns:
            User database ID
        """
        with log_context(
            logger, messenger_id=messenger_id, messenger_type=messenger_type
        ):
            # Get user by messenger ID
            user = UserRepository.get_by_messenger_id(db, messenger_id, messenger_type)

            if user:
                logger.info(
                    "Found existing user",
                    extra={
                        "messenger_type": messenger_type,
                        "messenger_id": messenger_id,
                        "user_id": user.id,
                    },
                )
                return user.id

            logger.info(
                "Creating new user",
                extra={"messenger_type": messenger_type, "messenger_id": messenger_id},
            )

            # Create a new user with free trial period
            free_until = datetime.now() + timedelta(days=7)

            # Create user with the appropriate messenger ID
            user = UserRepository.create_messenger_user(
                db, messenger_id, messenger_type, free_until
            )

            logger.info(
                "Created new user",
                extra={
                    "messenger_type": messenger_type,
                    "messenger_id": messenger_id,
                    "user_id": user.id,
                    "free_until": free_until.isoformat(),
                },
            )

            return user.id

    @staticmethod
    @log_operation("check_expiring_subscriptions")
    def check_expiring_subscriptions(db: Session) -> Dict[str, int]:
        """
        Check for expiring subscriptions and send reminders.

        Args:
            db: Database session

        Returns:
            Dictionary with counts of reminders sent
        """
        with log_context(logger):
            reminders_sent = 0
            aggregator = LogAggregator(logger, "check_expiring_subscriptions")

            # Check for subscriptions expiring in 3, 2, and 1 days
            for days in [3, 2, 1]:
                today = datetime.now().date()
                target_date = today + timedelta(days=days)

                # Get users whose subscription expires on the target date
                # Using ORM instead of raw SQL
                users = (
                    db.query(User)
                    .filter(func.date(User.subscription_until) == target_date)
                    .all()
                )

                logger.debug(
                    "Checking expiring subscriptions",
                    extra={
                        "days": days,
                        "target_date": target_date.isoformat(),
                        "users_count": len(users),
                    },
                )

                for user in users:
                    user_id = user.id
                    end_date = user.subscription_until.strftime("%d.%m.%Y")

                    # Determine template based on days remaining
                    if days == 1:
                        template = (
                            "⚠️ Ваша підписка закінчується завтра!\n\n"
                            "Дата закінчення: {end_date}\n\n"
                            "Щоб не втратити доступ до сервісу, оновіть підписку зараз."
                        )
                    else:
                        # Determine plural form
                        days_word = (
                            "день" if days == 1 else "дні" if days < 5 else "днів"
                        )
                        template = (
                            "⚠️ Нагадування про підписку\n\n"
                            "Ваша підписка закінчується через {days} "
                            "{days_word}.\n"
                            "Дата закінчення: {end_date}\n\n"
                            "Щоб продовжити користуватися сервісом, оновіть підписку."
                        )

                    # Send notification
                    send_notification.delay(
                        user_id=user_id,
                        template=template,
                        data={
                            "days": days,
                            "days_word": days_word,
                            "end_date": end_date,
                        },
                    )
                    reminders_sent += 1

                    aggregator.add_item(
                        {
                            "user_id": user_id,
                            "days_until_expiry": days,
                            "end_date": end_date,
                        },
                        success=True,
                    )

            # Notify on day of expiration
            users_today = (
                db.query(User).filter(func.date(User.subscription_until) == today).all()
            )

            logger.debug(
                "Checking same-day expiring subscriptions",
                extra={"today": today.isoformat(), "users_count": len(users_today)},
            )

            for user in users_today:
                user_id = user.id
                end_date = user.subscription_until.strftime("%d.%m.%Y %H:%M")

                send_notification.delay(
                    user_id=user_id,
                    template=(
                        "⚠️ Ваша підписка закінчується сьогодні!\n\n"
                        "Час закінчення: {end_date}\n\n"
                        "Щоб не втратити доступ до сервісу, оновіть підписку зараз."
                    ),
                    data={"end_date": end_date},
                )
                reminders_sent += 1

                aggregator.add_item(
                    {
                        "user_id": user_id,
                        "expiry_type": "same_day",
                        "end_date": end_date,
                    },
                    success=True,
                )

            aggregator.log_summary()

            logger.info(
                "Completed subscription expiry check",
                extra={"reminders_sent": reminders_sent},
            )

            return {"reminders_sent": reminders_sent}
