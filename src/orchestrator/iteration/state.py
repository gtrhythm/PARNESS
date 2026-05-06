"""
Iteration State Management.

Minimal module for tracking iteration state.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class IterationPhase(str, Enum):
    """Phases of the research iteration loop."""

    IDEA_GENERATION = "idea_generation"
    IDEA_EVALUATION = "idea_evaluation"
    EXPERIMENT_DESIGN = "experiment_design"
    EXPERIMENT_EXECUTION = "experiment_execution"
    RESULT_ANALYSIS = "result_analysis"
    PAPER_WRITING = "paper_writing"
    PAPER_REVISION = "paper_revision"



@dataclass
class IterationState:
    """Tracks the current state of an iteration loop."""

    phase: IterationPhase = IterationPhase.IDEA_GENERATION
    iteration_count: int = 0
    max_iterations: int = 5
    history: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def can_iterate(self) -> bool:
        """Check if another iteration is allowed."""
        return self.iteration_count < self.max_iterations

    def advance_iteration(self) -> None:
        """Advance to the next iteration."""
        self.iteration_count += 1
        self.history.append({
            "event": "iteration_advance",
            "phase": self.phase.value,
            "iteration": self.iteration_count,
        })

    def transition_to(self, new_phase: IterationPhase) -> None:
        """Transition to a new phase."""
        old_phase = self.phase
        self.phase = new_phase
        self.iteration_count = 0
        self.history.append({
            "event": "phase_transition",
            "from_phase": old_phase.value,
            "to_phase": new_phase.value,
        })

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for serialization."""
        return {
            "phase": self.phase.value,
            "iteration_count": self.iteration_count,
            "max_iterations": self.max_iterations,
            "history": self.history,
            "metadata": self.metadata,
        }
