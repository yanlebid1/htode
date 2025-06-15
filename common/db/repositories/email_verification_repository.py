# common/db/repositories/email_verification_repository.py

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from common.db.models.email_verification import EmailVerificationToken
from common.db.models.user import User
from common.utils.logging_config import log_operation, log_context, LogAggregator

# Import the repository logger
from . import logger


class EmailVerificationRepository:
    @staticmethod
    @log_operation("create_verification_token")
    def create_token(db: Session, email: str, token: str, expires_at: datetime) -> EmailVerificationToken:
        """Create a verification token for an email"""
        with log_context(logger, email=email[:5] + "...", expires_at=expires_at.isoformat()):
            # Delete any existing tokens for this email
            deleted_count = db.query(EmailVerificationToken).filter(EmailVerificationToken.email == email).delete()

            if deleted_count > 0:
                logger.debug("Deleted existing tokens", extra={
                    'email': email[:5] + "...",
                    'deleted_count': deleted_count
                })

            # Create a new token
            token_record = EmailVerificationToken(
                email=email,
                token=token,
                expires_at=expires_at,
                attempts=0
            )
            db.add(token_record)
            db.commit()
            db.refresh(token_record)

            logger.info("Created verification token", extra={
                'token_id': token_record.id,
                'email': email[:5] + "...",
                'expires_at': expires_at.isoformat()
            })

            return token_record

    @staticmethod
    @log_operation("get_verification_token")
    def get_token(db: Session, email: str) -> Optional[EmailVerificationToken]:
        """Get token record for an email"""
        with log_context(logger, email=email[:5] + "..."):
            token = db.query(EmailVerificationToken).filter(EmailVerificationToken.email == email).first()

            if token:
                logger.debug("Found verification token", extra={
                    'token_id': token.id,
                    'email': email[:5] + "...",
                    'attempts': token.attempts
                })
            else:
                logger.debug("No verification token found", extra={'email': email[:5] + "..."})

            return token

    @staticmethod
    @log_operation("increment_attempts")
    def increment_attempts(db: Session, token_id: int) -> int:
        """Increment the attempts counter for a token"""
        with log_context(logger, token_id=token_id):
            token = db.query(EmailVerificationToken).get(token_id)
            if token:
                token.attempts += 1
                db.commit()

                logger.debug("Incremented token attempts", extra={
                    'token_id': token_id,
                    'new_attempts': token.attempts
                })

                return token.attempts

            logger.warning("Token not found for increment", extra={'token_id': token_id})
            return 0

    @staticmethod
    @log_operation("verify_token")
    def verify_token(db: Session, email: str, token: str) -> bool:
        """Verify a token for an email"""
        with log_context(logger, email=email[:5] + "..."):
            token_record = db.query(EmailVerificationToken).filter(
                EmailVerificationToken.email == email,
                EmailVerificationToken.token == token,
                EmailVerificationToken.expires_at > datetime.now()
            ).first()

            if not token_record:
                logger.warning("Invalid or expired token", extra={'email': email[:5] + "..."})
                return False

            # Increment attempt counter
            attempts = EmailVerificationRepository.increment_attempts(db, token_record.id)

            result = attempts <= 3  # Maximum 3 attempts

            logger.info("Token verification", extra={
                'email': email[:5] + "...",
                'attempts': attempts,
                'valid': result
            })

            return result

    @staticmethod
    @log_operation("delete_verification_token")
    def delete_token(db: Session, email: str) -> bool:
        """Delete verification token for an email"""
        with log_context(logger, email=email[:5] + "..."):
            result = db.query(EmailVerificationToken).filter(EmailVerificationToken.email == email).delete()
            db.commit()

            logger.info("Deleted verification token", extra={
                'email': email[:5] + "...",
                'deleted_count': result
            })

            return result > 0

    @staticmethod
    @log_operation("mark_email_verified")
    def mark_email_verified(db: Session, email: str) -> bool:
        """Mark a user's email as verified"""
        with log_context(logger, email=email[:5] + "..."):
            user = db.query(User).filter(User.email == email).first()
            if user:
                user.email_verified = True
                db.commit()

                logger.info("Marked email as verified", extra={
                    'user_id': user.id,
                    'email': email[:5] + "..."
                })

                return True

            logger.warning("User not found for email verification", extra={'email': email[:5] + "..."})
            return False