from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from ..idea_agents.llm_utils import call_llm, parse_json_response
from .agents_models import (
    DirectorAction,
    DirectorDecision,
    Issue,
    IterativeExperimentResult,
    ExperimentRound,
    ReviewVerdict,
    Severity,
)

logger = logging.getLogger(__name__)

_REVIEW_PROMPT = """You are a senior ML experiment reviewer. Analyze this experiment result critically.

## Research Idea
{idea_title}
{idea_description}

## Experiment Setup
- Dataset: {dataset}
- Baseline: {baseline}
- Metrics requested: {metrics_requested}
- Hyperparameters: {hyperparameters}

## Experiment Result
Status: {status}
Metrics obtained: {metrics_obtained}
{extra_result_info}

## Your Task
Evaluate the result and identify issues. Check:

1. **Correctness**: Are the metrics plausible? (e.g., random baseline for CIFAR-10 is ~10%, for SST-2 is ~50%)
2. **Completeness**: Are all requested metrics present?
3. **Comparison**: How does it compare to the baseline? Is the improvement meaningful?
4. **Red flags**: 
   - Is accuracy suspiciously close to 1.0 or 0.0?
   - Are metrics inconsistent (e.g., high accuracy but low F1)?
   - Is there evidence of data leakage?
   - Are train/test splits reasonable?
5. **Practical quality**: Would this result be publishable at a workshop level?

Return JSON:
{{
  "overall_score": <1-10>,
  "result_quality": "<excellent|good|acceptable|marginal|poor|failed>",
  "is_acceptable": <true|false>,
  "issues": [
    {{
      "severity": "<info|warning|critical>",
      "category": "<correctness|completeness|comparison|red_flag|practical>",
      "message": "<what's wrong>",
      "suggestion": "<how to fix>"
    }}
  ],
  "metric_assessment": {{
    "<metric_name>": "<good|suspicious|missing|below_baseline|above_expected>"
  }},
  "recommendation": "<accept|retry|change_approach>"
}}
"""

_DIRECTOR_PROMPT = """You are the Experiment Director — a senior researcher controlling the experiment lifecycle.

## Research Idea
{idea_title}
{idea_description}

## Current Experiment Spec
- Dataset: {dataset}
- Baseline: {baseline}
- Hyperparameters: {hyperparameters}

## Round History Summary
{history_summary}

## This Round's Result
Metrics: {metrics_obtained}

## Reviewer's Assessment
Score: {review_score}/10
Quality: {result_quality}
Issues: {issues_summary}
Recommendation: {recommendation}

## Director's Task
Based on the reviewer's assessment and the full history, decide what to do next.

Consider:
- If results are good enough → ACCEPT (stop iterating)
- If there's a specific technical issue → RETRY_WITH_FIX (fix and re-run)
- If the approach fundamentally isn't working → CHANGE_APPROACH (try a different method)
- If the dataset is wrong → CHANGE_DATASET
- If the scope is too ambitious → REDUCE_SCOPE
- If nothing is working after multiple attempts → ABORT

{budget_info}

Return JSON:
{{
  "decision": "<accept|retry_with_fix|change_approach|change_dataset|reduce_scope|abort>",
  "reasoning": "<2-3 sentences explaining your decision>",
  "confidence": <0.0-1.0>,
  "feedback_to_opencode": "<specific instructions for the next opencode run, or empty string if accepting>",
  "refined_spec": {{
    "dataset": "<keep or change>",
    "dataset_url": "<keep or change>",
    "baseline": "<keep or change>",
    "hyperparameters": {{<updated hp or keep>}},
    "evaluation_metrics": [<keep or change>],
    "experimental_setup": {{<keep or change>}}
  }}
}}
"""


