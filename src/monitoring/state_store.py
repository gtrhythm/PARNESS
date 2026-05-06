import threading
from typing import Callable, Dict, List, Optional


class StateStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, dict] = {}
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.RLock()

    def update(self, state: dict) -> None:
        session_id = state.get("session_id")
        if session_id is None:
            return
        with self._lock:
            self._sessions[session_id] = state
        self._notify(session_id)

    def get(self, session_id: str) -> Optional[dict]:
        with self._lock:
            return self._sessions.get(session_id)

    def list_sessions(self) -> List[str]:
        with self._lock:
            return list(self._sessions.keys())

    def list_statuses(self) -> List[dict]:
        with self._lock:
            return [self._to_status_summary(s) for s in self._sessions.values()]

    def subscribe(self, session_id: str, callback: Callable) -> None:
        with self._lock:
            if session_id not in self._subscribers:
                self._subscribers[session_id] = []
            if callback not in self._subscribers[session_id]:
                self._subscribers[session_id].append(callback)

    def unsubscribe(self, session_id: str, callback: Callable) -> None:
        with self._lock:
            if session_id in self._subscribers:
                if callback in self._subscribers[session_id]:
                    self._subscribers[session_id].remove(callback)
                if not self._subscribers[session_id]:
                    del self._subscribers[session_id]

    def _to_status_summary(self, state: dict) -> dict:
        pipeline = state.get("pipeline", {})
        steps = pipeline.get("steps", [])
        return {
            "session_id": state.get("session_id"),
            "status": state.get("status"),
            "current_step": state.get("current_step"),
            "pipeline_name": pipeline.get("name"),
            "total_steps": len(steps),
            "completed_steps": sum(1 for s in steps if s.get("status") == "completed"),
        }

    def _notify(self, session_id: str) -> None:
        with self._lock:
            subscribers = list(self._subscribers.get(session_id, []))
        for callback in subscribers:
            try:
                callback(self.get(session_id))
            except Exception:
                pass
