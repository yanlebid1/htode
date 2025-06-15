# common/utils/retry_utils.py

import asyncio
import functools
import random
import time
from typing import Callable, List, Type, Any, TypeVar, Optional

from common.utils.logging_config import log_operation, log_context

# Import the common utils logger
from . import logger

# Type variable for return value
T = TypeVar('T')


def retry_with_exponential_backoff(
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        jitter: bool = True,
        jitter_factor: float = 0.2,
        retryable_exceptions: Optional[List[Type[Exception]]] = None,
        on_retry: Optional[Callable[[Exception, int, float], None]] = None
):
    """
    Decorator for retrying async functions with exponential backoff.
    """

    def decorator(func: Callable[..., Any]):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            """Wrapper for async functions"""
            if retryable_exceptions is None:
                retry_on = (Exception,)
            else:
                retry_on = tuple(retryable_exceptions)

            last_exception = None

            with log_context(logger, function=func.__name__, max_retries=max_retries):
                for attempt in range(max_retries):
                    try:
                        return await func(*args, **kwargs)
                    except retry_on as e:
                        last_exception = e
                        if attempt < max_retries - 1:
                            # Calculate exponential delay
                            delay = initial_delay * (backoff_factor ** attempt)

                            # Add jitter if enabled
                            if jitter:
                                jitter_range = delay * jitter_factor
                                delay = delay + random.uniform(-jitter_range, jitter_range)
                                delay = max(0.1, delay)  # Ensure delay is positive

                            # Call the on_retry callback if provided
                            if on_retry:
                                on_retry(e, attempt + 1, delay)
                            else:
                                logger.warning(
                                    "Retry attempt failed", extra={
                                        'function': func.__name__,
                                        'attempt': attempt + 1,
                                        'max_retries': max_retries,
                                        'delay': delay,
                                        'error': str(e),
                                        'error_type': type(e).__name__
                                    }
                                )

                            await asyncio.sleep(delay)
                        else:
                            logger.error("All retry attempts failed", extra={
                                'function': func.__name__,
                                'attempts': max_retries,
                                'error': str(e),
                                'error_type': type(e).__name__
                            })
                            raise
                    except Exception as e:
                        # Don't retry on non-retryable exceptions
                        logger.error("Non-retryable exception occurred", exc_info=True, extra={
                            'function': func.__name__,
                            'error_type': type(e).__name__
                        })
                        raise

                # This will only be reached if max_retries is 0
                if last_exception:
                    raise last_exception
                return None

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            """Wrapper for synchronous functions"""
            if retryable_exceptions is None:
                retry_on = (Exception,)
            else:
                retry_on = tuple(retryable_exceptions)

            last_exception = None

            with log_context(logger, function=func.__name__, max_retries=max_retries):
                for attempt in range(max_retries):
                    try:
                        return func(*args, **kwargs)
                    except retry_on as e:
                        last_exception = e
                        if attempt < max_retries - 1:
                            # Calculate exponential delay
                            delay = initial_delay * (backoff_factor ** attempt)

                            # Add jitter if enabled
                            if jitter:
                                jitter_range = delay * jitter_factor
                                delay = delay + random.uniform(-jitter_range, jitter_range)
                                delay = max(0.1, delay)  # Ensure delay is positive

                            # Call the on_retry callback if provided
                            if on_retry:
                                on_retry(e, attempt + 1, delay)
                            else:
                                logger.warning(
                                    "Retry attempt failed", extra={
                                        'function': func.__name__,
                                        'attempt': attempt + 1,
                                        'max_retries': max_retries,
                                        'delay': delay,
                                        'error': str(e),
                                        'error_type': type(e).__name__
                                    }
                                )

                            time.sleep(delay)
                        else:
                            logger.error("All retry attempts failed", extra={
                                'function': func.__name__,
                                'attempts': max_retries,
                                'error': str(e),
                                'error_type': type(e).__name__
                            })
                            raise
                    except Exception as e:
                        # Don't retry on non-retryable exceptions
                        logger.error("Non-retryable exception occurred", exc_info=True, extra={
                            'function': func.__name__,
                            'error_type': type(e).__name__
                        })
                        raise

                # This will only be reached if max_retries is 0
                if last_exception:
                    raise last_exception
                return None

        # Determine if the function is async or not
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


