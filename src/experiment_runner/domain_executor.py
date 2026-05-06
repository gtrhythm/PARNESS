from __future__ import annotations

import copy
import logging
import time
from typing import Any, Dict, List, Optional

from src.domain_adapter.base import DomainAdapter
from src.domain_adapter.registry import DomainRegistry
from src.domain_adapter.detector import DomainDetector
from src.domain_adapter.models import (
    CorrectionPlan,
    ExperimentFeedback,
    ExperimentPlan,
    ValidationResult,
)
from src.domain_adapter.resource_bridge import LocalResourceBridge

logger = logging.getLogger(__name__)


class DomainAwareExecutor:
    """Route experiments to the appropriate domain adapter and
    run iterative correction loops.

    This is the main integration point that connects domain adapters
    with the existing pipeline.

    Flow:
        Idea → DomainDetector → DomainAdapter → design → run → validate
              → auto_correct → loop

    Usage:
        registry = DomainRegistry()
        registry.register(CSDLAdapter(llm))
        registry.register(MathAdapter(llm))
        registry.register(PhysicsAdapter(llm))

        executor = DomainAwareExecutor(registry, llm)
        result = await executor.execute(idea)
    """

    def __init__(
        self,
        registry: DomainRegistry,
        llm_client=None,
        max_rounds: int = 4,
        score_threshold: float = 6.0,
        resource_bridge: Optional[LocalResourceBridge] = None,
    ):
        self.registry = registry
        self.llm = llm_client
        self.max_rounds = max_rounds
        self.score_threshold = score_threshold
        self.resource_bridge = resource_bridge or LocalResourceBridge()
        self.detector = DomainDetector(registry)

    async def execute(
        self,
        idea: Any,
        domain: Optional[str] = None,
        max_rounds: Optional[int] = None,
    ) -> Dict[str, Any]:
        if domain is None:
            domain = self.detector.detect(idea)

        adapter = self.registry.get_or_raise(domain)
        rounds_limit = max_rounds or adapter.max_retry_rounds()

        logger.info(
            "Executing idea '%s' in domain '%s' (max %d rounds)",
            getattr(idea, "title", "")[:60],
            domain,
            rounds_limit,
        )

        resources = adapter.resource_requirements()
        resource_check = self.resource_bridge.can_satisfy(resources)
        if not resource_check["can_satisfy"]:
            logger.warning(
                "Resource issues for domain '%s': %s",
                domain,
                resource_check["issues"],
            )

        plan = await adapter.design_experiment(idea, resources)
        logger.info("Experiment plan designed: %s (paradigm=%s)", plan.plan_id, plan.paradigm)

        history: List[ExperimentFeedback] = []
        best_feedback: Optional[ExperimentFeedback] = None
        best_score = 0.0
        best_plan = plan

        for round_num in range(1, rounds_limit + 1):
            logger.info("=== Round %d/%d (domain=%s) ===", round_num, rounds_limit, domain)

            feedback = await adapter.run_experiment(plan, resources)
            feedback.round_number = round_num
            history.append(feedback)

            validation = await adapter.validate_result(feedback, plan)
            logger.info(
                "Round %d: status=%s score=%.1f valid=%s metrics=%s",
                round_num,
                feedback.status,
                validation.score,
                validation.is_valid,
                list(feedback.metrics.keys()),
            )

            if validation.is_valid and validation.score >= self.score_threshold:
                logger.info(
                    "Experiment ACCEPTED at round %d (score=%.1f)",
                    round_num, validation.score,
                )
                return self._build_result(
                    idea, domain, plan, feedback, validation,
                    history, accepted=True, round_number=round_num,
                )

            if validation.score > best_score:
                best_score = validation.score
                best_feedback = feedback
                best_plan = plan

            if round_num < rounds_limit:
                correction = await adapter.auto_correct(feedback, validation, plan)
                plan = self._apply_correction(plan, correction)

                tuning = await adapter.auto_tune(history, validation)
                plan = self._apply_tuning(plan, tuning)

        logger.info(
            "Experiment completed after %d rounds (best_score=%.1f)",
            len(history), best_score,
        )

        return self._build_result(
            idea, domain, best_plan, best_feedback,
            validation if history else ValidationResult(),
            history, accepted=best_score >= self.score_threshold,
            round_number=len(history),
        )

    def _apply_correction(
        self,
        plan: ExperimentPlan,
        correction: CorrectionPlan,
    ) -> ExperimentPlan:
        refined = copy.deepcopy(plan)
        if correction.modified_parameters:
            refined.parameters.update(correction.modified_parameters)

        if correction.fix_hints:
            refined.parameters["_fix_hints"] = correction.fix_hints
            refined.parameters["_correction_type"] = correction.correction_type

        refined.parameters["_round_correction"] = correction.description
        return refined

    def _apply_tuning(
        self,
        plan: ExperimentPlan,
        tuning: List,
    ) -> ExperimentPlan:
        if not tuning:
            return plan

        refined = copy.deepcopy(plan)
        for suggestion in sorted(tuning, key=lambda s: s.priority):
            name = suggestion.parameter_name
            if "." in name:
                parts = name.split(".")
                target = refined.parameters
                for p in parts[:-1]:
                    if p not in target:
                        target[p] = {}
                    target = target[p]
                target[parts[-1]] = suggestion.suggested_value
            else:
                refined.parameters[name] = suggestion.suggested_value

        return refined

    def _build_result(
        self,
        idea: Any,
        domain: str,
        plan: ExperimentPlan,
        feedback: Optional[ExperimentFeedback],
        validation: ValidationResult,
        history: List[ExperimentFeedback],
        accepted: bool,
        round_number: int,
    ) -> Dict[str, Any]:
        return {
            "idea_id": plan.idea_id,
            "idea_title": plan.idea_title,
            "domain": domain,
            "paradigm": plan.paradigm,
            "plan_id": plan.plan_id,
            "accepted": accepted,
            "round_number": round_number,
            "final_score": validation.score,
            "final_metrics": feedback.metrics if feedback else {},
            "validation": validation.to_dict(),
            "history_length": len(history),
            "history_summary": [
                {
                    "round": h.round_number,
                    "status": h.status,
                    "metrics": h.metrics,
                }
                for h in history
            ],
            "feedback_artifacts": feedback.artifacts if feedback else {},
        }

    def detect_domain(self, idea: Any) -> str:
        return self.detector.detect(idea)

    async def classify_tasks(self, idea: Any, domain: Optional[str] = None):
        if domain is None:
            domain = self.detector.detect(idea)
        adapter = self.registry.get_or_raise(domain)
        return adapter.classify_tasks(idea)
