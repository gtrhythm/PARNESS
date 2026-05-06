import asyncio
import time
import logging
from collections import deque

logger = logging.getLogger(__name__)


class RateLimiter:
    """Sliding-window rate limiter.

    Tracks request timestamps in a deque. Before each request, checks if the
    count in the current window exceeds the limit. If so, sleeps until the
    oldest timestamp exits the window.
    """

    def __init__(self, max_requests: int = 60, window_seconds: float = 60.0):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._timestamps: deque = deque()
        self._lock = asyncio.Lock()

    @property
    def max_requests(self) -> int:
        return self._max_requests

    @property
    def window_seconds(self) -> float:
        return self._window_seconds

    @property
    def current_count(self) -> int:
        """Number of requests in the current sliding window."""
        now = time.monotonic()
        cutoff = now - self._window_seconds
        while self._timestamps and self._timestamps[0] <= cutoff:
            self._timestamps.popleft()
        return len(self._timestamps)

    async def acquire(self) -> None:
        """Wait until a request slot is available, then record the timestamp.

        This is the main entry point: call before making an API request.
        """
        async with self._lock:
            now = time.monotonic()
            cutoff = now - self._window_seconds
            while self._timestamps and self._timestamps[0] <= cutoff:
                self._timestamps.popleft()

            if len(self._timestamps) >= self._max_requests:
                oldest = self._timestamps[0]
                wait_time = oldest + self._window_seconds - now
                if wait_time > 0:
                    logger.info(
                        "Rate limit reached (%d/%.0fs), waiting %.2fs",
                        self._max_requests,
                        self._window_seconds,
                        wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    now = time.monotonic()
                    cutoff = now - self._window_seconds
                    while self._timestamps and self._timestamps[0] <= cutoff:
                        self._timestamps.popleft()

            self._timestamps.append(now)

    def reset(self) -> None:
        """Clear all recorded timestamps."""
        self._timestamps.clear()
