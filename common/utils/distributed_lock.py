# common/utils/distributed_lock.py

import uuid
import logging

logger = logging.getLogger(__name__)


class DistributedLock:
    """Redis-based distributed lock using SET NX + Lua release.

    Usage (sync context manager):
        lock = DistributedLock(redis_client, "lock:my_resource", timeout=30)
        with lock:
            # critical section
            ...

    Usage (async context manager):
        async with lock:
            # critical section
            ...

    The lock is safe against accidental release by other holders: the Lua
    script ensures only the owner (identified by a unique token) can delete
    the key.
    """

    RELEASE_SCRIPT = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    end
    return 0
    """

    def __init__(self, redis_client, key: str, timeout: int = 30):
        self.redis = redis_client
        self.key = key
        self.timeout = timeout
        self.token = None

    def acquire(self) -> bool:
        """Try to acquire the lock. Returns True on success."""
        self.token = str(uuid.uuid4())
        acquired = self.redis.set(self.key, self.token, ex=self.timeout, nx=True)
        if acquired:
            logger.debug("Lock acquired", extra={"key": self.key, "token": self.token})
        return bool(acquired)

    def release(self) -> bool:
        """Release the lock if we still own it. Returns True if released."""
        if self.token is None:
            return False
        result = self.redis.eval(self.RELEASE_SCRIPT, 1, self.key, self.token)
        released = bool(result)
        if released:
            logger.debug("Lock released", extra={"key": self.key, "token": self.token})
        else:
            logger.warning(
                "Lock not released (expired or stolen)",
                extra={"key": self.key, "token": self.token},
            )
        self.token = None
        return released

    # Sync context manager
    def __enter__(self):
        if not self.acquire():
            raise LockNotAcquired(f"Could not acquire lock: {self.key}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False

    # Async context manager (delegates to sync since redis-py operations are sync)
    async def __aenter__(self):
        if not self.acquire():
            raise LockNotAcquired(f"Could not acquire lock: {self.key}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


class LockNotAcquired(Exception):
    """Raised when a DistributedLock cannot be acquired."""
