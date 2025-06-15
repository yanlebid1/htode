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
            code = VerificationRepository.create_verification(
                db=db,
                verification_type="phone",
                target=phone_number,
                user_id=None,  # Will be linked later
                expiry_minutes=10
            )
            logger.info("Created verification code", extra={
                'phone_number': phone_number,
                'code_length': len(code) if code else 0
            })
            return code

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
    Link a messenger account to a user with this phone number.
    For Telegram-only app, messenger_type should always be "telegram".

    Args:
        phone_number: Phone number
        messenger_type: Type of messenger ("telegram")
        messenger_id: Messenger-specific ID

    Returns:
        User ID if successful, None otherwise
    """
    with log_context(logger, phone_number=phone_number, messenger_type=messenger_type, messenger_id=messenger_id):
        if messenger_type != "telegram":
            logger.error("Unsupported messenger type", extra={
                'messenger_type': messenger_type
            })
            return None

        try:
            from common.db.operations import link_telegram_to_phone
            user = link_telegram_to_phone(messenger_id, phone_number)

            if user:
                logger.info("Successfully linked messenger account", extra={
                    'phone_number': phone_number,
                    'messenger_type': messenger_type,
                    'user_id': user.id
                })
                return user.id
            else:
                logger.error("Failed to link messenger account", extra={
                    'phone_number': phone_number,
                    'messenger_type': messenger_type
                })
                return None

        except Exception as e:
            logger.error("Error linking messenger account", exc_info=True, extra={
                'phone_number': phone_number,
                'messenger_type': messenger_type,
                'error_type': type(e).__name__
            })
            return None


@log_operation("transfer_subscriptions")
def transfer_subscriptions(from_user_id: int, to_user_id: int) -> bool:
    """
    Transfer subscriptions from one user to another.
    This is used when merging accounts.

    Args:
        from_user_id: Source user ID
        to_user_id: Target user ID

    Returns:
        Success boolean
    """
    with log_context(logger, from_user_id=from_user_id, to_user_id=to_user_id):
        # This is now handled automatically in link_telegram_to_phone
        logger.info("Subscription transfer is handled automatically during account linking", extra={
            'from_user_id': from_user_id,
            'to_user_id': to_user_id
        })
        return True


@log_operation("send_phone_verification_code")
def send_phone_verification_code(phone_number: str, user_id: Optional[int] = None) -> str:
    """
    Create and send phone verification code.
    Updated to use unified Verification model.
    """
    with log_context(logger, phone_number=phone_number[:5] + "...", user_id=user_id):
        try:
            with db_session() as db:
                code = VerificationRepository.create_verification(
                    db=db,
                    verification_type="phone",
                    target=phone_number,
                    user_id=user_id,
                    expiry_minutes=10
                )

                logger.info("Phone verification code created", extra={
                    'phone_number': phone_number[:5] + "...",
                    'user_id': user_id
                })

                # In production, send SMS here
                # For now, just return the code
                return code

        except Exception as e:
            logger.error("Error creating phone verification", exc_info=True, extra={
                'phone_number': phone_number[:5] + "...",
                'error_type': type(e).__name__
            })
            raise


@log_operation("verify_phone_code")
def verify_phone_code(phone_number: str, code: str) -> Tuple[bool, str]:
    """
    Verify phone verification code.
    Updated to use a unified Verification model.
    """
    with log_context(logger, phone_number=phone_number[:5] + "..."):
        try:
            with db_session() as db:
                is_valid = VerificationRepository.verify_code(
                    db=db,
                    verification_type="phone",
                    target=phone_number,
                    code=code
                )

                if is_valid:
                    logger.info("Phone verification successful", extra={
                        'phone_number': phone_number[:5] + "..."
                    })
                    return True, ""
                else:
                    logger.warning("Phone verification failed", extra={
                        'phone_number': phone_number[:5] + "..."
                    })
                    return False, "Неправильний код або термін дії коду закінчився"

        except Exception as e:
            logger.error("Error verifying phone code", exc_info=True, extra={
                'phone_number': phone_number[:5] + "...",
                'error_type': type(e).__name__
            })
            return False, "Помилка при перевірці коду"
