# tests/conftest.py

import pytest
import asyncio
import redis
import os
from unittest.mock import MagicMock, patch
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set test environment variables if not present
if not os.getenv("REDIS_URL"):
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
if not os.getenv("DB_HOST"):
    os.environ["DB_HOST"] = "localhost"

@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    mock = MagicMock()
    with patch("redis.from_url", return_value=mock):
        yield mock

@pytest.fixture
def mock_db_connection():
    """Mock database connection for testing."""
    mock = MagicMock()
    with patch("common.db.database.get_db_connection", return_value=mock):
        with patch("common.db.database.return_connection"):
            yield mock

@pytest.fixture
def mock_execute_query():
    """Mock execute_query function for testing."""
    with patch("common.db.database.execute_query") as mock:
        yield mock

@pytest.fixture
def test_user_id():
    """Return a test user ID for messaging platforms."""
    return "test_user_123"

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
        "resource_url": "https://example.com/ad/123"
    }