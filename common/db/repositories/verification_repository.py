# common/db/repositories/verification_repository.py

from datetime import datetime, timedelta
import random
import string
import secrets
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_

from common.db.models.verification import Verification
from common.db.models.user import User
from common.db.repositories.base_repository import BaseRepository
from common.utils.logging_config import log_operation, log_context

# Import the repository logger
from . import logger


class VerificationRepository(BaseRepository):
    """Repository for unified verification operations (phone and email)"""

    @staticmethod
    def _generate_code(verification_type: str) -> str:
        """Generate appropriate code based on verification type"""
        if verification_type == "phone":
            # 6-digit code for phone
            return ''.join(random.choices(string.digits, k=6))
        else:  # email
            # Secure token for email
            return secrets.token_urlsafe(32)

    @staticmethod
    @log_operation("create_verification")
    def create_verification(
            db: Session,
            verification_type: str,
            target: str,
            user_id: Optional[int] = None,
            expiry_minutes: int = 10
    ) -> str:
        """Create a verification code/token for phone or email"""
        with log_context(logger,
                         verification_type=verification_type,
                         target=target[:5] + "...",
                         user_id=user_id):
            # Generate appropriate code
            code = VerificationRepository._generate_code(verification_type)

            # Set expiration time
            expires_at = datetime.now() + timedelta(minutes=expiry_minutes)

            # Delete any existing verifications for this target
            deleted = db.query(Verification).filter(
                and_(
                    Verification.target == target,
                    Verification.type == verification_type
                )
            ).delete()

            if deleted > 0:
                logger.debug("Deleted existing verifications", extra={
                    'target': target[:5] + "...",
                    'type': verification_type,
                    'deleted_count': deleted
                })

            # Create new verification
            verification = Verification(
                user_id=user_id,
                type=verification_type,
                target=target,
                code=code,
                expires_at=expires_at
            )

            db.add(verification)
            db.commit()

            logger.info("Created verification", extra={
                'verification_id': verification.id,
                'type': verification_type,
                'target': target[:5] + "...",
                'user_id': user_id,
                'expires_at': expires_at.isoformat()
            })

            return code

    @staticmethod
    @log_operation("verify_code")
    def verify_code(
            db: Session,
            verification_type: str,
            target: str,
            code: str
    ) -> bool:
        """Verify a code/token for phone or email"""
        with log_context(logger,
                         verification_type=verification_type,
                         target=target[:5] + "..."):

            verification = db.query(Verification).filter(
                and_(
                    Verification.type == verification_type,
                    Verification.target == target,
                    Verification.code == code,
                    Verification.expires_at > datetime.now()
                )
            ).first()

            if verification:
                # Mark as verified
                verification.verified_at = datetime.now()

                # Update user verification status if user_id exists
                if verification.user_id:
                    user = db.query(User).filter(User.id == verification.user_id).first()
                    if user:
                        if verification_type == "phone":
                            user.phone_verified = True
                        elif verification_type == "email":
                            user.email_verified = True

                db.commit()

                logger.info("Verification successful", extra={
                    'verification_id': verification.id,
                    'type': verification_type,
                    'target': target[:5] + "...",
                    'user_id': verification.user_id
                })

                return True

            # Increment attempts for failed verification
            failed_verification = db.query(Verification).filter(
                and_(
                    Verification.type == verification_type,
                    Verification.target == target,
                    Verification.expires_at > datetime.now()
                )
            ).first()

            if failed_verification:
                failed_verification.attempts += 1
                db.commit()

                logger.warning("Verification failed", extra={
                    'type': verification_type,
                    'target': target[:5] + "...",
                    'attempts': failed_verification.attempts
                })

            return False

    @staticmethod
    @log_operation("get_active_verification")
    def get_active_verification(
            db: Session,
            verification_type: str,
            target: str
    ) -> Optional[Verification]:
        """Get active verification for a target"""
        with log_context(logger,
                         verification_type=verification_type,
                         target=target[:5] + "..."):
            verification = db.query(Verification).filter(
                and_(
                    Verification.type == verification_type,
                    Verification.target == target,
                    Verification.expires_at > datetime.now()
                )
            ).first()

            if verification:
                logger.debug("Found active verification", extra={
                    'verification_id': verification.id,
                    'type': verification_type,
                    'expires_at': verification.expires_at.isoformat()
                })

            return verification

    @staticmethod
    @log_operation("cleanup_expired_verifications")
    def cleanup_expired_verifications(db: Session) -> int:
        """Clean up expired verifications"""
        with log_context(logger):
            result = db.query(Verification).filter(
                Verification.expires_at <= datetime.now()
            ).delete()

            db.commit()

            logger.info("Cleaned up expired verifications", extra={
                'deleted_count': result
            })

            return result

    @staticmethod
    @log_operation("get_recent_verification_attempts")
    def get_recent_verification_attempts(
            db: Session,
            verification_type: str,
            target: str,
            minutes: int = 30
    ) -> int:
        """Count recent verification attempts for rate limiting"""
        with log_context(logger,
                         verification_type=verification_type,
                         target=target[:5] + "...",
                         minutes=minutes):
            time_threshold = datetime.now() - timedelta(minutes=minutes)

            count = db.query(Verification).filter(
                and_(
                    Verification.type == verification_type,
                    Verification.target == target,
                    Verification.created_at >= time_threshold
                )
            ).count()

            logger.debug("Counted recent verification attempts", extra={
                'type': verification_type,
                'target': target[:5] + "...",
                'minutes': minutes,
                'attempt_count': count
            })

            return count

    @staticmethod
    @log_operation("mark_user_verified")
    def mark_user_verified(
            db: Session,
            user_id: int,
            verification_type: str,
            target: str
    ) -> bool:
        """Mark a user as verified and update their contact info"""
        with log_context(logger,
                         user_id=user_id,
                         verification_type=verification_type,
                         target=target[:5] + "..."):

            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning("User not found", extra={'user_id': user_id})
                return False

            if verification_type == "phone":
                user.phone_number = target
                user.phone_verified = True
            elif verification_type == "email":
                user.email = target
                user.email_verified = True

            db.commit()

            logger.info("User marked as verified", extra={
                'user_id': user_id,
                'type': verification_type,
                'target': target[:5] + "..."
            })

            return True

    @staticmethod
    @log_operation("get_user_verifications")
    def get_user_verifications(
            db: Session,
            user_id: int,
            verification_type: Optional[str] = None
    ) -> List[Verification]:
        """Get all verifications for a user"""
        with log_context(logger, user_id=user_id, verification_type=verification_type):
            query = db.query(Verification).filter(Verification.user_id == user_id)

            if verification_type:
                query = query.filter(Verification.type == verification_type)

            verifications = query.order_by(Verification.created_at.desc()).all()

            logger.debug("Retrieved user verifications", extra={
                'user_id': user_id,
                'type_filter': verification_type,
                'found_count': len(verifications)
            })

            return verifications