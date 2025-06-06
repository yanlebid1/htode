# common/verification/email_service.py

import smtplib
import uuid
import os
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from common.db.session import db_session
from common.db.repositories.email_verification_repository import EmailVerificationRepository
from common.db.repositories.user_repository import UserRepository
from common.utils.logging_config import log_operation, log_context

# Import the common verification logger
from . import logger

# Configuration
EMAIL_VERIFICATION_EXPIRY_MINUTES = 30
MAX_VERIFICATION_ATTEMPTS = 3
EMAIL_SERVICE_ENABLED = os.getenv("EMAIL_SERVICE_ENABLED", "false").lower() == "true"
EMAIL_SERVICE_DEBUG = os.getenv("EMAIL_SERVICE_DEBUG", "false").lower() == "true"

# SMTP settings
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@realestatefinder.com")


@log_operation("generate_verification_token")
def generate_verification_token():
    """Generate a unique verification token"""
    return str(uuid.uuid4())


@log_operation("create_verification_token")
def create_verification_token(email):
    """
    Create a verification token for the given email

    Returns:
        The verification token
    """
    # Normalize email
    email = email.lower().strip()

    with log_context(logger, email=email):
        # Generate token
        token = generate_verification_token()
        expires_at = datetime.now() + timedelta(minutes=EMAIL_VERIFICATION_EXPIRY_MINUTES)

        with db_session() as db:
            # Create token using repository
            EmailVerificationRepository.create_token(db, email, token, expires_at)

        # Send verification email
        send_verification_email(email, token)

        logger.info("Created verification token", extra={'email': email})
        return token


@log_operation("verify_token")
def verify_token(email, token):
    """
    Verify the token for an email address

    Returns:
        (success, error_message) tuple
    """
    # Normalize email
    email = email.lower().strip()

    with log_context(logger, email=email):
        with db_session() as db:
            # Get the verification record
            token_record = EmailVerificationRepository.get_token(db, email)

            if not token_record:
                logger.warning("No verification token found", extra={'email': email})
                return False, "No verification token found for this email"

            # Check if expired
            if datetime.now() > token_record.expires_at:
                logger.warning("Verification token expired", extra={
                    'email': email,
                    'expires_at': token_record.expires_at.isoformat()
                })
                return False, "Verification token has expired"

            # Check attempts
            if token_record.attempts >= MAX_VERIFICATION_ATTEMPTS:
                logger.warning("Too many verification attempts", extra={
                    'email': email,
                    'attempts': token_record.attempts,
                    'max_attempts': MAX_VERIFICATION_ATTEMPTS
                })
                return False, "Too many verification attempts"

            # Verify token
            if not EmailVerificationRepository.verify_token(db, email, token):
                logger.warning("Invalid verification token", extra={'email': email})
                return False, "Invalid verification token"

            # Mark email as verified
            EmailVerificationRepository.mark_email_verified(db, email)

            # Delete the token
            EmailVerificationRepository.delete_token(db, email)

            logger.info("Email verification successful", extra={'email': email})
            return True, None


@log_operation("mark_email_verified")
def mark_email_verified(email):
    """Mark an email as verified"""
    with log_context(logger, email=email):
        with db_session() as db:
            EmailVerificationRepository.mark_email_verified(db, email)
            logger.info("Marked email as verified", extra={'email': email})


@log_operation("send_verification_email")
def send_verification_email(email, token):
    """Send verification email with a token"""
    with log_context(logger, email=email, email_service_enabled=EMAIL_SERVICE_ENABLED):
        if not EMAIL_SERVICE_ENABLED:
            # For development, just log the token
            logger.info("EMAIL SERVICE DISABLED", extra={
                'email': email,
                'token': token,
                'action': 'would_send'
            })

            # Write to the file in debug mode
            if EMAIL_SERVICE_DEBUG:
                try:
                    with open(f"email_token_{email.replace('@', '_at_')}.txt", "w") as f:
                        f.write(token)
                    logger.debug("Wrote token to debug file", extra={
                        'email': email,
                        'file': f"email_token_{email.replace('@', '_at_')}.txt"
                    })
                except Exception as e:
                    logger.error("Failed to write debug email token to file", exc_info=True, extra={
                        'email': email,
                        'error_type': type(e).__name__
                    })

            return True

        try:
            # Create a message
            msg = MIMEMultipart()
            msg['From'] = FROM_EMAIL
            msg['To'] = email
            msg['Subject'] = "Verify your email for RealEstateFinder"

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
            msg.attach(MIMEText(body, 'html'))

            # Send email
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()

            logger.info("Sent verification email", extra={'email': email})
            return True

        except Exception as e:
            logger.error("Failed to send verification email", exc_info=True, extra={
                'email': email,
                'smtp_server': SMTP_SERVER,
                'smtp_port': SMTP_PORT,
                'error_type': type(e).__name__
            })
            return False


@log_operation("link_messenger_account")
def link_messenger_account(email, messenger_type, messenger_id):
    """
    Link a messenger account to a user with the given email.
    If a user with email doesn't exist, creates a new user.

    Returns:
        The user's database ID
    """
    # Normalize email
    email = email.lower().strip()

    with log_context(logger, email=email, messenger_type=messenger_type, messenger_id=messenger_id):
        with db_session() as db:
            # Check if the user with this email exists
            user = UserRepository.get_by_email(db, email)

            if user:
                # Update existing user with messenger ID
                if messenger_type == "telegram":
                    user.telegram_id = messenger_id
                else:
                    logger.error("Invalid messenger type", extra={
                        'messenger_type': messenger_type,
                        'email': email
                    })
                    raise ValueError(f"Invalid messenger type: {messenger_type}")

                db.commit()
                logger.info("Linked messenger account to existing user", extra={
                    'messenger_type': messenger_type,
                    'messenger_id': messenger_id,
                    'user_id': user.id,
                    'email': email
                })
                return user.id
            else:
                # Create a new user with this email and messenger ID
                free_until = datetime.now() + timedelta(days=7)

                # Prepare user data
                user_data = {
                    "email": email,
                    "email_verified": True,
                    "free_until": free_until
                }

                # Add messenger-specific ID
                user_data[f"{messenger_type}_id"] = messenger_id

                # Create user
                user = UserRepository.create_user(db, user_data)
                logger.info("Created new user with messenger account", extra={
                    'messenger_type': messenger_type,
                    'messenger_id': messenger_id,
                    'user_id': user.id,
                    'email': email
                })
                return user.id