# common/db/models/user.py
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, Integer, String, DateTime, Boolean, BigInteger, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from common.db.base import Base
from common.utils.encryption import encrypt, decrypt, make_search_token, is_encryption_configured


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    email_verified = Column(Boolean, default=False)
    phone_number = Column(String, unique=True, index=True, nullable=True)
    phone_verified = Column(Boolean, default=False)
    free_until = Column(DateTime, nullable=True)
    subscription_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # PII encrypted columns
    email_encrypted = Column(Text, nullable=True)
    email_search_token = Column(String(64), unique=True, index=True, nullable=True)
    phone_encrypted = Column(Text, nullable=True)
    phone_search_token = Column(String(64), unique=True, index=True, nullable=True)

    # Multi-bot architecture fields
    assigned_bot_name = Column(String, nullable=True, index=True)  # e.g., "bot_1", "bot_2", etc.
    assigned_bot_username = Column(String, nullable=True)  # e.g., "@YourBot_1"
    assignment_date = Column(DateTime, nullable=True)
    dispatcher_chat_id = Column(String, nullable=True)  # Original chat ID with dispatcher

    # Relationships (updated to use new model names)
    filters = relationship(
        "UserFilter", back_populates="user", cascade="all, delete-orphan"
    )
    favorites = relationship(
        "FavoriteAd", back_populates="user", cascade="all, delete-orphan"
    )
    payments = relationship(
        "Payment", back_populates="user", cascade="all, delete-orphan"
    )
    verifications = relationship(
        "Verification", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def email_decrypted(self):
        """Return decrypted email, falling back to plaintext column."""
        if self.email_encrypted:
            decrypted = decrypt(self.email_encrypted)
            if decrypted:
                return decrypted
        return self.email

    @property
    def phone_decrypted(self):
        """Return decrypted phone, falling back to plaintext column."""
        if self.phone_encrypted:
            decrypted = decrypt(self.phone_encrypted)
            if decrypted:
                return decrypted
        return self.phone_number

    def set_email(self, email):
        """Set email with encryption if configured."""
        self.email = email
        if is_encryption_configured() and email:
            self.email_encrypted = encrypt(email)
            self.email_search_token = make_search_token(email)

    def set_phone(self, phone_number):
        """Set phone number with encryption if configured."""
        self.phone_number = phone_number
        if is_encryption_configured() and phone_number:
            self.phone_encrypted = encrypt(phone_number)
            self.phone_search_token = make_search_token(phone_number)

    @property
    def is_subscription_active(self) -> bool:
        """Check if the user has an active subscription"""
        now = datetime.now(timezone.utc)
        free_until = self.free_until
        subscription_until = self.subscription_until
        # Ensure naive datetimes from DB are treated as UTC for comparison
        if free_until and free_until.tzinfo is None:
            free_until = free_until.replace(tzinfo=timezone.utc)
        if subscription_until and subscription_until.tzinfo is None:
            subscription_until = subscription_until.replace(tzinfo=timezone.utc)
        free_active = free_until and free_until > now
        paid_active = subscription_until and subscription_until > now
        return free_active or paid_active

    @property
    def is_verified(self) -> bool:
        """User is verified if either email or phone is verified"""
        return self.email_verified or self.phone_verified

    @classmethod
    def get_or_create(cls, db, telegram_id: str) -> "User":
        """Get or create a user with telegram ID (simplified for Telegram-only)"""
        user = db.query(cls).filter(cls.telegram_id == telegram_id).first()

        if user:
            return user

        # Create a new user
        free_until = datetime.now(timezone.utc) + timedelta(days=7)
        new_user = cls(telegram_id=telegram_id, free_until=free_until)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
