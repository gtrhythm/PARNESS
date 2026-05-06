from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentOutput:
    display_type: str = "plain"
    title: str = ""
    content: Any = None
    data: Dict[str, Any] = field(default_factory=dict)
    render_hints: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "display_type": self.display_type,
            "title": self.title,
            "content": self.content,
            "data": self.data,
            "render_hints": self.render_hints,
            "timestamp": self.timestamp,
        }


class ProgressReporter:
    def __init__(
        self,
        callback: Callable[[Dict[str, Any]], None],
        heartbeat_interval: float = 30.0,
    ):
        self._callback = callback
        self._heartbeat_interval = heartbeat_interval
        self._last_emit_time: Optional[float] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._context: Dict[str, Any] = {}

    def update_context(self, **kwargs: Any) -> None:
        self._context.update(kwargs)

    def emit(self, event: str, **details: Any) -> None:
        payload: Dict[str, Any] = {
            "event": event,
            "timestamp": time.monotonic(),
            **details,
            **self._context,
        }
        try:
            self._callback(payload)
        except Exception:
            logger.debug("ProgressReporter callback error", exc_info=True)
        self._last_emit_time = time.monotonic()

    async def start_heartbeat(self) -> None:
        if self._heartbeat_task is not None:
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)
                if (
                    self._last_emit_time is None
                    or time.monotonic() - self._last_emit_time > self._heartbeat_interval
                ):
                    self.emit("heartbeat")
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

    def emit_output(self, output: AgentOutput) -> None:
        """Emit an agent output to the monitoring system."""
        try:
            self._callback({
                "event": "agent_output",
                "output": output.to_dict(),
            })
        except Exception:
            logger.debug("ProgressReporter emit_output error", exc_info=True)
