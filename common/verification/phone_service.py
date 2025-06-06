# common/verification/phone_service.py
from typing import Tuple, Optional, Dict, Any

from common.db.session import db_session
from common.db.repositories.verification_repository import VerificationRepository
from common.db.repositories.user_repository import UserRepository
from common.utils.logging_config import log_operation, log_context

# Import the common verification logger
from . import logger


@log_operation("create_verification_code")
def create_verification_code(phone_number: str) -> str:
    """
    Create a verification code for a phone number

    Args:
        phone_number: Phone number to verify

    Returns:
        Generated verification code
    """
    with log_context(logger, phone_number=phone_number):
        with db_session() as db:
            code = VerificationRepository.create_verification_code(db, phone_number)
            logger.info("Created verification code", extra={
                'phone_number': phone_number,
                'code_length': len(code) if code else 0
            })
            return code


@log_operation("verify_code")
def verify_code(phone_number: str, code: str) -> Tuple[bool, str]:
    """
    Verify a code for a phone number

    Args:
        phone_number: Phone number to verify
        code: Verification code to check

    Returns:
        Tuple of (success, error_message)
    """
    with log_context(logger, phone_number=phone_number):
        try:
            with db_session() as db:
                is_valid = VerificationRepository.verify_code(db, phone_number, code)

                if is_valid:
                    logger.info("Code verification successful", extra={
                        'phone_number': phone_number
                    })
                    return True, ""
                else:
                    logger.warning("Code verification failed", extra={
                        'phone_number': phone_number,
                        'error': 'invalid_or_expired_code'
                    })
                    return False, "Неправильний код або термін дії коду закінчився"
        except Exception as e:
            logger.error("Error verifying code", exc_info=True, extra={
                'phone_number': phone_number,
                'error_type': type(e).__name__
            })
            return False, "Помилка при перевірці коду"


@log_operation("get_user_by_phone")
def get_user_by_phone(phone_number: str) -> Optional[Dict[str, Any]]:
    """
    Get user by phone number

    Args:
        phone_number: Phone number to look up

    Returns:
        User data dictionary or None if not found
    """
    with log_context(logger, phone_number=phone_number):
        try:
            with db_session() as db:
                user = UserRepository.get_by_phone(db, phone_number)

                if not user:
                    logger.debug("No user found with phone number", extra={
                        'phone_number': phone_number
                    })
                    return None

                user_data = {
                    "id": user.id,
                    "telegram_id": user.telegram_id,
                    "phone_number": user.phone_number,
                    "email": user.email
                }

                logger.info("Found user by phone number", extra={
                    'phone_number': phone_number,
                    'user_id': user.id,
                    'has_telegram': bool(user.telegram_id),
                    'has_email': bool(user.email)
                })

                return user_data
        except Exception as e:
            logger.error("Error getting user by phone", exc_info=True, extra={
                'phone_number': phone_number,
                'error_type': type(e).__name__
            })
            return None


@log_operation("link_messenger_account")
def link_messenger_account(phone_number: str, messenger_type: str, messenger_id: str) -> Optional[int]:
    """
    Link a messenger account to a user with this phone number

    Args:
        phone_number: Phone number
        messenger_type: Type of messenger ("telegram",)
        messenger_id: Messenger-specific ID

    Returns:
        User ID if successful, None otherwise
    """
    with log_context(logger, phone_number=phone_number, messenger_type=messenger_type, messenger_id=messenger_id):
        try:
            with db_session() as db:
                # Find user by phone
                user = UserRepository.get_by_phone(db, phone_number)

                if user:
                    # Update messenger ID
                    if messenger_type == "telegram":
                        user.telegram_id = messenger_id

                    # Verify phone number if not already verified
                    if not user.phone_verified:
                        user.phone_verified = True

                    db.commit()

                    logger.info("Linked messenger account to existing user", extra={
                        'phone_number': phone_number,
                        'messenger_type': messenger_type,
                        'messenger_id': messenger_id,
                        'user_id': user.id,
                        'phone_verified_changed': not user.phone_verified
                    })

                    return user.id
                else:
                    # Create new user with phone and messenger ID
                    user_data = {
                        "phone_number": phone_number,
                        "phone_verified": True
                    }

                    # Add messenger-specific ID
                    user_data[f"{messenger_type}_id"] = messenger_id

                    # Create user
                    user = UserRepository.create_user(db, user_data)

                    logger.info("Created new user with messenger account", extra={
                        'phone_number': phone_number,
                        'messenger_type': messenger_type,
                        'messenger_id': messenger_id,
                        'user_id': user.id
                    })

                    return user.id
        except Exception as e:
            logger.error("Error linking messenger account", exc_info=True, extra={
                'phone_number': phone_number,
                'messenger_type': messenger_type,
                'messenger_id': messenger_id,
                'error_type': type(e).__name__
            })
            return None


@log_operation("transfer_subscriptions")
def transfer_subscriptions(from_user_id: int, to_user_id: int) -> bool:
    """
    Transfer subscriptions from one user to another

    Args:
        from_user_id: Source user ID
        to_user_id: Destination user ID

    Returns:
        True if successful, False otherwise
    """
    with log_context(logger, from_user_id=from_user_id, to_user_id=to_user_id):
        try:
            from common.db.repositories.subscription_repository import SubscriptionRepository

            with db_session() as db:
                success = SubscriptionRepository.transfer_subscriptions(db, from_user_id, to_user_id)

                if success:
                    logger.info("Successfully transferred subscriptions", extra={
                        'from_user_id': from_user_id,
                        'to_user_id': to_user_id
                    })
                else:
                    logger.warning("Failed to transfer subscriptions", extra={
                        'from_user_id': from_user_id,
                        'to_user_id': to_user_id
                    })

                return success
        except Exception as e:
            logger.error("Error transferring subscriptions", exc_info=True, extra={
                'from_user_id': from_user_id,
                'to_user_id': to_user_id,
                'error_type': type(e).__name__
            })
            return False