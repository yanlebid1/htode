# tests/test_state_manager.py

import pytest
import json
from unittest.mock import patch, MagicMock
from common.unified_state_management import state_manager as RedisStateManager


@pytest.mark.asyncio
async def test_state_manager_get_state(mock_redis):
    """Test that get_state works correctly."""
    # Mock Redis get
    mock_redis.get.return_value = json.dumps({"state": "test_state", "data": "test_data"}).encode()

    state_manager = RedisStateManager(prefix="test")
    state = await state_manager.get_state("test_user")

    assert state == {"state": "test_state", "data": "test_data"}
    mock_redis.get.assert_called_once_with("test:test_user")


@pytest.mark.asyncio
async def test_state_manager_get_state_none(mock_redis):
    """Test that get_state returns None when no state exists."""
    # Mock Redis get returning None
    mock_redis.get.return_value = None

    state_manager = RedisStateManager(prefix="test")
    state = await state_manager.get_state("test_user")

    assert state is None
    mock_redis.get.assert_called_once_with("test:test_user")


@pytest.mark.asyncio
async def test_state_manager_set_state(mock_redis):
    """Test that set_state works correctly."""
    state_manager = RedisStateManager(prefix="test")
    await state_manager.set_state("test_user", {"state": "test_state", "data": "test_data"})

    mock_redis.setex.assert_called_once()
    # Check the key
    args, _ = mock_redis.setex.call_args
    assert args[0] == "test:test_user"
    # Check the serialized state
    assert json.loads(args[2]) == {"state": "test_state", "data": "test_data"}


@pytest.mark.asyncio
async def test_state_manager_update_state(mock_redis, monkeypatch):
    """Test that update_state works correctly."""
    # Mock get_state and set_state
    get_state_mock = MagicMock(return_value={"state": "old_state", "data": "old_data"})
    set_state_mock = MagicMock(return_value=True)

    state_manager = RedisStateManager(prefix="test")
    monkeypatch.setattr(state_manager, "get_state", get_state_mock)
    monkeypatch.setattr(state_manager, "set_state", set_state_mock)

    await state_manager.update_state("test_user", {"state": "new_state"})

    # Verify get_state was called
    get_state_mock.assert_called_once_with("test_user")
    # Verify set_state was called with merged state
    set_state_mock.assert_called_once()
    args, _ = set_state_mock.call_args
    assert args[0] == "test_user"
    assert args[1] == {"state": "new_state", "data": "old_data"}


@pytest.mark.asyncio
async def test_state_manager_clear_state(mock_redis):
    """Test that clear_state works correctly."""
    state_manager = RedisStateManager(prefix="test")
    await state_manager.clear_state("test_user")

    mock_redis.delete.assert_called_once_with("test:test_user")