import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Optional

from .schema import PipelineStateSchema

logger = logging.getLogger(__name__)


class FileWatcher:
    def __init__(
        self,
        state_dir: str,
        state_store,
        poll_interval: float = 1.0,
    ):
        self._state_dir = Path(state_dir)
        self._state_store = state_store
        self._poll_interval = poll_interval
        self._last_mtimes: Dict[str, float] = {}
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        await self._scan_existing()
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._running = False
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

    async def _poll_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self._poll_interval)
                await self._check_for_changes()
        except asyncio.CancelledError:
            pass

    async def _scan_existing(self) -> None:
        if not self._state_dir.exists():
            return
        for path in self._state_dir.glob("*.json"):
            try:
                mtime = path.stat().st_mtime
                self._last_mtimes[str(path)] = mtime
                await self._load_and_update(path)
            except Exception as e:
                logger.warning(f"Failed to scan existing file {path}: {e}")

    async def _check_for_changes(self) -> None:
        if not self._state_dir.exists():
            return
        for path in self._state_dir.glob("*.json"):
            try:
                mtime = path.stat().st_mtime
                path_str = str(path)
                if path_str not in self._last_mtimes or self._last_mtimes[path_str] != mtime:
                    self._last_mtimes[path_str] = mtime
                    await self._load_and_update(path)
            except Exception as e:
                logger.warning(f"Failed to check file {path}: {e}")

    async def _load_and_update(self, path: Path) -> None:
        try:
            with open(path, "r") as f:
                raw = json.load(f)
            state = PipelineStateSchema.model_validate(raw)
            self._state_store.update(state.model_dump())
        except Exception as e:
            logger.warning(f"Failed to load and update state from {path}: {e}")
