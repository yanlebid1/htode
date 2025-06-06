# common/db/models/__init__.py
# Import all models to ensure they're registered with SQLAlchemy
from common.db.base import Base
import logging
# Import all model classes
from common.db.models.user import User
from common.db.models.subscription import UserFilter
from common.db.models.ad import Ad, AdImage, AdPhone
from common.db.models.favorite import FavoriteAd
from common.db.models.payment import PaymentOrder, PaymentHistory
from common.db.models.verification import VerificationCode

logger = logging.getLogger(__name__)

# Function to create all tables (for initial setup)
def create_tables():
    from common.db.session import engine
    Base.metadata.create_all(bind=engine)

# Import repositories separately to avoid circular imports
from common.db.repositories import *

def initialize_database():
    """Initialize database by creating all tables"""
    from common.db.session import engine
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized")