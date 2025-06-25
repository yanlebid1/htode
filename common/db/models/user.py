# common/db/models/user.py
from datetime import datetime, timedelta

from sqlalchemy import Column, Integer, String, DateTime, Boolean, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from common.db.base import Base


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
    def is_subscription_active(self) -> bool:
        """Check if the user has an active subscription"""
        now = datetime.now()
        free_active = self.free_until and self.free_until > now
        paid_active = self.subscription_until and self.subscription_until > now
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
        free_until = datetime.now() + timedelta(days=7)
        new_user = cls(telegram_id=telegram_id, free_until=free_until)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
