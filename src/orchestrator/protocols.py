from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .monitoring.reporter import ProgressReporter


class ProgressDispatcher:
    """Protocol for hook dispatchers.

    Both GraphRunner and ModuleRegistry accept this protocol instead of
    the concrete HookDispatcher, enabling testability and substitution.
    """

    def make_progress_reporter(self, node_id: str, module_name: str) -> "ProgressReporter":
        ...

    def init_pipeline(self, pipeline_name: str, session_id: str, node_ids: list) -> None:
        ...

    async def emit(self, event_type: str, payload: dict) -> None:
        ...

    def emit_sync(self, event_type: str, payload: dict) -> None:
        ...
