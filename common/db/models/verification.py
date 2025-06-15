# common/db/models/verification.py

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from common.db.base import Base


class Verification(Base):
    __tablename__ = "verifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    type = Column(String, nullable=False)  # 'email' or 'phone'
    target = Column(String, nullable=False, index=True)  # email address or phone number
    code = Column(String, nullable=False)  # verification code/token
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    user = relationship("User", back_populates="verifications")

    # Composite index for efficient lookups
    __table_args__ = (
        Index('idx_verification_lookup', 'target', 'type', 'code'),
        Index('idx_verification_target_type', 'target', 'type'),
    )