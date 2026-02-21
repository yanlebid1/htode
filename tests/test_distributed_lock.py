# tests/test_distributed_lock.py

import pytest
from unittest.mock import MagicMock
from common.utils.distributed_lock import DistributedLock, LockNotAcquired


@pytest.fixture
def mock_redis():
    """Provide a mock Redis client for lock tests."""
    return MagicMock()


@pytest.fixture
def lock(mock_redis):
    """Create a DistributedLock with mock Redis."""
    return DistributedLock(mock_redis, "lock:test_resource", timeout=30)


class TestAcquire:
    def test_acquire_success(self, lock, mock_redis):
        """Test that acquire returns True when SET NX succeeds."""
        mock_redis.set.return_value = True

        assert lock.acquire() is True
        assert lock.token is not None
        mock_redis.set.assert_called_once_with(
            "lock:test_resource", lock.token, ex=30, nx=True
        )

    def test_acquire_failure(self, lock, mock_redis):
        """Test that acquire returns False when lock is already held."""
        mock_redis.set.return_value = None

        assert lock.acquire() is False

    def test_unique_token_per_acquire(self, mock_redis):
        """Test that each acquire attempt generates a unique token."""
        mock_redis.set.return_value = True

        lock1 = DistributedLock(mock_redis, "lock:a")
        lock2 = DistributedLock(mock_redis, "lock:b")
        lock1.acquire()
        lock2.acquire()

        assert lock1.token != lock2.token


class TestRelease:
    def test_release_success(self, lock, mock_redis):
        """Test that release returns True when Lua script returns 1."""
        mock_redis.set.return_value = True
        lock.acquire()

        mock_redis.eval.return_value = 1
        assert lock.release() is True

    def test_release_failure_expired(self, lock, mock_redis):
        """Test that release returns False when lock expired or was stolen."""
        mock_redis.set.return_value = True
        lock.acquire()

        mock_redis.eval.return_value = 0
        assert lock.release() is False

    def test_release_without_token(self, lock):
        """Test that release returns False when no token exists."""
        assert lock.release() is False


class TestSyncContextManager:
    def test_context_manager_success(self, mock_redis):
        """Test sync context manager acquires and releases."""
        mock_redis.set.return_value = True
        mock_redis.eval.return_value = 1
        lock = DistributedLock(mock_redis, "lock:ctx")

        with lock:
            assert lock.token is not None

        mock_redis.eval.assert_called_once()

    def test_context_manager_raises_on_failure(self, mock_redis):
        """Test sync context manager raises LockNotAcquired."""
        mock_redis.set.return_value = None
        lock = DistributedLock(mock_redis, "lock:ctx")

        with pytest.raises(LockNotAcquired):
            with lock:
                pass  # pragma: no cover


class TestAsyncContextManager:
    async def test_async_context_manager_success(self, mock_redis):
        """Test async context manager acquires and releases."""
        mock_redis.set.return_value = True
        mock_redis.eval.return_value = 1
        lock = DistributedLock(mock_redis, "lock:async_ctx")

        async with lock:
            assert lock.token is not None

        mock_redis.eval.assert_called_once()

    async def test_async_context_manager_raises_on_failure(self, mock_redis):
        """Test async context manager raises LockNotAcquired."""
        mock_redis.set.return_value = None
        lock = DistributedLock(mock_redis, "lock:async_ctx")

        with pytest.raises(LockNotAcquired):
            async with lock:
                pass  # pragma: no cover
