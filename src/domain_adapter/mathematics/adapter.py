from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from ..base import DomainAdapter
from ..models import (
    CorrectionPlan,
    ExperimentFeedback,
    ExperimentPlan,
    ResourceSpec,
    TaskClassification,
    ToolSpec,
    TuningSuggestion,
    ValidationResult,
)
from .proof_assistant import ProofAssistant
from .symbolic_engine import SymbolicEngine
from .counterexample import CounterExampleSearcher

logger = logging.getLogger(__name__)

_MATH_DESIGN_PROMPT = """You are a mathematical research experiment designer. Design a computational experiment for the following mathematical idea.

## Research Idea
Title: {title}
Description: {description}
Category: {category}

## Your Task
Design a mathematical exploration plan:
1. Formalize the conjecture/theorem
2. Identify proof strategy
3. Plan symbolic verification steps
4. Plan numerical verification steps
5. Plan counterexample search

Return JSON:
{{
  "conjecture": "<formal statement>",
  "proof_strategy": "<technique>",
  "key_lemmas": ["<lemma1>", "<lemma2>"],
  "symbolic_checks": [
    {{
      "description": "<what to check>",
      "expression": "<sympy-compatible expression>",
      "expected": "<expected result>"
    }}
  ],
  "numerical_checks": [
    {{
      "description": "<what to verify numerically>",
      "test_range": "<range of values>",
      "num_samples": <int>
    }}
  ],
  "counterexample_search": {{
    "domain": "<integer|real|positive|prime>",
    "value_range": [min, max],
    "num_trials": <int>
  }},
  "expected_outcomes": "<description>"
}}
"""


