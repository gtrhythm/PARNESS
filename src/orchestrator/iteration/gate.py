"""
Decision Gate for Iteration Control.

Evaluates whether to continue, retry, or exit an iteration.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union


class Decision(str, Enum):
    """Possible decisions from a gate evaluation."""

    CONTINUE = "continue"
    RETRY = "retry"
    EXIT = "exit"


@dataclass
class GateCriteria:
    """Defines criteria for making a decision."""

    name: str
    threshold: float
    metric_path: str
    operator: str = "gt"
    weight: float = 1.0


class DecisionGate:
    """
    Evaluates outputs against criteria to make iteration decisions.
    
    Minimal implementation:
    - Accepts a list of criteria
    - Evaluates outputs against criteria
    - Returns decision based on weighted scores
    """

    def __init__(
        self,
        exit_threshold: float = 7.0,
        retry_threshold: float = 4.0,
        criteria: Optional[List[GateCriteria]] = None,
    ):
        """
        Initialize DecisionGate.
        
        Args:
            exit_threshold: Score above this threshold triggers EXIT (success)
            retry_threshold: Score below this threshold triggers RETRY
            criteria: List of criteria to evaluate
        """
        self.exit_threshold = exit_threshold
        self.retry_threshold = retry_threshold
        self.criteria = criteria or []

    def evaluate(self, outputs: Dict[str, Any]) -> Decision:
        """
        Evaluate outputs and return a decision.
        
        Args:
            outputs: Dictionary containing evaluation outputs
            
        Returns:
            Decision: CONTINUE, RETRY, or EXIT
        """
        if not outputs:
            return Decision.RETRY

        score = self._calculate_score(outputs)

        if score >= self.exit_threshold:
            return Decision.EXIT
        elif score <= self.retry_threshold:
            return Decision.RETRY
        else:
            return Decision.CONTINUE

    def _calculate_score(self, outputs: Dict[str, Any]) -> float:
        """Calculate weighted score from outputs."""
        if not self.criteria:
            return outputs.get("score", outputs.get("avg_score", 0.0))

        total_weight = 0.0
        weighted_sum = 0.0

        for criterion in self.criteria:
            value = self._get_nested_value(outputs, criterion.metric_path)
            if value is not None:
                weighted_sum += value * criterion.weight
                total_weight += criterion.weight

        if total_weight == 0:
            return outputs.get("score", 0.0)

        return weighted_sum / total_weight

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Optional[float]:
        """Get a nested value from dictionary using dot notation."""
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
            if value is None:
                return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def add_criterion(self, criterion: GateCriteria) -> None:
        """Add a evaluation criterion."""
        self.criteria.append(criterion)

    @classmethod
    def for_phase(cls, phase: str, **kwargs) -> "DecisionGate":
        """
        Factory method to create a gate configured for a specific phase.
        
        Args:
            phase: The iteration phase
            **kwargs: Additional arguments passed to constructor
            
        Returns:
            Configured DecisionGate instance
        """
        defaults = {
            "idea_generation": {"exit_threshold": 7.0, "retry_threshold": 4.0},
            "idea_evaluation": {"exit_threshold": 7.5, "retry_threshold": 4.5},
            "experiment_design": {"exit_threshold": 6.5, "retry_threshold": 4.0},
            "experiment_execution": {"exit_threshold": 7.0, "retry_threshold": 3.5},
            "result_analysis": {"exit_threshold": 6.0, "retry_threshold": 4.0},
            "paper_writing": {"exit_threshold": 7.0, "retry_threshold": 4.5},
            "paper_revision": {"exit_threshold": 7.5, "retry_threshold": 5.0},
        }

        config = defaults.get(phase, {})
        config.update(kwargs)
        return cls(**config)