import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncContextManager

logger = logging.getLogger(__name__)


class AsyncRWLock:
    """Async read-write lock for concurrent access control.

    Allows multiple concurrent readers OR a single exclusive writer.
    Writers are given priority to prevent starvation.
    """

    def __init__(self):
        self._condition: asyncio.Condition = asyncio.Condition()
        self._readers: int = 0
        self._writer: bool = False
        self._waiting_writers: int = 0

    async def acquire_read(self) -> None:
        async with self._condition:
            while self._writer or self._waiting_writers > 0:
                await self._condition.wait()
            self._readers += 1

    async def release_read(self) -> None:
        async with self._condition:
            self._readers -= 1
            if self._readers == 0:
                self._condition.notify_all()

    async def acquire_write(self) -> None:
        async with self._condition:
            self._waiting_writers += 1
            while self._writer or self._readers > 0:
                await self._condition.wait()
            self._waiting_writers -= 1
            self._writer = True

    async def release_write(self) -> None:
        async with self._condition:
            self._writer = False
            self._condition.notify_all()

    @asynccontextmanager
    async def read_locked(self) -> AsyncContextManager:
        await self.acquire_read()
        try:
            yield
        finally:
            await self.release_read()

    @asynccontextmanager
    async def write_locked(self) -> AsyncContextManager:
        await self.acquire_write()
        try:
            yield
        finally:
            await self.release_write()
