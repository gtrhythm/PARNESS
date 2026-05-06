import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

from .models import PDFQueueItem, PDFQueueState, PDFItemStatus, parse_pdf_list

logger = logging.getLogger(__name__)


class PDFQueueAgent:
    """Reads a JSON list of PDF paths and yields them one at a time.

    Usage::

        agent = PDFQueueAgent.from_json("pdf_list.json")
        while agent.has_next():
            result = agent.next()
            print(result["path"])

    State is persisted to ``state_dir / "queue_state.json"`` so the agent
    can be resumed after a crash / restart.
    """

    def __init__(
        self,
        items: List[PDFQueueItem],
        state_dir: str = "output/pdf_queue",
    ) -> None:
        self._state_dir = Path(state_dir)
        self._state_path = self._state_dir / "queue_state.json"
        self._state: Optional[PDFQueueState] = None
        self._initial_items = items

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_json(
        cls,
        json_path: Union[str, Path],
        state_dir: str = "output/pdf_queue",
    ) -> "PDFQueueAgent":
        """Create an agent from a JSON file containing PDF paths."""
        items = parse_pdf_list(json_path)
        logger.info("Loaded %d PDF paths from %s", len(items), json_path)
        return cls(items=items, state_dir=state_dir)

    @classmethod
    def from_list(
        cls,
        paths: List[Union[str, Dict]],
        state_dir: str = "output/pdf_queue",
    ) -> "PDFQueueAgent":
        """Create an agent from an in-memory list."""
        items = parse_pdf_list(paths)
        return cls(items=items, state_dir=state_dir)

    @classmethod
    def resume(
        cls,
        state_dir: str = "output/pdf_queue",
    ) -> "PDFQueueAgent":
        """Resume an agent from its persisted state (no new JSON needed)."""
        state_path = Path(state_dir) / "queue_state.json"
        state = PDFQueueState.load(state_path)
        if not state.items:
            raise FileNotFoundError(
                f"No resumable state found at {state_path}"
            )
        agent = cls.__new__(cls)
        agent._state_dir = Path(state_dir)
        agent._state_path = state_path
        agent._state = state
        agent._initial_items = state.items
        logger.info(
            "Resumed queue with %d items (cursor=%d)",
            state.total,
            state.cursor,
        )
        return agent

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def has_next(self) -> bool:
        """Return True if there are still undispatched items."""
        return not self._get_state().exhausted

    def next(self) -> Optional[Dict[str, str]]:
        """Dispatch and return the next PDF item.

        Returns a dict ``{"path": ..., "label": ..., "index": ...}``
        or ``None`` when the queue is exhausted.
        """
        state = self._get_state()
        if state.exhausted:
            logger.debug("Queue exhausted, nothing to dispatch")
            return None

        item = state.items[state.cursor]
        item.status = PDFItemStatus.DISPATCHED
        idx = state.cursor
        state.cursor += 1
        self._persist()
        logger.info("Dispatched [%d/%d] %s", idx + 1, state.total, item.path)
        return {"path": item.path, "label": item.label, "index": idx}

    def mark_done(self, index: int) -> None:
        """Mark a previously dispatched item as done."""
        self._update_status(index, PDFItemStatus.DONE)

    def mark_error(self, index: int, message: str = "") -> None:
        """Mark a previously dispatched item as errored."""
        self._update_status(index, PDFItemStatus.ERROR, message=message)

    def mark_skipped(self, index: int) -> None:
        """Mark an item as skipped."""
        self._update_status(index, PDFItemStatus.SKIPPED)

    def progress(self) -> Dict[str, int]:
        """Return a summary of current progress."""
        state = self._get_state()
        dispatched = sum(
            1 for i in state.items if i.status == PDFItemStatus.DISPATCHED
        )
        done = sum(
            1 for i in state.items if i.status == PDFItemStatus.DONE
        )
        errors = sum(
            1 for i in state.items if i.status == PDFItemStatus.ERROR
        )
        skipped = sum(
            1 for i in state.items if i.status == PDFItemStatus.SKIPPED
        )
        return {
            "total": state.total,
            "dispatched": dispatched,
            "done": done,
            "errors": errors,
            "skipped": skipped,
            "remaining": state.remaining,
        }

    def reset(self) -> None:
        """Reset cursor to 0 and re-queue all items."""
        state = self._get_state()
        state.cursor = 0
        for item in state.items:
            item.status = PDFItemStatus.PENDING
            item.error_message = ""
        self._persist()
        logger.info("Queue reset: %d items re-queued", state.total)

    def peek(self) -> Optional[Dict[str, str]]:
        """Look at the next item without dispatching it."""
        state = self._get_state()
        if state.exhausted:
            return None
        item = state.items[state.cursor]
        return {"path": item.path, "label": item.label, "index": state.cursor}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_state(self) -> PDFQueueState:
        if self._state is None:
            persisted = PDFQueueState.load(self._state_path)
            if persisted.items:
                self._state = persisted
                logger.info(
                    "Restored existing state (%d items, cursor=%d)",
                    persisted.total,
                    persisted.cursor,
                )
            else:
                self._state = PDFQueueState(items=self._initial_items)
                self._persist()
                logger.info(
                    "Initialised new queue with %d items", len(self._initial_items)
                )
        return self._state

    def _persist(self) -> None:
        if self._state is not None:
            self._state.save(self._state_path)

    def _update_status(
        self,
        index: int,
        status: PDFItemStatus,
        message: str = "",
    ) -> None:
        state = self._get_state()
        if 0 <= index < state.total:
            state.items[index].status = status
            if message:
                state.items[index].error_message = message
            self._persist()
        else:
            raise IndexError(f"Index {index} out of range (0..{state.total - 1})")
