import asyncio
import random
import logging
from typing import Type, Tuple, Optional, Callable, Any, Set

logger = logging.getLogger(__name__)


class RetryPolicy:
    """Exponential-backoff retry with jitter.
    
    Usage:
        retry = RetryPolicy(max_retries=3, base_delay=1.0)
        result = await retry.execute(my_async_func, arg1, arg2)
    """
    
    DEFAULT_RETRYABLE_ERRORS: Set[int] = {429, 500, 502, 503, 504}
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        timeout: Optional[float] = None,
    ):
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._exponential_base = exponential_base
        self._jitter = jitter
        self._timeout = timeout
    
    @property
    def max_retries(self) -> int:
        return self._max_retries
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt (0-indexed) with jitter."""
        delay = min(
            self._base_delay * (self._exponential_base ** attempt),
            self._max_delay,
        )
        if self._jitter:
            delay = delay * random.uniform(0.5, 1.5)
        return delay
    
    async def execute(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute func with retry logic.
        
        Retries on any exception up to max_retries times.
        Uses exponential backoff with jitter between retries.
        If timeout is set, wraps each attempt in asyncio.wait_for().
        """
        last_exception = None
        
        for attempt in range(self._max_retries + 1):
            try:
                if self._timeout is not None:
                    result = await asyncio.wait_for(
                        func(*args, **kwargs),
                        timeout=self._timeout,
                    )
                else:
                    result = await func(*args, **kwargs)
                return result
            except asyncio.TimeoutError:
                last_exception = asyncio.TimeoutError(
                    f"Attempt {attempt + 1}/{self._max_retries + 1} timed out "
                    f"(timeout={self._timeout}s)"
                )
                logger.warning(str(last_exception))
            except Exception as e:
                last_exception = e
                logger.warning(
                    "Attempt %d/%d failed: %s: %s",
                    attempt + 1, self._max_retries + 1,
                    type(e).__name__, e,
                )
            
            if attempt < self._max_retries:
                delay = self._calculate_delay(attempt)
                logger.info("Retrying in %.2fs...", delay)
                await asyncio.sleep(delay)
        
        raise last_exception
