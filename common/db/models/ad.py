# common/db/models/ad.py

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from common.db.base import Base


class Ad(Base):
    __tablename__ = "ads"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True)
    property_type = Column(String, index=True)
    city = Column(Integer, index=True)
    address = Column(String)
    price = Column(Numeric(10, 2), index=True)
    square_feet = Column(Numeric(10, 2))
    rooms_count = Column(Integer, index=True)
    floor = Column(Integer)
    total_floors = Column(Integer)
    insert_time = Column(DateTime, default=func.now())
    description = Column(Text)
    resource_url = Column(String, unique=True)
    original_currency = Column(String, default="UAH")

    # Relationships
    images = relationship("AdImage", back_populates="ad", cascade="all, delete-orphan")
    phones = relationship("AdPhone", back_populates="ad", cascade="all, delete-orphan")
    favorites = relationship("FavoriteAd", back_populates="ad", cascade="all, delete-orphan")


class AdImage(Base):
    __tablename__ = "ad_images"

    id = Column(Integer, primary_key=True, index=True)
    ad_id = Column(Integer, ForeignKey("ads.id"), index=True)
    image_url = Column(String)

    # Relationships
    ad = relationship("Ad", back_populates="images")


class AdPhone(Base):
    __tablename__ = "ad_phones"

    id = Column(Integer, primary_key=True, index=True)
    ad_id = Column(Integer, ForeignKey("ads.id"), index=True)
    phone = Column(String, nullable=True)
    viber_link = Column(String, nullable=True)

    # Relationships
    ad = relationship("Ad", back_populates="phones")