# common/db/repositories/user_repository.py

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from common.db.models.user import User
from common.utils.cache_managers import UserCacheManager
from common.utils.logging_config import log_operation, log_context, LogAggregator

# Import the repository logger
from . import logger


class UserRepository:
    """Repository for user operations"""

    @staticmethod
    @log_operation("get_by_id")
    def get_by_id(db: Session, user_id: int) -> Optional[User]:
        """Get user by database ID"""
        with log_context(logger, user_id=user_id):
            user = db.query(User).filter(User.id == user_id).first()

            if user:
                logger.debug("Found user", extra={'user_id': user_id})
            else:
                logger.debug("User not found", extra={'user_id': user_id})

            return user

    @staticmethod
    @log_operation("get_by_messenger_id")
    def get_by_messenger_id(
            db: Session, messenger_id: str, messenger_type: str = "telegram"
    ) -> Optional[User]:
        """Get user by messenger ID"""
        with log_context(logger, messenger_id=messenger_id, messenger_type=messenger_type):
            filter_kwargs = {f"{messenger_type}_id": messenger_id}
            user = db.query(User).filter_by(**filter_kwargs).first()

            if user:
                logger.debug("Found user by messenger ID", extra={
                    'messenger_type': messenger_type,
                    'messenger_id': messenger_id,
                    'user_id': user.id
                })
            else:
                logger.debug("User not found by messenger ID", extra={
                    'messenger_type': messenger_type,
                    'messenger_id': messenger_id
                })

            return user

    @staticmethod
    @log_operation("get_by_phone")
    def get_by_phone(db: Session, phone_number: str) -> Optional[User]:
        """Get user by phone number"""
        with log_context(logger, phone_number=phone_number[:5] + "..."):
            user = db.query(User).filter(User.phone_number == phone_number).first()

            if user:
                logger.debug("Found user by phone", extra={
                    'phone_number': phone_number[:5] + "...",
                    'user_id': user.id
                })
            else:
                logger.debug("User not found by phone", extra={
                    'phone_number': phone_number[:5] + "..."
                })

            return user

    @staticmethod
    @log_operation("get_by_email")
    def get_by_email(db: Session, email: str) -> Optional[User]:
        """Get user by email"""
        with log_context(logger, email=email[:5] + "..."):
            user = db.query(User).filter(User.email == email.lower()).first()

            if user:
                logger.debug("Found user by email", extra={
                    'email': email[:5] + "...",
                    'user_id': user.id
                })
            else:
                logger.debug("User not found by email", extra={
                    'email': email[:5] + "..."
                })

            return user

    @staticmethod
    @log_operation("get_or_create")
    def get_or_create(
            db: Session, messenger_id: str, messenger_type: str = "telegram"
    ) -> User:
        """Get or create a user with messenger ID"""
        with log_context(logger, messenger_id=messenger_id, messenger_type=messenger_type):
            user = User.get_or_create(db, messenger_id, messenger_type)

            logger.info("Got or created user", extra={
                'messenger_type': messenger_type,
                'messenger_id': messenger_id,
                'user_id': user.id,
                'is_new': not hasattr(user, 'created_at') or user.created_at == datetime.now()
            })

            return user

    @staticmethod
    @log_operation("start_free_subscription")
    def start_free_subscription(db: Session, user_id: int) -> bool:
        """Start a free subscription for the user"""
        with log_context(logger, user_id=user_id):
            user = UserRepository.get_by_id(db, user_id)
            if not user:
                logger.warning("Cannot start free subscription - user not found", extra={'user_id': user_id})
                return False

            old_date = user.free_until
            user.free_until = datetime.now() + timedelta(days=7)
            db.commit()

            # Invalidate cache using the cache manager
            UserCacheManager.invalidate_all(user_id)

            logger.info("Started free subscription", extra={
                'user_id': user_id,
                'old_date': old_date.isoformat() if old_date else None,
                'new_date': user.free_until.isoformat()
            })

            return True

    @staticmethod
    @log_operation("get_subscription_status")
    def get_subscription_status(db: Session, user_id: int) -> Dict[str, Any]:
        """Get subscription status for a user with caching"""
        with log_context(logger, user_id=user_id):
            # Try to get from cache first using the cache manager
            cached_status = UserCacheManager.get_subscription_status(user_id)
            if cached_status:
                logger.debug("Cache hit for subscription status", extra={'user_id': user_id})
                return cached_status

            # Cache miss, calculate status
            user = UserRepository.get_by_id(db, user_id)
            if not user:
                logger.warning("Cannot get subscription status - user not found", extra={'user_id': user_id})
                return {"active": False}

            now = datetime.now()
            free_until = user.free_until
            subscription_until = user.subscription_until

            free_active = free_until and free_until > now
            paid_active = subscription_until and subscription_until > now

            status = {
                "active": free_active or paid_active,
                "free_active": free_active,
                "paid_active": paid_active,
                "free_until": free_until.isoformat() if free_until else None,
                "subscription_until": subscription_until.isoformat() if subscription_until else None
            }

            # Cache the result
            UserCacheManager.set_subscription_status(user_id, status)

            logger.debug("Retrieved subscription status", extra={
                'user_id': user_id,
                'status': status
            })

            return status

    @staticmethod
    @log_operation("update_last_active")
    def update_last_active(db: Session, user_id: int) -> bool:
        """Update the user's last active timestamp"""
        with log_context(logger, user_id=user_id):
            user = UserRepository.get_by_id(db, user_id)
            if not user:
                logger.warning("Cannot update last active - user not found", extra={'user_id': user_id})
                return False

            old_time = user.last_active
            user.last_active = datetime.now()
            db.commit()

            logger.debug("Updated last active time", extra={
                'user_id': user_id,
                'old_time': old_time.isoformat() if old_time else None,
                'new_time': user.last_active.isoformat()
            })

            return True

    @staticmethod
    @log_operation("create_messenger_user")
    def create_messenger_user(
            db: Session, messenger_id: str, messenger_type: str, free_until: datetime
    ) -> User:
        """Create a new user with messenger ID"""
        with log_context(logger, messenger_id=messenger_id, messenger_type=messenger_type):
            messenger_field = f"{messenger_type}_id"
            user_data = {
                messenger_field: messenger_id,
                "free_until": free_until
            }
            user = User(**user_data)
            db.add(user)
            db.commit()
            db.refresh(user)

            logger.info("Created new messenger user", extra={
                'messenger_type': messenger_type,
                'messenger_id': messenger_id,
                'user_id': user.id,
                'free_until': free_until.isoformat()
            })

            return user

    @staticmethod
    @log_operation("update_messenger_id")
    def update_messenger_id(
            db: Session, user_id: int, messenger_id: str, messenger_type: str
    ) -> bool:
        """Update/set a messenger ID for a user"""
        with log_context(logger, user_id=user_id, messenger_id=messenger_id, messenger_type=messenger_type):
            user = UserRepository.get_by_id(db, user_id)
            if not user:
                logger.warning("Cannot update messenger ID - user not found", extra={'user_id': user_id})
                return False

            old_value = getattr(user, f"{messenger_type}_id")
            setattr(user, f"{messenger_type}_id", messenger_id)
            db.commit()

            logger.info("Updated messenger ID", extra={
                'user_id': user_id,
                'messenger_type': messenger_type,
                'old_value': old_value,
                'new_value': messenger_id
            })

            return True

    @staticmethod
    @log_operation("link_phone_number")
    def link_phone_number(
            db: Session, user_id: int, phone_number: str, verified: bool = False
    ) -> bool:
        """Link a phone number to a user"""
        with log_context(logger, user_id=user_id, phone_number=phone_number[:5] + "..."):
            user = UserRepository.get_by_id(db, user_id)
            if not user:
                logger.warning("Cannot link phone number - user not found", extra={'user_id': user_id})
                return False

            old_phone = user.phone_number
            user.phone_number = phone_number
            user.phone_verified = verified
            db.commit()

            logger.info("Linked phone number", extra={
                'user_id': user_id,
                'old_phone': old_phone[:5] + "..." if old_phone else None,
                'new_phone': phone_number[:5] + "...",
                'verified': verified
            })

            return True

    @staticmethod
    @log_operation("get_users_with_expiring_subscription")
    def get_users_with_expiring_subscription(db: Session, days: int) -> List[User]:
        """
        Get users whose subscription is expiring in the specified number of days.
        """
        with log_context(logger, days=days):
            future_date = datetime.now() + timedelta(days=days, hours=1)
            past_date = datetime.now() + timedelta(days=days - 1)

            users = db.query(User).filter(
                User.subscription_until.isnot(None),
                User.subscription_until > datetime.now(),
                User.subscription_until < future_date,
                User.subscription_until > past_date
            ).all()

            logger.debug("Found users with expiring subscriptions", extra={
                'days': days,
                'user_count': len(users)
            })

            return users

    @staticmethod
    @log_operation("get_active_users")
    def get_active_users(db: Session, days: int = 7, limit: int = 100) -> List[User]:
        """
        Get users who have been active within the specified number of days.
        """
        with log_context(logger, days=days, limit=limit):
            cutoff_date = datetime.now() - timedelta(days=days)
            users = db.query(User).filter(
                User.last_active > cutoff_date
            ).limit(limit).all()

            logger.debug("Found active users", extra={
                'days': days,
                'limit': limit,
                'user_count': len(users)
            })

            return users

    @staticmethod
    @log_operation("update_subscription_end_date")
    def update_subscription_end_date(
            db: Session, user_id: int, subscription_until: datetime
    ) -> bool:
        """Update user subscription end date"""
        with log_context(logger, user_id=user_id, subscription_until=subscription_until.isoformat()):
            user = UserRepository.get_by_id(db, user_id)
            if not user:
                logger.warning("Cannot update subscription end date - user not found", extra={'user_id': user_id})
                return False

            old_date = user.subscription_until
            user.subscription_until = subscription_until
            db.commit()

            # Invalidate cache using the cache manager
            UserCacheManager.invalidate_all(user_id)

            logger.info("Updated subscription end date", extra={
                'user_id': user_id,
                'old_date': old_date.isoformat() if old_date else None,
                'new_date': subscription_until.isoformat()
            })

            return True

    @staticmethod
    @log_operation("get_user_id_by_telegram_id")
    def get_user_id_by_telegram_id(db: Session, telegram_id: str) -> Optional[int]:
        """Get database user ID from Telegram ID"""
        with log_context(logger, telegram_id=telegram_id):
            user = db.query(User).filter(User.telegram_id == telegram_id).first()

            if user:
                logger.debug("Found user ID by telegram ID", extra={
                    'telegram_id': telegram_id,
                    'user_id': user.id
                })
                return user.id
            else:
                logger.debug("User ID not found by telegram ID", extra={
                    'telegram_id': telegram_id
                })
                return None

    @staticmethod
    @log_operation("get_subscription_until")
    def get_subscription_until(db: Session, user_id: int, free: bool = False) -> Optional[str]:
        """Get subscription expiration date for a user"""
        with log_context(logger, user_id=user_id, free=free):
            user = db.query(User).filter(User.id == user_id).first()

            if not user:
                logger.debug("User not found for subscription until", extra={'user_id': user_id})
                return None

            # Get the appropriate date field
            date_field = user.free_until if free else user.subscription_until

            if date_field:
                result = date_field.strftime("%d.%m.%Y")
                logger.debug("Retrieved subscription until date", extra={
                    'user_id': user_id,
                    'free': free,
                    'date': result
                })
                return result

            logger.debug("No subscription until date found", extra={
                'user_id': user_id,
                'free': free
            })
            return None

    @staticmethod
    @log_operation("get_admin_user")
    def get_admin_user(db: Session) -> Optional[User]:
        """
        Get an admin user (first one found).
        """
        with log_context(logger):
            # TODO: Implement admin user logic
            logger.warning("Admin user logic not implemented")
            return None

    @staticmethod
    @log_operation("create_user")
    def create_user(db: Session, user_data: Dict[str, Any]) -> User:
        """
        Create a new user with the provided data.
        """
        with log_context(logger, user_data_keys=list(user_data.keys())):
            user = User(**user_data)
            db.add(user)
            db.commit()
            db.refresh(user)

            logger.info("Created new user", extra={
                'user_id': user.id,
                'has_telegram': bool(user.telegram_id),
                'has_email': bool(user.email),
                'has_phone': bool(user.phone_number)
            })

            return user