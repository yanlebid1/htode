# tests/conftest.py

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# ── Set test environment variables BEFORE any project imports ─────────────────

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "testdb")
os.environ.setdefault("DB_USER", "testuser")
os.environ.setdefault("DB_PASS", "testpass")
os.environ.setdefault("DB_PGBOUNCER_HOST", "localhost")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("REDIS_QUEUE_URL", "redis://localhost:6379/0")
os.environ.setdefault("REDIS_CACHE_URL", "redis://localhost:6379/1")
os.environ.setdefault("REDIS_STATE_URL", "redis://localhost:6379/2")
os.environ.setdefault("REDIS_ANALYTICS_URL", "redis://localhost:6379/3")
os.environ.setdefault("WEBAPP_URL", "http://localhost:8200")
os.environ.setdefault("TELEGRAM_TOKEN", "test:token")
os.environ.setdefault("TELEGRAM_DISPATCHER_TOKEN", "test:dispatcher_token")
os.environ.setdefault("WAYFORPAY_MERCHANT_LOGIN", "test_merchant")
os.environ.setdefault("WAYFORPAY_MERCHANT_SECRET", "test_secret")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test_key")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test_secret_key")
os.environ.setdefault("AWS_S3_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFRONT_DOMAIN", "test.cloudfront.net")

# ── Mock Redis cluster manager BEFORE any project code imports ────────────────
# The common.utils.cache module calls get_cache_redis() at import time.
# Without a running Redis, this raises ValueError. We intercept that here.

_mock_redis = MagicMock()
# Configure scan() to return (0, []) so _scan_keys works
_mock_redis.scan.return_value = (0, [])
# Configure get() to return None (cache miss) by default
_mock_redis.get.return_value = None
# Configure pipeline
_mock_redis.pipeline.return_value.__enter__ = MagicMock(return_value=MagicMock())
_mock_redis.pipeline.return_value.__exit__ = MagicMock(return_value=False)


def _mock_get_cache_redis():
    return _mock_redis


def _mock_get_state_redis():
    return _mock_redis


def _mock_get_queue_redis():
    return _mock_redis


def _mock_get_analytics_redis():
    return _mock_redis


# Pre-populate the redis_cluster_manager module before anything imports cache.py
import common.utils.redis_cluster_manager as _rcm

_rcm.get_cache_redis = _mock_get_cache_redis
_rcm.get_state_redis = _mock_get_state_redis
_rcm.get_queue_redis = _mock_get_queue_redis
_rcm.get_analytics_redis = _mock_get_analytics_redis

# Also patch the cluster instance so individual role lookups work
_rcm.redis_cluster.connections = {}
_rcm.redis_cluster._initialized = True
_rcm.redis_cluster.get_connection = MagicMock(return_value=_mock_redis)
_rcm.redis_cluster.get_cache_redis = MagicMock(return_value=_mock_redis)
_rcm.redis_cluster.get_state_redis = MagicMock(return_value=_mock_redis)
_rcm.redis_cluster.get_queue_redis = MagicMock(return_value=_mock_redis)
_rcm.redis_cluster.get_analytics_redis = MagicMock(return_value=_mock_redis)

# ── Now we can safely import project modules ──────────────────────────────────

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.db.base import Base
from common.db.models.user import User
from common.db.models.ad import Ad, AdImage, AdPhone
from common.db.models.payment import Payment
from common.db.models.favorite import FavoriteAd


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite engine with selective table creation."""
    engine = create_engine("sqlite:///:memory:", echo=False)

    # Create only the tables that work with SQLite
    # (skip user_filters which uses PostgreSQL ARRAY)
    tables_to_create = [
        User.__table__,
        Ad.__table__,
        AdImage.__table__,
        AdPhone.__table__,
        Payment.__table__,
        FavoriteAd.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables_to_create)

    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Provide a transactional DB session for tests."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def test_telegram_message():
    """Create a mock Telegram message object."""
    message = MagicMock()
    message.chat.id = 123456789
    message.from_user.id = 123456789
    message.text = "Test message"
    return message


@pytest.fixture
def test_ad_data():
    """Sample ad data for testing notification functions."""
    return {
        "id": 1,
        "external_id": "test_external_id",
        "property_type": "apartment",
        "price": 5000,
        "rooms_count": 2,
        "city": 10009580,  # Kyiv
        "address": "Test Address",
        "square_feet": 65.5,
        "floor": 3,
        "total_floors": 9,
        "description": "Test description",
        "resource_url": "https://example.com/ad/123",
    }
