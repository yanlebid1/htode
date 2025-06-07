# common/db/models/payment.py

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Index
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from common.db.base import Base


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    order_id = Column(String, unique=True, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    period = Column(String, nullable=False)
    status = Column(String, default="pending", index=True)  # 'pending', 'completed', 'cancelled', 'failed'

    # Transaction details
    transaction_id = Column(String, nullable=True)
    card_mask = Column(String, nullable=True)
    payment_details = Column(JSON, nullable=True)  # Using JSON instead of Text

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="payments")

    # Add index for status queries
    __table_args__ = (
        Index('idx_payment_status_created', 'status', 'created_at'),
    )