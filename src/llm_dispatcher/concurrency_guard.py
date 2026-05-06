import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ConcurrencyLimitError(Exception):
    """Raised when queue depth exceeds max_queue_depth."""
    pass


class ConcurrencyGuard:
    """Concurrency control using Semaphore + queue depth limit.

    Layer 1: Semaphore limits concurrent executions.
    Layer 2: Queue depth limit provides fast-fail when too many tasks are waiting.

    Usage:
        guard = ConcurrencyGuard(max_concurrent=5, max_queue_depth=20, queue_timeout=30.0)
        async with guard:
            result = await call_api(...)
    """

    def __init__(
        self,
        max_concurrent: int = 5,
        max_queue_depth: int = 20,
        queue_timeout: Optional[float] = None,
    ):
        self._max_concurrent = max_concurrent
        self._max_queue_depth = max_queue_depth
        self._queue_timeout = queue_timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._waiting = 0
        self._lock = asyncio.Lock()

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    @property
    def max_queue_depth(self) -> int:
        return self._max_queue_depth

    @property
    def active_count(self) -> int:
        """Number of currently executing tasks."""
        return self._max_concurrent - self._semaphore._value

    @property
    def waiting_count(self) -> int:
        """Number of tasks waiting for a slot."""
        return self._waiting

    async def _enter_queue(self) -> None:
        """Check queue depth and increment waiting counter."""
        async with self._lock:
            if self._waiting >= self._max_queue_depth:
                raise ConcurrencyLimitError(
                    f"Queue depth limit reached ({self._max_queue_depth}). "
                    f"Active: {self.active_count}, Waiting: {self._waiting}"
                )
            self._waiting += 1

    async def _exit_queue(self) -> None:
        """Decrement waiting counter."""
        async with self._lock:
            self._waiting -= 1

    async def acquire(self) -> None:
        """Acquire a concurrency slot. Blocks if at capacity.

        Raises:
            ConcurrencyLimitError: If too many tasks are already queued.
        """
        await self._enter_queue()
        try:
            if self._queue_timeout is not None:
                try:
                    await asyncio.wait_for(
                        self._semaphore.acquire(),
                        timeout=self._queue_timeout,
                    )
                except asyncio.TimeoutError:
                    raise ConcurrencyLimitError(
                        f"Queue timeout ({self._queue_timeout}s) exceeded while "
                        f"waiting for a concurrency slot."
                    )
            else:
                await self._semaphore.acquire()
        except ConcurrencyLimitError:
            await self._exit_queue()
            raise
        except Exception:
            await self._exit_queue()
            raise
        await self._exit_queue()

    def release(self) -> None:
        """Release the concurrency slot."""
        self._semaphore.release()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False
