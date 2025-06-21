# common/verification/email_service.py

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from common.db.session import db_session
from common.db.repositories.verification_repository import VerificationRepository
from common.db.repositories.user_repository import UserRepository
from common.utils.logging_config import log_operation, log_context

# Import the common verification logger
from . import logger

# Email configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USERNAME)
EMAIL_VERIFICATION_EXPIRY_MINUTES = 60


@log_operation("send_verification_email_with_token")
def send_verification_email_with_token(email: str) -> Optional[str]:
    """
    Create a verification token and send it via email

    Args:
        email: Email address to verify

    Returns:
        Generated token if successful, None otherwise
    """
    with log_context(logger, email=email[:5] + "..."):
        try:
            # Create verification token
            with db_session() as db:
                token = VerificationRepository.create_verification(
                    db=db,
                    verification_type="email",
                    target=email.lower().strip(),
                    user_id=None,  # Will be linked later
                    expiry_minutes=EMAIL_VERIFICATION_EXPIRY_MINUTES,
                )

            # Send email
            if send_verification_email(email, token):
                logger.info(
                    "Verification email sent successfully",
                    extra={"email": email[:5] + "..."},
                )
                return token
            else:
                logger.error(
                    "Failed to send verification email",
                    extra={"email": email[:5] + "..."},
                )
                return None

        except Exception as e:
            logger.error(
                "Error in send_verification_email_with_token",
                exc_info=True,
                extra={"email": email[:5] + "...", "error_type": type(e).__name__},
            )
            return None


@log_operation("send_verification_email")
def send_verification_email(email: str, token: str) -> bool:
    """
    Send verification email with token

    Args:
        email: Recipient email
        token: Verification token

    Returns:
        Success boolean
    """
    with log_context(logger, email=email[:5] + "..."):
        if not all([SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD]):
            logger.warning(
                "Email configuration incomplete, skipping email send",
                extra={
                    "smtp_server": SMTP_SERVER,
                    "smtp_port": SMTP_PORT,
                    "has_username": bool(SMTP_USERNAME),
                    "has_password": bool(SMTP_PASSWORD),
                },
            )
            return True

        try:
            # Create message
            msg = MIMEMultipart()
            msg["From"] = FROM_EMAIL
            msg["To"] = email
            msg["Subject"] = "Verify your email for RealEstateFinder"

            # Message body
            body = f"""
            <html>
            <body>
                <h2>Email Verification</h2>
                <p>Thank you for using RealEstateFinder!</p>
                <p>Your verification code is: <strong>{token}</strong></p>
                <p>This code will expire in {EMAIL_VERIFICATION_EXPIRY_MINUTES} minutes.</p>
                <p>If you didn't request this verification, please ignore this email.</p>
            </body>
            </html>
            """
            msg.attach(MIMEText(body, "html"))

            # Send email
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()

            logger.info("Sent verification email", extra={"email": email})
            return True

        except Exception as e:
            logger.error(
                "Failed to send verification email",
                exc_info=True,
                extra={
                    "email": email,
                    "smtp_server": SMTP_SERVER,
                    "smtp_port": SMTP_PORT,
                    "error_type": type(e).__name__,
                },
            )
            return False


@log_operation("verify_email_token")
def verify_email_token(email: str, token: str) -> bool:
    """
    Verify an email verification token

    Args:
        email: Email address
        token: Verification token

    Returns:
        True if valid, False otherwise
    """
    with log_context(logger, email=email[:5] + "..."):
        try:
            with db_session() as db:
                is_valid = VerificationRepository.verify_code(
                    db=db,
                    verification_type="email",
                    target=email.lower().strip(),
                    code=token,
                )

                if is_valid:
                    logger.info(
                        "Email token verified successfully",
                        extra={"email": email[:5] + "..."},
                    )
                else:
                    logger.warning(
                        "Email token verification failed",
                        extra={"email": email[:5] + "..."},
                    )

                return is_valid

        except Exception as e:
            logger.error(
                "Error verifying email token",
                exc_info=True,
                extra={"email": email[:5] + "...", "error_type": type(e).__name__},
            )
            return False


@log_operation("link_messenger_account")
def link_messenger_account(
    email: str, messenger_type: str, messenger_id: str
) -> Optional[int]:
    """
    Link a messenger account to a user with the given email.
    For Telegram-only app, messenger_type should always be "telegram".

    Args:
        email: Email address
        messenger_type: Type of messenger ("telegram")
        messenger_id: Messenger-specific ID

    Returns:
        The user's database ID if successful, None otherwise
    """
    with log_context(logger, email=email[:5] + "...", messenger_type=messenger_type):
        if messenger_type != "telegram":
            logger.error(
                "Unsupported messenger type", extra={"messenger_type": messenger_type}
            )
            return None

        try:
            from common.db.operations import link_telegram_to_email

            user = link_telegram_to_email(messenger_id, email)

            if user:
                logger.info(
                    "Successfully linked email to telegram account",
                    extra={"email": email[:5] + "...", "user_id": user.id},
                )
                return user.id
            else:
                logger.error(
                    "Failed to link email to telegram account",
                    extra={"email": email[:5] + "..."},
                )
                return None

        except Exception as e:
            logger.error(
                "Error linking email to telegram",
                exc_info=True,
                extra={"email": email[:5] + "...", "error_type": type(e).__name__},
            )
            return None


@log_operation("get_user_by_email")
def get_user_by_email(email: str) -> Optional[dict]:
    """
    Get user information by email

    Args:
        email: Email address

    Returns:
        User data dictionary or None if not found
    """
    with log_context(logger, email=email[:5] + "..."):
        try:
            with db_session() as db:
                user = UserRepository.get_by_email(db, email)

                if not user:
                    logger.debug(
                        "No user found with email", extra={"email": email[:5] + "..."}
                    )
                    return None

                user_data = {
                    "id": user.id,
                    "telegram_id": user.telegram_id,
                    "email": user.email,
                    "email_verified": user.email_verified,
                    "phone_number": user.phone_number,
                }

                logger.info(
                    "Found user by email",
                    extra={
                        "email": email[:5] + "...",
                        "user_id": user.id,
                        "email_verified": user.email_verified,
                    },
                )

                return user_data

        except Exception as e:
            logger.error(
                "Error getting user by email",
                exc_info=True,
                extra={"email": email[:5] + "...", "error_type": type(e).__name__},
            )
            return None
