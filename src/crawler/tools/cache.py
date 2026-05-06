import asyncio
import hashlib
import time
from collections import OrderedDict
from typing import Optional

_EntryTTL = 0
_EntryValue = 1


class ResponseCache:
    def __init__(self, max_size: int = 1000, default_ttl: float = 3600):
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._store: OrderedDict[str, tuple] = OrderedDict()
        self._lock = asyncio.Lock()

    def _hash_key(self, key: str) -> str:
        if len(key) > 128:
            return hashlib.md5(key.encode()).hexdigest()
        return key

    async def get(self, key: str) -> Optional[bytes]:
        hashed = self._hash_key(key)
        async with self._lock:
            if hashed not in self._store:
                return None
            expires_at, value = self._store[hashed]
            if time.monotonic() > expires_at:
                del self._store[hashed]
                return None
            self._store.move_to_end(hashed)
            return value

    async def set(self, key: str, value: bytes, ttl: float = None) -> None:
        hashed = self._hash_key(key)
        expires_at = time.monotonic() + (ttl if ttl is not None else self._default_ttl)
        async with self._lock:
            if hashed in self._store:
                self._store.move_to_end(hashed)
            self._store[hashed] = (expires_at, value)
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)
