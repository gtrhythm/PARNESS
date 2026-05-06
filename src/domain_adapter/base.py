from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .models import (
    CorrectionPlan,
    ExperimentFeedback,
    ExperimentPlan,
    ResourceSpec,
    TaskClassification,
    ToolSpec,
    TuningSuggestion,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class DomainAdapter(ABC):
    """Abstract base class for research domain adapters.

    Each domain (CS/DL, Mathematics, Physics, etc.) implements this interface
    to provide domain-specific experiment design, execution, validation,
    auto-correction, and auto-tuning capabilities.
    """

    def __init__(self, llm_client=None, resource_bridge=None):
        self.llm = llm_client
        self.resource_bridge = resource_bridge

    @abstractmethod
    def domain_name(self) -> str:
        """Return the domain identifier, e.g. 'cs_dl', 'mathematics', 'physics'."""
        ...

    @abstractmethod
    def experiment_paradigm(self) -> str:
        """Return the experiment paradigm type."""
        ...

    @abstractmethod
    async def design_experiment(
        self,
        idea: Any,
        resources: Optional[ResourceSpec] = None,
    ) -> ExperimentPlan:
        """Design an experiment plan for the given research idea."""
        ...

    @abstractmethod
    async def run_experiment(
        self,
        plan: ExperimentPlan,
        resources: Optional[ResourceSpec] = None,
    ) -> ExperimentFeedback:
        """Execute the experiment and return feedback."""
        ...

    @abstractmethod
    async def validate_result(
        self,
        feedback: ExperimentFeedback,
        plan: ExperimentPlan,
    ) -> ValidationResult:
        """Validate experiment results against success criteria."""
        ...

    @abstractmethod
    async def auto_correct(
        self,
        feedback: ExperimentFeedback,
        validation: ValidationResult,
        plan: ExperimentPlan,
    ) -> CorrectionPlan:
        """Generate a correction plan based on failed validation."""
        ...

    @abstractmethod
    async def auto_tune(
        self,
        history: List[ExperimentFeedback],
        validation: ValidationResult,
    ) -> List[TuningSuggestion]:
        """Suggest parameter tuning based on experiment history."""
        ...

    @abstractmethod
    def classify_tasks(self, idea: Any) -> TaskClassification:
        """Classify tasks into human vs machine assignments."""
        ...

    @abstractmethod
    def required_tools(self) -> List[ToolSpec]:
        """Return the tools required for this domain."""
        ...

    @abstractmethod
    def resource_requirements(self) -> ResourceSpec:
        """Return default resource requirements for this domain."""
        ...

    def supports_auto_execution(self) -> bool:
        """Whether this domain supports fully automated execution."""
        return True

    def max_retry_rounds(self) -> int:
        """Default maximum retry rounds for iterative correction."""
        return 4
