"""
Iteration Loop Framework for Research Automation.

This module provides iteration and memory capabilities
for the research pipeline. DecisionGate and IterationController
are utility classes available for Agent modules to use directly.
"""

from .state import IterationPhase, IterationState
from .gate import Decision, DecisionGate
from .controller import IterationController
from .exceptions import (
    IterationMaxReached,
    InvalidStateTransition,
    IterationGateError,
)

__all__ = [
    "IterationPhase",
    "IterationState",
    "Decision",
    "DecisionGate",
    "IterationController",
    "IterationMaxReached",
    "InvalidStateTransition",
    "IterationGateError",
]
