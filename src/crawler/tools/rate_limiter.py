import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, min_interval: float = 1.0):
        self._min_interval = min_interval
        self._last_request: float = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self._min_interval:
                delay = self._min_interval - elapsed
                logger.debug("Rate limiter: sleeping %.2fs", delay)
                await asyncio.sleep(delay)
            self._last_request = time.monotonic()
