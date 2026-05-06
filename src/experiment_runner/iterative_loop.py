from __future__ import annotations

import copy
import logging
import time
from typing import Any, Dict, List, Optional

from .agents import ExperimentDirectorAgent, ExperimentReviewAgent
from .agents_models import (
    DirectorAction,
    DirectorDecision,
    ExperimentRound,
    IterativeExperimentResult,
    ReviewVerdict,
)
from .executor import OpenCodeExecutor
from .models import ExperimentResult, ExperimentSpec, ExecutionStatus

logger = logging.getLogger(__name__)


class IterativeExperimentLoop:
    """Agent-driven iterative experiment execution.

    The loop follows this pattern:
        ┌─────────────────────────────────────────────────────────────┐
        │  Round N:                                                    │
        │                                                              │
        │  1. DirectorAgent looks at history, decides what to try      │
        │  2. OpenCodeExecutor runs the experiment                     │
        │  3. ReviewAgent examines the result for quality/soundness    │
        │  4. DirectorAgent reviews + review → decides next action     │
        │     ├── ACCEPT → done, return result                         │
        │     ├── RETRY_WITH_FIX → incorporate feedback, goto 1       │
        │     ├── CHANGE_APPROACH → modify spec, goto 1               │
        │     ├── CHANGE_DATASET → swap dataset, goto 1               │
        │     ├── REDUCE_SCOPE → simplify, goto 1                     │
        │     └── ABORT → stop, return best result so far             │
        └─────────────────────────────────────────────────────────────┘
    """

    def __init__(
        self,
        executor: OpenCodeExecutor,
        reviewer: ExperimentReviewAgent,
        director: ExperimentDirectorAgent,
        max_rounds: int = 4,
        score_threshold: float = 6.5,
        evaluator_config: Optional[Dict[str, Any]] = None,
    ):
        self.executor = executor
        self.reviewer = reviewer
        self.director = director
        self.max_rounds = max_rounds
        self.score_threshold = score_threshold
        self.evaluator_config = evaluator_config or {}

    async def run(self, spec: ExperimentSpec) -> IterativeExperimentResult:
        overall_result = IterativeExperimentResult(idea_id=spec.idea_id)
        current_spec = copy.deepcopy(spec)
        best_result: Optional[ExperimentResult] = None
        best_score = 0.0

        for round_num in range(1, self.max_rounds + 1):
            logger.info(
                "=== Experiment %s Round %d/%d ===",
                spec.idea_id, round_num, self.max_rounds,
            )

            exec_result = await self.executor.execute(current_spec)

            if exec_result.status == ExecutionStatus.SUCCESS and exec_result.predictions and exec_result.labels:
                eval_result = await self._evaluate(exec_result)
                exec_result.metrics.update(eval_result.metrics)

            result_dict = exec_result.to_dict()

            review = await self.reviewer.review(
                idea_title=current_spec.idea_title,
                idea_description=current_spec.idea_description,
                dataset=current_spec.dataset,
                baseline=current_spec.baseline,
                metrics_requested=current_spec.evaluation_metrics,
                hyperparameters=current_spec.hyperparameters,
                result=result_dict,
            )

            if exec_result.status == ExecutionStatus.SUCCESS:
                round_score = review.overall_score
                if round_score > best_score:
                    best_score = round_score
                    best_result = exec_result

            spec_dict = {
                "dataset": current_spec.dataset,
                "dataset_url": current_spec.dataset_url,
                "baseline": current_spec.baseline,
                "hyperparameters": dict(current_spec.hyperparameters),
                "evaluation_metrics": list(current_spec.evaluation_metrics),
                "experimental_setup": dict(current_spec.experimental_setup),
                "_last_metrics": exec_result.metrics,
            }

            director_action = await self.director.decide(
                idea_title=current_spec.idea_title,
                idea_description=current_spec.idea_description,
                spec=spec_dict,
                review=review,
                history=overall_result.rounds,
            )

            round_record = ExperimentRound(
                round_number=round_num,
                spec_snapshot=spec_dict,
                result_snapshot=result_dict,
                review=review,
                director_action=director_action,
            )
            overall_result.rounds.append(round_record)

            logger.info(
                "Round %d: decision=%s review_score=%.1f metrics=%s",
                round_num,
                director_action.decision.value,
                review.overall_score,
                json_safe_metrics(exec_result.metrics),
            )

            if director_action.decision == DirectorDecision.ACCEPT:
                overall_result.accepted = True
                overall_result.final_result = result_dict
                overall_result.final_metrics = exec_result.metrics
                overall_result.director_summary = director_action.reasoning
                logger.info("Experiment %s ACCEPTED at round %d", spec.idea_id, round_num)
                break

            if director_action.decision == DirectorDecision.ABORT:
                logger.info("Experiment %s ABORTED at round %d", spec.idea_id, round_num)
                break

            current_spec = self._apply_refinement(
                current_spec, director_action, review
            )

            if director_action.feedback_to_opencode:
                current_spec.experimental_setup["_director_feedback"] = (
                    director_action.feedback_to_opencode
                )

        overall_result.total_rounds = len(overall_result.rounds)

        if not overall_result.final_result and best_result:
            overall_result.final_result = best_result.to_dict()
            overall_result.final_metrics = best_result.metrics
            overall_result.director_summary = (
                f"Best result obtained across {overall_result.total_rounds} rounds "
                f"(score={best_score:.1f}). Was not formally accepted but is the best available."
            )

        return overall_result

    def _apply_refinement(
        self,
        spec: ExperimentSpec,
        action: DirectorAction,
        review: ReviewVerdict,
    ) -> ExperimentSpec:
        refined = copy.deepcopy(spec)

        if action.refined_spec:
            updates = action.refined_spec
            if updates.get("dataset") and updates["dataset"] != "keep":
                refined.dataset = updates["dataset"]
            if updates.get("dataset_url") and updates["dataset_url"] != "keep":
                refined.dataset_url = updates["dataset_url"]
            if updates.get("baseline") and updates["baseline"] != "keep":
                refined.baseline = updates["baseline"]
            if updates.get("hyperparameters") and updates["hyperparameters"] != {"<updated hp or keep>"}:
                refined.hyperparameters.update(updates["hyperparameters"])
            if updates.get("evaluation_metrics") and updates["evaluation_metrics"] != ["<keep or change>"]:
                refined.evaluation_metrics = updates["evaluation_metrics"]
            if updates.get("experimental_setup") and updates["experimental_setup"] != {"<keep or change>"}:
                refined.experimental_setup.update(updates["experimental_setup"])

        if action.decision == DirectorDecision.REDUCE_SCOPE:
            refined.experimental_setup["reduced_scope"] = True
            refined.experimental_setup["quick_validation"] = True
            if refined.hyperparameters.get("epochs", 0) > 10:
                refined.hyperparameters["epochs"] = 5

        if action.decision == DirectorDecision.RETRY_WITH_FIX:
            fix_hints = []
            for issue in review.issues:
                if issue.severity.value in ("warning", "critical") and issue.suggestion:
                    fix_hints.append(f"- [{issue.category}] {issue.suggestion}")
            if fix_hints:
                refined.experimental_setup["_fix_hints"] = "\n".join(fix_hints)

        refined.experimental_setup["_round"] = len(review.issues) + 1

        return refined

    async def _evaluate(self, result: ExperimentResult) -> Any:
        from src.evaluator.evaluator import Evaluator, EvalConfig, TrainResult

        eval_config = EvalConfig(
            output_dir=str(result.workdir) + "/eval_output" if result.workdir else "/tmp/eval_output",
            task_type=self.evaluator_config.get("task_type", "classification"),
            metrics=self.evaluator_config.get("metrics", []),
            generate_visualizations=False,
            generate_report=False,
        )

        evaluator = Evaluator(eval_config)
        train_result = TrainResult(
            idea_id=result.idea_id,
            predictions=result.predictions,
            labels=result.labels,
        )

        return await evaluator.evaluate(train_result)

    async def run_batch(
        self,
        specs: List[ExperimentSpec],
        max_concurrent: int = 1,
    ) -> List[IterativeExperimentResult]:
        import asyncio

        semaphore = asyncio.Semaphore(max_concurrent)

        async def _run_one(s: ExperimentSpec) -> IterativeExperimentResult:
            async with semaphore:
                return await self.run(s)

        tasks = [_run_one(s) for s in specs]
        return list(await asyncio.gather(*tasks))


def json_safe_metrics(metrics: Dict[str, Any]) -> str:
    import json
    try:
        return json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in metrics.items()})
    except (TypeError, ValueError):
        return str(metrics)[:200]
