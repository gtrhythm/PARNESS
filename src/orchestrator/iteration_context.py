"""
Iteration Context Module.

Extends PipelineContext with iteration state management,
checkpoint save/restore, and research memory integration.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .iteration.state import IterationPhase, IterationState
from .iteration.memory import ResearchMemory


@dataclass
class IterationContext:
    session_id: str
    config: Dict[str, Any]
    iteration_state: IterationState = field(default_factory=IterationState)
    memory: Optional[ResearchMemory] = field(default=None)
    _data: Dict[str, Any] = field(default_factory=dict)
    _metadata: Dict[str, Any] = field(default_factory=dict)
    _checkpoint_stack: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.memory is None:
            self.memory = ResearchMemory()

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def require(self, key: str) -> Any:
        if key not in self._data:
            raise KeyError(
                f"IterationContext missing required key: '{key}'. "
                f"Available keys: {list(self._data.keys())}"
            )
        return self._data[key]

    def has(self, key: str) -> bool:
        return key in self._data

    def keys(self) -> List[str]:
        return list(self._data.keys())

    def snapshot(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "data_keys": list(self._data.keys()),
            "metadata": dict(self._metadata),
            "iteration_state": self.iteration_state.to_dict(),
        }

    def get_iteration_state(self) -> IterationState:
        return self.iteration_state

    def set_iteration_state(self, state: IterationState) -> None:
        self.iteration_state = state

    def get_phase(self) -> IterationPhase:
        return self.iteration_state.phase

    def set_phase(self, phase: IterationPhase) -> None:
        self.iteration_state.transition_to(phase)

    def get_iteration_count(self) -> int:
        return self.iteration_state.iteration_count

    def advance_iteration(self) -> None:
        self.iteration_state.advance_iteration()

    def save_checkpoint(self, outputs: Optional[Dict[str, Any]] = None) -> str:
        checkpoint_data = {
            "session_id": self.session_id,
            "data": dict(self._data),
            "metadata": dict(self._metadata),
            "iteration_state": {
                "phase": self.iteration_state.phase,
                "iteration_count": self.iteration_state.iteration_count,
                "max_iterations": self.iteration_state.max_iterations,
                "history": list(self.iteration_state.history),
                "metadata": dict(self.iteration_state.metadata),
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
        if outputs:
            checkpoint_data["outputs"] = dict(outputs)

        checkpoint_id = f"checkpoint_{len(self._checkpoint_stack)}"
        checkpoint_data["id"] = checkpoint_id
        self._checkpoint_stack.append(checkpoint_data)
        return checkpoint_id

    def restore_checkpoint(self, checkpoint_id: Optional[str] = None) -> bool:
        if not self._checkpoint_stack:
            return False

        if checkpoint_id is None:
            target_checkpoint = self._checkpoint_stack.pop()
        else:
            checkpoint_index = None
            for i, cp in enumerate(self._checkpoint_stack):
                if cp.get("id") == checkpoint_id:
                    checkpoint_index = i
                    break

            if checkpoint_index is None:
                return False
            target_checkpoint = self._checkpoint_stack.pop(checkpoint_index)

        self._data = target_checkpoint.get("data", {})
        self._metadata = target_checkpoint.get("metadata", {})

        state_data = target_checkpoint.get("iteration_state", {})
        phase_val = state_data.get("phase", "idea_generation")
        self.iteration_state.phase = IterationPhase(phase_val.value) if isinstance(phase_val, IterationPhase) else IterationPhase(phase_val)
        self.iteration_state.iteration_count = state_data.get("iteration_count", 0)
        self.iteration_state.max_iterations = state_data.get("max_iterations", 5)
        self.iteration_state.history = state_data.get("history", [])
        self.iteration_state.metadata = state_data.get("metadata", {})

        return True

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": f"checkpoint_{i}",
                "phase": cp.get("iteration_state", {}).get("phase", "unknown"),
                "iteration": cp.get("iteration_state", {}).get("iteration_count", 0),
                "timestamp": cp.get("timestamp", ""),
            }
            for i, cp in enumerate(self._checkpoint_stack)
        ]

    def can_iterate(self) -> bool:
        return self.iteration_state.can_iterate()

    def get_memory_stats(self) -> Dict[str, int]:
        if self.memory is None:
            return {"ideas": 0, "experiments": 0, "lessons": 0, "papers": 0}
        return self.memory.get_stats()

    async def store_idea(self, idea: Dict[str, Any], embedding: Optional[List[float]] = None) -> str:
        if self.memory is None:
            self.memory = ResearchMemory()
        return await self.memory.store_idea(idea, embedding)

    async def store_experiment(
        self, experiment: Dict[str, Any], embedding: Optional[List[float]] = None
    ) -> str:
        if self.memory is None:
            self.memory = ResearchMemory()
        return await self.memory.store_experiment(experiment, embedding)

    async def store_lesson(self, lesson: Dict[str, Any], embedding: Optional[List[float]] = None) -> str:
        if self.memory is None:
            self.memory = ResearchMemory()
        return await self.memory.store_lesson(lesson, embedding)

    async def search_similar_ideas(
        self, query: str, top_k: int = 5, domain: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if self.memory is None:
            return []
        return await self.memory.search_similar_ideas(query, top_k, domain)

    async def search_experiments(
        self, query: str, top_k: int = 5, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if self.memory is None:
            return []
        return await self.memory.search_experiments(query, top_k, status)

    async def get_recent_ideas(self, limit: int = 10) -> List[Dict[str, Any]]:
        if self.memory is None:
            return []
        return await self.memory.get_recent_ideas(limit)

    async def get_lessons_for_topic(self, topic: str) -> List[Dict[str, Any]]:
        if self.memory is None:
            return []
        return await self.memory.get_lessons_for_topic(topic)
