# common/db/models/payment.py

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from common.db.base import Base


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    order_id = Column(String, unique=True, index=True)
    amount = Column(Float, nullable=False)
    period = Column(String, nullable=False)
    status = Column(String, default="pending")  # 'pending', 'completed', 'cancelled', 'failed'
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="payment_orders")


class PaymentHistory(Base):
    __tablename__ = "payment_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    order_id = Column(String, index=True)
    amount = Column(Float, nullable=False)
    subscription_period = Column(String, nullable=False)
    status = Column(String, nullable=False)
    transaction_id = Column(String, nullable=True)
    card_mask = Column(String, nullable=True)
    payment_details = Column(Text, nullable=True)  # JSON stored as text
    created_at = Column(DateTime, default=func.now())

    # Relationships
    user = relationship("User")