# tests/test_retry_utils.py

import sys
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from common.utils.retry_utils import (
    retry_with_exponential_backoff,
    retry_async_function,
    retry_sync_function,
    AsyncRetry,
)


# ── retry_with_exponential_backoff() — async wrapper ──────────────────────


class TestRetryWithExponentialBackoffAsync:
    @pytest.mark.asyncio
    @patch("common.utils.retry_utils.asyncio.sleep", new_callable=AsyncMock)
    async def test_async_succeeds_on_first_try_no_retry(self, mock_sleep):
        call_count = 0

        @retry_with_exponential_backoff(max_retries=3)
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    @patch("common.utils.retry_utils.asyncio.sleep", new_callable=AsyncMock)
    async def test_async_retries_on_failure_then_succeeds(self, mock_sleep):
        attempts = []

        @retry_with_exponential_backoff(max_retries=3, jitter=False)
        async def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("transient")
            return "recovered"

        result = await flaky()
        assert result == "recovered"
        assert len(attempts) == 3
        assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    @patch("common.utils.retry_utils.asyncio.sleep", new_callable=AsyncMock)
    async def test_async_exceeds_max_retries_raises(self, mock_sleep):
        @retry_with_exponential_backoff(max_retries=2, jitter=False)
        async def always_fail():
            raise ValueError("permanent")

        with pytest.raises(ValueError, match="permanent"):
            await always_fail()
        # 2 attempts total, 1 sleep between them
        assert mock_sleep.call_count == 1

    @pytest.mark.asyncio
    @patch("common.utils.retry_utils.asyncio.sleep", new_callable=AsyncMock)
    async def test_async_calls_on_retry_callback(self, mock_sleep):
        callback = MagicMock()

        @retry_with_exponential_backoff(max_retries=3, on_retry=callback, jitter=False)
        async def flaky():
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            await flaky()

        # on_retry called for attempts 1 and 2 (not the last one which raises)
        assert callback.call_count == 2
        # First call: (exception, attempt_number=1, delay)
        first_call = callback.call_args_list[0]
        assert isinstance(first_call[0][0], RuntimeError)
        assert first_call[0][1] == 1

    @pytest.mark.asyncio
    @patch("common.utils.retry_utils.random.uniform", return_value=0.1)
    @patch("common.utils.retry_utils.asyncio.sleep", new_callable=AsyncMock)
    async def test_async_applies_jitter_to_backoff(self, mock_sleep, mock_uniform):
        call_count = 0

        @retry_with_exponential_backoff(
            max_retries=2, initial_delay=1.0, backoff_factor=2.0,
            jitter=True, jitter_factor=0.2,
        )
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("fail")
            return "ok"

        result = await flaky()
        assert result == "ok"
        # random.uniform was called for jitter calculation
        mock_uniform.assert_called()
        mock_sleep.assert_called_once()

    @pytest.mark.asyncio
    @patch("common.utils.retry_utils.asyncio.sleep", new_callable=AsyncMock)
    async def test_async_non_retryable_exception_raises_immediately(self, mock_sleep):
        @retry_with_exponential_backoff(
            max_retries=3, retryable_exceptions=[ConnectionError]
        )
        async def fail_with_type_error():
            raise TypeError("not retryable")

        with pytest.raises(TypeError, match="not retryable"):
            await fail_with_type_error()
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    @patch("common.utils.retry_utils.asyncio.sleep", new_callable=AsyncMock)
    async def test_async_respects_max_retries_parameter(self, mock_sleep):
        attempts = []

        @retry_with_exponential_backoff(max_retries=5, jitter=False)
        async def fail_four_times():
            attempts.append(1)
            if len(attempts) < 5:
                raise RuntimeError("not yet")
            return "done"

        result = await fail_four_times()
        assert result == "done"
        assert len(attempts) == 5
        assert mock_sleep.call_count == 4


# ── retry_with_exponential_backoff() — sync wrapper ──────────────────────