class MathAdapter(DomainAdapter):
    """Domain adapter for mathematical research.

    Supports theorem proving, symbolic computation,
    counterexample search, and numerical verification.
    """

    def __init__(self, llm_client=None, resource_bridge=None,
                 symbolic_engine: Optional[SymbolicEngine] = None,
                 proof_assistant: Optional[ProofAssistant] = None,
                 counterexample_searcher: Optional[CounterExampleSearcher] = None):
        super().__init__(llm_client=llm_client, resource_bridge=resource_bridge)
        self.symbolic_engine = symbolic_engine or SymbolicEngine()
        self.proof_assistant = proof_assistant or ProofAssistant(
            llm_client, self.symbolic_engine
        )
        self.counterexample_searcher = counterexample_searcher or CounterExampleSearcher(
            self.symbolic_engine
        )

    def domain_name(self) -> str:
        return "mathematics"

    def experiment_paradigm(self) -> str:
        return "proof"

    def required_tools(self) -> List[ToolSpec]:
        tools = [
            ToolSpec(name="python", version="3.10+", required=True,
                     check_command="python --version"),
            ToolSpec(name="sympy", required=True,
                     install_command="pip install sympy",
                     check_command="python -c 'import sympy'"),
        ]
        return tools

    def resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(
            gpu_required=False,
            cpu_cores=2,
            ram_gb=4,
            disk_gb=5,
            estimated_duration_hours=0.5,
        )

    async def design_experiment(
        self,
        idea: Any,
        resources: Optional[ResourceSpec] = None,
    ) -> ExperimentPlan:
        idea_id = getattr(idea, "idea_id", "") or hashlib.sha256(
            getattr(idea, "title", "").encode()
        ).hexdigest()[:16]

        if self.llm is None:
            return self._default_plan(idea, idea_id)

        try:
            from src.idea_agents.llm_utils import call_llm, parse_json_response

            prompt = _MATH_DESIGN_PROMPT.format(
                title=getattr(idea, "title", ""),
                description=getattr(idea, "description", "")[:1500],
                category=getattr(idea, "category", ""),
            )

            resp = await call_llm(self.llm, prompt)
            data = parse_json_response(resp)

            return ExperimentPlan(
                plan_id=f"math_{idea_id}_{int(time.time())}",
                domain="mathematics",
                paradigm="proof",
                idea_id=idea_id,
                idea_title=getattr(idea, "title", ""),
                description=data.get("expected_outcomes", ""),
                steps=self._build_proof_steps(data),
                parameters={
                    "conjecture": data.get("conjecture", ""),
                    "proof_strategy": data.get("proof_strategy", ""),
                    "key_lemmas": data.get("key_lemmas", []),
                    "symbolic_checks": data.get("symbolic_checks", []),
                    "numerical_checks": data.get("numerical_checks", []),
                    "counterexample_search": data.get("counterexample_search", {}),
                },
                expected_outputs=["proof_status", "symbolic_verification", "counterexamples"],
                success_criteria={
                    "proof_complete": False,
                    "no_counterexamples": True,
                    "symbolic_checks_pass": True,
                },
                resource_requirements=resources or self.resource_requirements(),
            )
        except Exception as e:
            logger.warning("LLM math design failed: %s", e)
            return self._default_plan(idea, idea_id)

    async def run_experiment(
        self,
        plan: ExperimentPlan,
        resources: Optional[ResourceSpec] = None,
    ) -> ExperimentFeedback:
        results = {
            "symbolic_results": [],
            "numerical_results": [],
            "counterexample_results": {},
            "proof_analysis": {},
        }

        params = plan.parameters
        errors = []
        metrics = {}

        symbolic_checks = params.get("symbolic_checks", [])
        for check in symbolic_checks:
            try:
                expr = check.get("expression", "")
                if "=" in expr:
                    parts = expr.split("=", 1)
                    result = self.symbolic_engine.verify_identity(
                        parts[0].strip(), parts[1].strip()
                    )
                elif "+" in expr or "-" in expr or "*" in expr:
                    result = self.symbolic_engine.simplify(expr)
                else:
                    result = {"expression": expr, "status": "skipped"}

                results["symbolic_results"].append({
                    "check": check.get("description", ""),
                    "result": result,
                })
                if result.get("is_identity", False):
                    metrics["symbolic_pass_rate"] = metrics.get("symbolic_pass_rate", 0) + 1
            except Exception as e:
                errors.append(f"Symbolic check failed: {e}")

        total_symbolic = len(symbolic_checks)
        if total_symbolic > 0:
            metrics["symbolic_pass_rate"] = metrics.get("symbolic_pass_rate", 0) / total_symbolic

        conjecture = params.get("conjecture", plan.idea_title)
        counterexample_params = params.get("counterexample_search", {})
        try:
            ce_results = await self.counterexample_searcher.search(
                conjecture=conjecture,
                domain=counterexample_params.get("domain", "integer"),
                num_trials=counterexample_params.get("num_trials", 10000),
                value_range=tuple(counterexample_params.get("value_range", [-100, 100])),
            )
            results["counterexample_results"] = ce_results
            metrics["has_counterexamples"] = 1.0 if ce_results.get("counterexamples_found") else 0.0
            metrics["supports_conjecture"] = 1.0 if ce_results.get("supports_conjecture", True) else 0.0
        except Exception as e:
            errors.append(f"Counterexample search failed: {e}")

        proof_strategy = params.get("proof_strategy", "auto")
        try:
            proof_analysis = await self.proof_assistant.analyze_conjecture(
                conjecture=conjecture,
                context=plan.idea_title,
                approach=proof_strategy,
            )
            results["proof_analysis"] = proof_analysis
            metrics["proof_confidence"] = proof_analysis.get("confidence", 0.0)
        except Exception as e:
            errors.append(f"Proof analysis failed: {e}")

        return ExperimentFeedback(
            idea_id=plan.idea_id,
            status="success" if not errors else "partial",
            metrics=metrics,
            errors=errors,
            raw_data=results,
        )

    async def validate_result(
        self,
        feedback: ExperimentFeedback,
        plan: ExperimentPlan,
    ) -> ValidationResult:
        issues = []
        score = 5.0

        metrics = feedback.metrics
        raw = feedback.raw_data

        if metrics.get("has_counterexamples", 0) > 0:
            issues.append({
                "severity": "critical",
                "category": "counterexample",
                "message": "Counterexamples found - conjecture is FALSE",
            })
            score = 1.0

        symbolic_rate = metrics.get("symbolic_pass_rate", 0)
        if symbolic_rate < 1.0 and symbolic_rate > 0:
            issues.append({
                "severity": "warning",
                "category": "symbolic",
                "message": f"Some symbolic checks failed ({symbolic_rate:.0%} pass rate)",
            })
            score -= 1.0

        proof_confidence = metrics.get("proof_confidence", 0)
        if proof_confidence > 0.7:
            score = min(score + 2, 10)
        elif proof_confidence > 0.4:
            score = min(score + 1, 10)

        is_valid = score >= 6.0 and not any(
            i["severity"] == "critical" for i in issues
        )

        return ValidationResult(
            is_valid=is_valid,
            score=score,
            issues=issues,
            proof_status="supported" if metrics.get("supports_conjecture", 0) else "falsified",
            numerical_accuracy=metrics,
        )

    async def auto_correct(
        self,
        feedback: ExperimentFeedback,
        validation: ValidationResult,
        plan: ExperimentPlan,
    ) -> CorrectionPlan:
        fix_hints = []
        modified_params = dict(plan.parameters)

        for issue in validation.issues:
            cat = issue.get("category", "")
            msg = issue.get("message", "")

            if cat == "counterexample":
                fix_hints.append("Conjecture is falsified - need to revise the statement")
                fix_hints.append("Consider adding conditions or restricting the domain")
                fix_hints.append(f"Details: {msg}")
                modified_params["proof_strategy"] = "revise_conjecture"

            elif cat == "symbolic":
                fix_hints.append("Review symbolic expressions for typos or domain issues")
                fix_hints.append("Try alternative formulations of the identity")

        if validation.proof_status == "supported" and validation.score >= 6.0:
            fix_hints.append("Try to strengthen the proof or find a more elegant approach")
            modified_params["proof_strategy"] = "strengthen"

        return CorrectionPlan(
            correction_type="proof_revision",
            description=f"Proof correction based on {len(validation.issues)} issues",
            modified_parameters=modified_params,
            fix_hints=fix_hints,
        )

    async def auto_tune(
        self,
        history: List[ExperimentFeedback],
        validation: ValidationResult,
    ) -> List[TuningSuggestion]:
        suggestions = []

        if not history:
            return suggestions

        latest = history[-1]
        ce_params = latest.raw_data.get("counterexample_results", {})

        if ce_params.get("supports_conjecture") and ce_params.get("trials", 0) < 100000:
            suggestions.append(TuningSuggestion(
                parameter_name="counterexample_search.num_trials",
                current_value=ce_params.get("trials", 10000),
                suggested_value=100000,
                reason="Increase trials for stronger verification",
                confidence=0.7,
                priority=1,
            ))

        symbolic_results = latest.raw_data.get("symbolic_results", [])
        if any(not r.get("result", {}).get("is_identity", True) for r in symbolic_results):
            suggestions.append(TuningSuggestion(
                parameter_name="symbolic_checks.simplification_level",
                current_value="standard",
                suggested_value="deep",
                reason="Try deeper simplification for failed checks",
                confidence=0.5,
                priority=2,
            ))

        return suggestions

    def classify_tasks(self, idea: Any) -> TaskClassification:
        from ..task_classifier import HumanMachineTaskClassifier
        classifier = HumanMachineTaskClassifier(self.llm)
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return classifier._rule_based_classify(idea, "mathematics")
            return loop.run_until_complete(classifier.classify(idea, "mathematics"))
        except RuntimeError:
            return classifier._rule_based_classify(idea, "mathematics")

    def _build_proof_steps(self, data: dict) -> List[Dict[str, Any]]:
        steps = [
            {"step": 1, "action": "Formalize conjecture",
             "details": data.get("conjecture", "")},
            {"step": 2, "action": "Run symbolic verification",
             "details": data.get("symbolic_checks", [])},
            {"step": 3, "action": "Search for counterexamples",
             "details": data.get("counterexample_search", {})},
            {"step": 4, "action": "Analyze proof strategy",
             "details": data.get("proof_strategy", "")},
            {"step": 5, "action": "Attempt proof construction",
             "details": data.get("key_lemmas", [])},
        ]
        return steps

    def _default_plan(self, idea: Any, idea_id: str) -> ExperimentPlan:
        return ExperimentPlan(
            plan_id=f"math_{idea_id}_{int(time.time())}",
            domain="mathematics",
            paradigm="proof",
            idea_id=idea_id,
            idea_title=getattr(idea, "title", ""),
            description=getattr(idea, "description", "")[:500],
            steps=[],
            parameters={
                "conjecture": getattr(idea, "title", ""),
                "proof_strategy": "auto",
                "counterexample_search": {
                    "domain": "integer",
                    "value_range": [-100, 100],
                    "num_trials": 10000,
                },
            },
            expected_outputs=["proof_status", "counterexamples"],
            success_criteria={"no_counterexamples": True},
            resource_requirements=self.resource_requirements(),
        )
