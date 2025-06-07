# common/db/models/subscription.py
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship

from common.db.base import Base


class UserFilter(Base):
    __tablename__ = "user_filters"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    property_type = Column(String, nullable=True)
    city = Column(Integer, nullable=True)
    rooms_count = Column(ARRAY(Integer), nullable=True)
    price_min = Column(Numeric(10, 2), nullable=True)
    price_max = Column(Numeric(10, 2), nullable=True)
    is_paused = Column(Boolean, default=False)
    floor_max = Column(Integer, nullable=True)
    is_not_first_floor = Column(Boolean, nullable=True)
    is_not_last_floor = Column(Boolean, nullable=True)
    is_last_floor_only = Column(Boolean, nullable=True)
    pets_allowed = Column(Boolean, nullable=True)
    without_broker = Column(Boolean, nullable=True)

    # Relationships
    user = relationship("User", back_populates="filters")