@log_operation("retry_async_function")
async def retry_async_function(
        func: Callable[..., Any],
        *args: Any,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        retryable_exceptions: Optional[List[Type[Exception]]] = None,
        **kwargs: Any
) -> Any:
    """
    Retry an async function with exponential backoff.
    This is a non-decorator version for when you need to dynamically add retry behavior.
    """
    if retryable_exceptions is None:
        retry_on = (Exception,)
    else:
        retry_on = tuple(retryable_exceptions)

    last_exception = None

    with log_context(logger, function=func.__name__, max_retries=max_retries):
        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except retry_on as e:
                last_exception = e
                if attempt < max_retries - 1:
                    delay = initial_delay * (backoff_factor ** attempt)
                    jitter = random.uniform(0.8, 1.2)
                    final_delay = delay * jitter

                    logger.warning(
                        "Retry attempt failed", extra={
                            'function': func.__name__,
                            'attempt': attempt + 1,
                            'max_retries': max_retries,
                            'delay': final_delay,
                            'error': str(e),
                            'error_type': type(e).__name__
                        }
                    )
                    await asyncio.sleep(final_delay)
                else:
                    logger.error("All retry attempts failed", extra={
                        'function': func.__name__,
                        'attempts': max_retries,
                        'error': str(e),
                        'error_type': type(e).__name__
                    })
                    raise
            except Exception as e:
                logger.error("Non-retryable exception occurred", exc_info=True, extra={
                    'function': func.__name__,
                    'error_type': type(e).__name__
                })
                raise

        if last_exception:
            raise last_exception
        return None


@log_operation("retry_sync_function")
def retry_sync_function(
        func: Callable[..., Any],
        *args: Any,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        retryable_exceptions: Optional[List[Type[Exception]]] = None,
        **kwargs: Any
) -> Any:
    """
    Retry a synchronous function with exponential backoff.
    This is a non-decorator version for when you need to dynamically add retry behavior.
    """
    if retryable_exceptions is None:
        retry_on = (Exception,)
    else:
        retry_on = tuple(retryable_exceptions)

    last_exception = None

    with log_context(logger, function=func.__name__, max_retries=max_retries):
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except retry_on as e:
                last_exception = e
                if attempt < max_retries - 1:
                    delay = initial_delay * (backoff_factor ** attempt)
                    jitter = random.uniform(0.8, 1.2)
                    final_delay = delay * jitter

                    logger.warning(
                        "Retry attempt failed", extra={
                            'function': func.__name__,
                            'attempt': attempt + 1,
                            'max_retries': max_retries,
                            'delay': final_delay,
                            'error': str(e),
                            'error_type': type(e).__name__
                        }
                    )
                    time.sleep(final_delay)
                else:
                    logger.error("All retry attempts failed", extra={
                        'function': func.__name__,
                        'attempts': max_retries,
                        'error': str(e),
                        'error_type': type(e).__name__
                    })
                    raise
            except Exception as e:
                logger.error("Non-retryable exception occurred", exc_info=True, extra={
                    'function': func.__name__,
                    'error_type': type(e).__name__
                })
                raise

        if last_exception:
            raise last_exception
        return None


class AsyncRetry:
    """Helper class for retrying async operations within an async context."""

    def __init__(
            self,
            max_retries: int = 3,
            initial_delay: float = 1.0,
            backoff_factor: float = 2.0,
            retryable_exceptions: Optional[List[Type[Exception]]] = None
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.retryable_exceptions = retryable_exceptions

    @log_operation("async_retry_call")
    async def __call__(self, func, *args, **kwargs):
        """Make the class callable."""
        return await retry_async_function(
            func,
            *args,
            max_retries=self.max_retries,
            initial_delay=self.initial_delay,
            backoff_factor=self.backoff_factor,
            retryable_exceptions=self.retryable_exceptions,
            **kwargs
        )

    @log_operation("async_retry_execute")
    async def execute(self, func, *args, **kwargs):
        """Execute a function with retries."""
        return await retry_async_function(
            func,
            *args,
            max_retries=self.max_retries,
            initial_delay=self.initial_delay,
            backoff_factor=self.backoff_factor,
            retryable_exceptions=self.retryable_exceptions,
            **kwargs
        )


# Common exception categories for retry
NETWORK_EXCEPTIONS = [
    ConnectionError,
    TimeoutError,
    OSError,
    # Add any other network-related exceptions your code might encounter
]

API_EXCEPTIONS = [
    # Add your API-specific exceptions here
]

DATABASE_EXCEPTIONS = [
    # Add your database-specific exceptions here
]