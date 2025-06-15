# common/utils/db_utils.py

from typing import Optional
from common.db.models import Ad
from common.db.session import db_session
from common.utils.logging_config import log_operation, log_context

# Import the common utils logger
from . import logger


@log_operation("get_ad_id_by_external_id")
def get_ad_id_by_external_id(external_id: str) -> Optional[int]:
    """
    Get the database ID for an ad based on its external ID.

    Args:
        external_id: External identifier for the ad

    Returns:
        Database ID if found, None otherwise
    """
    with log_context(logger, external_id=external_id):
        with db_session() as db:
            ad = db.query(Ad).filter(Ad.external_id == external_id).first()

            if ad:
                logger.debug("Found ad by external ID", extra={
                    'external_id': external_id,
                    'ad_id': ad.id
                })
                return ad.id
            else:
                logger.debug("No ad found for external ID", extra={'external_id': external_id})
                return None


@log_operation("ensure_ad_exists")
def ensure_ad_exists(ad_id: int) -> bool:
    """
    Check if an ad exists in the database.

    Args:
        ad_id: Database ID of the ad to check

    Returns:
        True if the ad exists, False otherwise
    """
    with log_context(logger, ad_id=ad_id):
        try:
            with db_session() as db:
                exists = db.query(db.query(Ad).filter(Ad.id == ad_id).exists()).scalar()

                logger.debug("Checked ad existence", extra={
                    'ad_id': ad_id,
                    'exists': exists
                })

                return exists
        except Exception as e:
            logger.error("Error checking if ad exists", exc_info=True, extra={
                'ad_id': ad_id,
                'error_type': type(e).__name__
            })
            return False