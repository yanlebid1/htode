# common/db/models/favorite.py
from datetime import datetime

from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from common.db.base import Base


class FavoriteAd(Base):
    __tablename__ = "favorite_ads"
    __table_args__ = (
        UniqueConstraint('user_id', 'ad_id', name='uq_favorite_ads_user_id_ad_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    ad_id = Column(Integer, ForeignKey("ads.id"), index=True)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    user = relationship("User", back_populates="favorites")
    ad = relationship("Ad", back_populates="favorites")