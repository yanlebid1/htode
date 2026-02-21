# tests/test_state_manager.py

import pytest
import json
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_state_redis():
    """Provide a mock Redis client for the StateManager."""
    mock_redis = MagicMock()
    with patch("common.unified_state_management.get_state_redis", create=True) as mock_get:
        mock_get.return_value = mock_redis
        yield mock_redis


@pytest.fixture
def state_manager(mock_state_redis):
    """Create a StateManager instance with mocked Redis."""
    with patch("common.utils.redis_cluster_manager.get_state_redis", return_value=mock_state_redis):
        from common.unified_state_management import StateManager
        sm = StateManager.__new__(StateManager)
        sm.redis = mock_state_redis
        sm.prefix = "test"
        sm.default_ttl = 86400
        sm.platform_handlers = {}
        return sm


async def test_get_state_returns_parsed_json(state_manager, mock_state_redis):
    """Test that get_state returns parsed JSON from Redis."""
    mock_state_redis.get.return_value = json.dumps(
        {"state": "searching", "data": "some_data"}
    ).encode()

    state = await state_manager.get_state("user123")

    assert state == {"state": "searching", "data": "some_data"}
    mock_state_redis.get.assert_called_once_with("test:user123")


async def test_get_state_returns_none_when_missing(state_manager, mock_state_redis):
    """Test that get_state returns None when no state exists."""
    mock_state_redis.get.return_value = None

    state = await state_manager.get_state("user123")

    assert state is None


async def test_set_state_writes_to_redis(state_manager, mock_state_redis):
    """Test that set_state serializes and writes to Redis with TTL."""
    await state_manager.set_state("user123", {"state": "new_state"})

    mock_state_redis.setex.assert_called_once()
    args, _ = mock_state_redis.setex.call_args
    assert args[0] == "test:user123"
    assert args[1] == 86400  # default TTL
    assert json.loads(args[2]) == {"state": "new_state"}


async def test_clear_state_deletes_key(state_manager, mock_state_redis):
    """Test that clear_state deletes the Redis key."""
    await state_manager.clear_state("user123")

    mock_state_redis.delete.assert_called_once_with("test:user123")


def test_get_state_sync(state_manager, mock_state_redis):
    """Test the synchronous get_state_sync method."""
    mock_state_redis.get.return_value = json.dumps({"state": "active"}).encode()

    state = state_manager.get_state_sync("user123")

    assert state == {"state": "active"}
    mock_state_redis.get.assert_called_once_with("test:user123")


def test_set_state_sync(state_manager, mock_state_redis):
    """Test the synchronous set_state_sync method."""
    result = state_manager.set_state_sync("user123", {"state": "idle"})

    assert result is True
    mock_state_redis.setex.assert_called_once()


def test_clear_state_sync(state_manager, mock_state_redis):
    """Test the synchronous clear_state_sync method."""
    result = state_manager.clear_state_sync("user123")

    assert result is True
    mock_state_redis.delete.assert_called_once_with("test:user123")


def test_get_key_with_platform(state_manager):
    """Test that _get_key includes platform in the key."""
    key = state_manager._get_key("user123", platform="telegram")
    assert key == "test:telegram:user123"


def test_get_key_without_platform(state_manager):
    """Test that _get_key works without platform."""
    key = state_manager._get_key("user123")
    assert key == "test:user123"