class ExperimentReviewAgent:
    def __init__(self, llm_client):
        self.llm = llm_client

    async def review(
        self,
        idea_title: str,
        idea_description: str,
        dataset: str,
        baseline: str,
        metrics_requested: List[str],
        hyperparameters: Dict[str, Any],
        result: Dict[str, Any],
    ) -> ReviewVerdict:
        metrics_obtained = result.get("metrics", {})
        if isinstance(metrics_obtained, dict):
            metrics_str = json.dumps(metrics_obtained, indent=2)
        else:
            metrics_str = str(metrics_obtained)

        extra_parts = []
        if result.get("baseline_metrics"):
            extra_parts.append(f"Baseline metrics: {json.dumps(result['baseline_metrics'], indent=2)}")
        if result.get("error_message"):
            extra_parts.append(f"Error: {result['error_message'][:500]}")
        if result.get("stdout"):
            tail = result["stdout"][-1500:]
            extra_parts.append(f"Output tail:\n{tail}")
        extra_result_info = "\n".join(extra_parts)

        prompt = _REVIEW_PROMPT.format(
            idea_title=idea_title,
            idea_description=idea_description[:500],
            dataset=dataset,
            baseline=baseline,
            metrics_requested=", ".join(metrics_requested),
            hyperparameters=json.dumps(hyperparameters, indent=2),
            status=result.get("status", "unknown"),
            metrics_obtained=metrics_str,
            extra_result_info=extra_result_info[:3000],
        )

        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        issues = []
        for i_data in data.get("issues", []):
            try:
                issues.append(Issue(
                    severity=Severity(i_data.get("severity", "info")),
                    category=i_data.get("category", "unknown"),
                    message=i_data.get("message", ""),
                    suggestion=i_data.get("suggestion", ""),
                ))
            except (ValueError, KeyError):
                continue

        return ReviewVerdict(
            overall_score=float(data.get("overall_score", 0)),
            result_quality=data.get("result_quality", "unknown"),
            issues=issues,
            metric_assessment=data.get("metric_assessment", {}),
            recommendation=data.get("recommendation", "retry"),
            is_acceptable=bool(data.get("is_acceptable", False)),
        )


class ExperimentDirectorAgent:
    def __init__(self, llm_client, max_rounds: int = 4, score_threshold: float = 6.5):
        self.llm = llm_client
        self.max_rounds = max_rounds
        self.score_threshold = score_threshold

    async def decide(
        self,
        idea_title: str,
        idea_description: str,
        spec: Dict[str, Any],
        review: ReviewVerdict,
        history: List[ExperimentRound],
    ) -> DirectorAction:
        if review.is_acceptable and review.overall_score >= self.score_threshold:
            return DirectorAction(
                decision=DirectorDecision.ACCEPT,
                reasoning=f"Review score {review.overall_score} meets threshold {self.score_threshold}. Result is acceptable.",
                confidence=review.overall_score / 10.0,
            )

        if len(history) >= self.max_rounds:
            return DirectorAction(
                decision=DirectorDecision.ABORT,
                reasoning=f"Max rounds ({self.max_rounds}) reached. Best score: {review.overall_score}.",
                confidence=0.3,
            )

        history_summary = self._summarize_history(history)

        issues_summary = "; ".join(
            f"[{i.severity.value}] {i.message}" for i in review.issues
        ) or "None"

        budget_info = f"Round {len(history) + 1}/{self.max_rounds}. Budget remaining: {self.max_rounds - len(history)} rounds."

        prompt = _DIRECTOR_PROMPT.format(
            idea_title=idea_title,
            idea_description=idea_description[:500],
            dataset=spec.get("dataset", ""),
            baseline=spec.get("baseline", ""),
            hyperparameters=json.dumps(spec.get("hyperparameters", {}), indent=2),
            history_summary=history_summary[:3000],
            metrics_obtained=json.dumps(spec.get("_last_metrics", {}), indent=2),
            review_score=review.overall_score,
            result_quality=review.result_quality,
            issues_summary=issues_summary,
            recommendation=review.recommendation,
            budget_info=budget_info,
        )

        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        try:
            decision = DirectorDecision(data.get("decision", "retry_with_fix"))
        except ValueError:
            decision = DirectorDecision.RETRY_WITH_FIX

        return DirectorAction(
            decision=decision,
            reasoning=data.get("reasoning", ""),
            refined_spec=data.get("refined_spec"),
            feedback_to_opencode=data.get("feedback_to_opencode", ""),
            confidence=float(data.get("confidence", 0.5)),
        )

    def _summarize_history(self, history: List[ExperimentRound]) -> str:
        if not history:
            return "No previous rounds."

        lines = []
        for round_ in history:
            line = f"Round {round_.round_number}: "
            metrics = round_.result_snapshot.get("metrics", {})
            line += f"metrics={json.dumps(metrics)}, "
            if round_.review:
                line += f"review_score={round_.review.overall_score}, "
                line += f"quality={round_.review.result_quality}"
            if round_.director_action:
                line += f", decision={round_.director_action.decision.value}"
            lines.append(line)
        return "\n".join(lines)
