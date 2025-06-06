# common/db/models/user.py
from datetime import datetime, timedelta

from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from common.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=True)
    email_verified = Column(Boolean, default=False)
    phone_number = Column(String, unique=True, index=True, nullable=True)
    phone_verified = Column(Boolean, default=False)
    free_until = Column(DateTime, nullable=True)
    subscription_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_active = Column(DateTime, default=func.now())

    # Relationships
    filters = relationship("UserFilter", back_populates="user", cascade="all, delete-orphan")
    favorites = relationship("FavoriteAd", back_populates="user", cascade="all, delete-orphan")
    payment_orders = relationship("PaymentOrder", back_populates="user", cascade="all, delete-orphan")
    verification_codes = relationship("VerificationCode", back_populates="user", cascade="all, delete-orphan")

    @property
    def is_subscription_active(self) -> bool:
        """Check if the user has an active subscription"""
        now = datetime.now()
        free_active = self.free_until and self.free_until > now
        paid_active = self.subscription_until and self.subscription_until > now
        return free_active or paid_active

    @classmethod
    def get_or_create(cls, db, messenger_id: str, messenger_type: str = "telegram") -> "User":
        """Get or create a user with messenger ID"""
        # Set the appropriate field based on a messenger type
        filter_kwargs = {f"{messenger_type}_id": messenger_id}
        user = db.query(cls).filter_by(**filter_kwargs).first()

        if user:
            return user

        # Create a new user
        free_until = datetime.now() + timedelta(days=7)
        new_user = cls(free_until=free_until, **filter_kwargs)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user