class TestRetryWithExponentialBackoffSync:
    @patch("common.utils.retry_utils.time.sleep")
    def test_sync_succeeds_on_first_try(self, mock_sleep):
        @retry_with_exponential_backoff(max_retries=3)
        def succeed():
            return "ok"

        result = succeed()
        assert result == "ok"
        mock_sleep.assert_not_called()

    @patch("common.utils.retry_utils.time.sleep")
    def test_sync_retries_on_failure_then_succeeds(self, mock_sleep):
        attempts = []

        @retry_with_exponential_backoff(max_retries=3, jitter=False)
        def flaky():
            attempts.append(1)
            if len(attempts) < 2:
                raise OSError("transient")
            return "recovered"

        result = flaky()
        assert result == "recovered"
        assert len(attempts) == 2
        assert mock_sleep.call_count == 1

    @patch("common.utils.retry_utils.time.sleep")
    def test_sync_exceeds_max_retries_raises(self, mock_sleep):
        @retry_with_exponential_backoff(max_retries=2, jitter=False)
        def always_fail():
            raise ValueError("permanent")

        with pytest.raises(ValueError, match="permanent"):
            always_fail()


# ── retry_async_function() ───────────────────────────────────────────────


class TestRetryAsyncFunction:
    @pytest.mark.asyncio
    @patch("common.utils.retry_utils.asyncio.sleep", new_callable=AsyncMock)
    async def test_retries_on_exception_then_succeeds(self, mock_sleep):
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "success"

        result = await retry_async_function(flaky, max_retries=3)
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    @patch("common.utils.retry_utils.asyncio.sleep", new_callable=AsyncMock)
    async def test_returns_result_on_first_success(self, mock_sleep):
        async def ok():
            return 42

        result = await retry_async_function(ok, max_retries=3)
        assert result == 42
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    @patch("common.utils.retry_utils.asyncio.sleep", new_callable=AsyncMock)
    async def test_raises_after_max_attempts(self, mock_sleep):
        async def fail():
            raise TimeoutError("timeout")

        with pytest.raises(TimeoutError, match="timeout"):
            await retry_async_function(fail, max_retries=2)


# ── retry_sync_function() ───────────────────────────────────────────────


class TestRetrySyncFunction:
    @patch("common.utils.retry_utils.time.sleep")
    def test_retries_sync_on_exception(self, mock_sleep):
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OSError("transient")
            return "recovered"

        result = retry_sync_function(flaky, max_retries=3)
        assert result == "recovered"
        assert call_count == 2

    @patch("common.utils.retry_utils.time.sleep")
    def test_returns_result_on_first_success(self, mock_sleep):
        def ok():
            return "immediate"

        result = retry_sync_function(ok, max_retries=3)
        assert result == "immediate"
        mock_sleep.assert_not_called()


# ── AsyncRetry class ────────────────────────────────────────────────────


class TestAsyncRetry:
    @pytest.mark.asyncio
    @patch("common.utils.retry_utils.asyncio.sleep", new_callable=AsyncMock)
    async def test_callable_interface_retries(self, mock_sleep):
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("fail")
            return "ok"

        retry = AsyncRetry(max_retries=3)
        result = await retry(flaky)
        assert result == "ok"
        assert call_count == 2

    @pytest.mark.asyncio
    @patch("common.utils.retry_utils.asyncio.sleep", new_callable=AsyncMock)
    async def test_configurable_with_custom_exceptions(self, mock_sleep):
        async def fail_with_value_error():
            raise ValueError("custom")

        retry = AsyncRetry(max_retries=2, retryable_exceptions=[ValueError])
        with pytest.raises(ValueError, match="custom"):
            await retry(fail_with_value_error)

    @pytest.mark.asyncio
    @patch("common.utils.retry_utils.asyncio.sleep", new_callable=AsyncMock)
    async def test_ignores_non_matching_exception(self, mock_sleep):
        """Non-matching exceptions are re-raised immediately without retry."""
        async def fail_with_type_error():
            raise TypeError("wrong type")

        retry = AsyncRetry(max_retries=3, retryable_exceptions=[ConnectionError])
        with pytest.raises(TypeError, match="wrong type"):
            await retry(fail_with_type_error)
        mock_sleep.assert_not_called()
