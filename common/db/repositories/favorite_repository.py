# common/db/repositories/favorite_repository.py

from typing import List, Dict, Any, Optional
import decimal

from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import func

from common.db.models.favorite import FavoriteAd
from common.db.models.ad import Ad
from common.utils.cache_managers import FavoriteCacheManager
from common.utils.logging_config import log_operation, log_context, LogAggregator

# Import the repository logger
from . import logger


class FavoriteRepository:
    """Repository for favorite ad operations"""

    @staticmethod
    @log_operation("list_favorites")
    def list_favorites(db: Session, user_id: int) -> List[Dict[str, Any]]:
        """List user's favorite ads with eager loading and caching"""
        with log_context(logger, user_id=user_id):
            # Try to get from cache first using the cache manager
            cached_favorites = FavoriteCacheManager.get_user_favorites(user_id)
            if cached_favorites:
                logger.debug("Cache hit for user favorites", extra={'user_id': user_id})
                return cached_favorites

            # Cache miss, query database
            favorites = db.query(FavoriteAd) \
                .filter(FavoriteAd.user_id == user_id) \
                .options(
                joinedload(FavoriteAd.ad).joinedload(Ad.images),
                joinedload(FavoriteAd.ad).joinedload(Ad.phones)
            ) \
                .order_by(FavoriteAd.created_at.desc()) \
                .all()

            aggregator = LogAggregator(logger, f"list_favorites_{user_id}")
            result = []

            for fav in favorites:
                ad = fav.ad
                ad_dict = {
                    "favorite_id": fav.id,
                    "ad_id": ad.id,
                    "price": float(ad.price) if isinstance(ad.price, decimal.Decimal) else ad.price,
                    "address": ad.address,
                    "city": ad.city,
                    "property_type": ad.property_type,
                    "rooms_count": ad.rooms_count,
                    "resource_url": ad.resource_url,
                    "external_id": ad.external_id,
                    "square_feet": float(ad.square_feet) if isinstance(ad.square_feet,
                                                                       decimal.Decimal) else ad.square_feet,
                    "floor": ad.floor,
                    "total_floors": ad.total_floors,
                    "images": [img.image_url for img in ad.images],
                    "phones": [phone.phone for phone in ad.phones if phone.phone],
                    "viber_link": next((phone.viber_link for phone in ad.phones if phone.viber_link), None)
                }
                result.append(ad_dict)
                aggregator.add_item({'ad_id': ad.id}, success=True)

            # Cache the result
            FavoriteCacheManager.set_user_favorites(user_id, result)

            aggregator.log_summary()
            logger.debug("Retrieved and cached user favorites", extra={
                'user_id': user_id,
                'favorite_count': len(result)
            })

            return result

    @staticmethod
    @log_operation("add_favorite")
    def add_favorite(db: Session, user_id: int, ad_id: int) -> Optional[FavoriteAd]:
        """Add a favorite ad"""
        with log_context(logger, user_id=user_id, ad_id=ad_id):
            # Check limit of 50 favorites
            favorites_count = db.query(func.count(FavoriteAd.id)).filter(
                FavoriteAd.user_id == user_id
            ).scalar()

            if favorites_count >= 50:
                logger.warning("User reached favorites limit", extra={
                    'user_id': user_id,
                    'current_count': favorites_count,
                    'limit': 50
                })
                raise ValueError("You already have 50 favorite ads, cannot add more.")

            # Check if already exists
            existing = db.query(FavoriteAd).filter(
                FavoriteAd.user_id == user_id,
                FavoriteAd.ad_id == ad_id
            ).first()

            if existing:
                logger.debug("Favorite already exists", extra={
                    'user_id': user_id,
                    'ad_id': ad_id,
                    'favorite_id': existing.id
                })
                return existing

            # Create new favorite
            favorite = FavoriteAd(user_id=user_id, ad_id=ad_id)
            db.add(favorite)
            db.commit()
            db.refresh(favorite)

            # Invalidate cache using the cache manager
            FavoriteCacheManager.invalidate_all(user_id)

            logger.info("Added favorite ad", extra={
                'user_id': user_id,
                'ad_id': ad_id,
                'favorite_id': favorite.id
            })

            return favorite

    @staticmethod
    @log_operation("remove_favorite")
    def remove_favorite(db: Session, user_id: int, ad_id: int) -> bool:
        """Remove a favorite ad"""
        with log_context(logger, user_id=user_id, ad_id=ad_id):
            favorite = db.query(FavoriteAd).filter(
                FavoriteAd.user_id == user_id,
                FavoriteAd.ad_id == ad_id
            ).first()

            if not favorite:
                logger.warning("Favorite not found", extra={
                    'user_id': user_id,
                    'ad_id': ad_id
                })
                return False

            favorite_id = favorite.id
            db.delete(favorite)
            db.commit()

            # Invalidate cache using the cache manager
            FavoriteCacheManager.invalidate_all(user_id)

            logger.info("Removed favorite ad", extra={
                'user_id': user_id,
                'ad_id': ad_id,
                'favorite_id': favorite_id
            })

            return True