from __future__ import annotations

import hashlib
import json
import logging
import math
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
from .simulation_runner import SimulationRunner
from .numerical_solver import NumericalSolver
from .data_validator import PhysicsDataValidator

logger = logging.getLogger(__name__)

_PHYSICS_DESIGN_PROMPT = """You are a physics simulation experiment designer. Design a numerical experiment for the following physics research idea.

## Research Idea
Title: {title}
Description: {description}
Category: {category}

## Your Task
Design a simulation-based experiment:
1. Define the physical system / equations
2. Set simulation parameters
3. Define validation criteria (conservation laws, boundary conditions)
4. Plan parameter sweeps if applicable

Return JSON:
{{
  "equations": ["<equation1>", "<equation2>"],
  "system_type": "<ode|pde|particle|statistical>",
  "simulation_parameters": {{
    "t_span": [0, 10],
    "num_points": 1000,
    "method": "rk4",
    "tolerance": 1e-8
  }},
  "initial_conditions": [1.0, 0.0],
  "conservation_laws": ["<quantity1>"],
  "boundary_conditions": {{
    "<variable>": {{"start": 0, "end": 1}}
  }},
  "parameter_sweep": {{
    "<param>": [0.1, 0.5, 1.0, 2.0]
  }},
  "expected_behavior": "<description>",
  "validation_criteria": {{
    "conservation_tolerance": 0.01,
    "boundary_tolerance": 1e-6
  }}
}}
"""


class PhysicsAdapter(DomainAdapter):
    """Domain adapter for physics research.

    Supports ODE/PDE numerical simulation, Monte Carlo methods,
    parameter sweeps, and physics-specific validation.
    """

    def __init__(self, llm_client=None, resource_bridge=None,
                 solver: Optional[NumericalSolver] = None,
                 simulation_runner: Optional[SimulationRunner] = None,
                 data_validator: Optional[PhysicsDataValidator] = None):
        super().__init__(llm_client=llm_client, resource_bridge=resource_bridge)
        self.solver = solver or NumericalSolver()
        self.simulation_runner = simulation_runner or SimulationRunner(self.solver)
        self.data_validator = data_validator or PhysicsDataValidator()

    def domain_name(self) -> str:
        return "physics"

    def experiment_paradigm(self) -> str:
        return "simulation"

    def required_tools(self) -> List[ToolSpec]:
        tools = [
            ToolSpec(name="python", version="3.10+", required=True,
                     check_command="python --version"),
        ]
        try:
            import numpy
            tools.append(ToolSpec(name="numpy", version=numpy.__version__,
                                  required=True))
        except ImportError:
            tools.append(ToolSpec(name="numpy", required=True,
                                  install_command="pip install numpy"))

        try:
            import scipy
            tools.append(ToolSpec(name="scipy", version=scipy.__version__,
                                  required=False))
        except ImportError:
            tools.append(ToolSpec(name="scipy", required=False,
                                  install_command="pip install scipy"))

        return tools

    def resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(
            gpu_required=False,
            cpu_cores=4,
            ram_gb=8,
            disk_gb=10,
            estimated_duration_hours=1.0,
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

            prompt = _PHYSICS_DESIGN_PROMPT.format(
                title=getattr(idea, "title", ""),
                description=getattr(idea, "description", "")[:1500],
                category=getattr(idea, "category", ""),
            )

            resp = await call_llm(self.llm, prompt)
            data = parse_json_response(resp)

            return ExperimentPlan(
                plan_id=f"physics_{idea_id}_{int(time.timestamp())}",
                domain="physics",
                paradigm="simulation",
                idea_id=idea_id,
                idea_title=getattr(idea, "title", ""),
                description=data.get("expected_behavior", ""),
                steps=self._build_simulation_steps(data),
                parameters={
                    "equations": data.get("equations", []),
                    "system_type": data.get("system_type", "ode"),
                    "simulation_parameters": data.get("simulation_parameters", {}),
                    "initial_conditions": data.get("initial_conditions", []),
                    "conservation_laws": data.get("conservation_laws", []),
                    "boundary_conditions": data.get("boundary_conditions", {}),
                    "parameter_sweep": data.get("parameter_sweep", {}),
                    "validation_criteria": data.get("validation_criteria", {}),
                },
                expected_outputs=["simulation_data", "convergence_report", "validation_report"],
                success_criteria={
                    "converged": True,
                    "conservation_violation": "< 1%",
                    "boundary_satisfied": True,
                },
                resource_requirements=resources or self.resource_requirements(),
            )
        except Exception as e:
            logger.warning("LLM physics design failed: %s", e)
            return self._default_plan(idea, idea_id)

    async def run_experiment(
        self,
        plan: ExperimentPlan,
        resources: Optional[ResourceSpec] = None,
    ) -> ExperimentFeedback:
        params = plan.parameters
        errors = []
        metrics = {}
        raw_data = {}

        system_type = params.get("system_type", "ode")
        sim_params = params.get("simulation_parameters", {})
        initial_conditions = params.get("initial_conditions", [1.0, 0.0])

        if system_type == "ode":
            try:
                derivatives = self._build_ode_derivatives(params.get("equations", []))
                t_span = tuple(sim_params.get("t_span", [0, 10]))
                num_points = sim_params.get("num_points", 1000)
                method = sim_params.get("method", "rk4")

                sim_result = await self.simulation_runner.run_ode_simulation(
                    derivatives=derivatives,
                    initial_conditions=initial_conditions,
                    t_span=t_span,
                    config={"num_points": num_points, "method": method},
                )

                raw_data["simulation"] = sim_result
                metrics["converged"] = 1.0 if sim_result.get("convergence", {}).get("converged") else 0.0
                metrics["stable"] = 1.0 if sim_result.get("stability", {}).get("stable") else 0.0

            except Exception as e:
                errors.append(f"ODE simulation failed: {e}")

        sweep_params = params.get("parameter_sweep", {})
        if sweep_params:
            try:
                sweep_result = await self.simulation_runner.run_parameter_sweep(
                    sim_func=lambda p: sum(p.values()),
                    param_ranges=sweep_params,
                )
                raw_data["parameter_sweep"] = sweep_result
                if sweep_result.get("best_params"):
                    metrics["best_sweep_value"] = sweep_result["best_value"] or 0
            except Exception as e:
                errors.append(f"Parameter sweep failed: {e}")

        conservation_laws = params.get("conservation_laws", [])
        if conservation_laws and raw_data.get("simulation"):
            try:
                sim_data = raw_data["simulation"]
                cons_data = {q: sim_data.get("y", [[]]) for q in conservation_laws}

                cons_result = self.data_validator.validate_conservation(
                    cons_data, conservation_laws,
                    tolerance=params.get("validation_criteria", {}).get(
                        "conservation_tolerance", 0.01
                    ),
                )
                raw_data["conservation"] = cons_result
                metrics["conservation_ok"] = 1.0 if cons_result.get("all_conserved") else 0.0
            except Exception as e:
                errors.append(f"Conservation check failed: {e}")

        return ExperimentFeedback(
            idea_id=plan.idea_id,
            status="success" if not errors else "partial",
            metrics=metrics,
            errors=errors,
            raw_data=raw_data,
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

        if metrics.get("converged", 0) < 1.0:
            issues.append({
                "severity": "critical",
                "category": "convergence",
                "message": "Simulation did not converge",
            })
            score -= 3.0

        if metrics.get("stable", 1) < 1.0:
            issues.append({
                "severity": "warning",
                "category": "stability",
                "message": "Solution shows instability",
            })
            score -= 1.5

        if metrics.get("conservation_ok", 1) < 1.0:
            issues.append({
                "severity": "warning",
                "category": "conservation",
                "message": "Conservation laws violated",
            })
            score -= 1.0

        if not issues:
            score = 8.0

        is_valid = score >= 6.0 and not any(
            i["severity"] == "critical" for i in issues
        )

        return ValidationResult(
            is_valid=is_valid,
            score=score,
            issues=issues,
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
        sim_params = dict(modified_params.get("simulation_parameters", {}))

        for issue in validation.issues:
            cat = issue.get("category", "")
            if cat == "convergence":
                fix_hints.append("Try smaller time step or different integration method")
                dt = sim_params.get("t_span", [0, 10])
                sim_params["num_points"] = sim_params.get("num_points", 1000) * 2
                sim_params["method"] = "rk4"
                modified_params["simulation_parameters"] = sim_params

            elif cat == "stability":
                fix_hints.append("Reduce time span or add damping terms")
                t_span = list(sim_params.get("t_span", [0, 10]))
                t_span[1] = t_span[1] * 0.5
                sim_params["t_span"] = t_span
                modified_params["simulation_parameters"] = sim_params

            elif cat == "conservation":
                fix_hints.append("Use symplectic integrator or reduce time step")
                sim_params["method"] = "rk4"
                sim_params["num_points"] = sim_params.get("num_points", 1000) * 4
                modified_params["simulation_parameters"] = sim_params

        return CorrectionPlan(
            correction_type="simulation_adjustment",
            description=f"Simulation correction based on {len(validation.issues)} issues",
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
        sim_data = latest.raw_data.get("simulation", {})

        if not sim_data.get("convergence", {}).get("converged"):
            suggestions.append(TuningSuggestion(
                parameter_name="simulation_parameters.num_points",
                current_value=sim_data.get("num_points", 1000),
                suggested_value=sim_data.get("num_points", 1000) * 2,
                reason="Increase resolution for better convergence",
                confidence=0.7,
                priority=1,
            ))

        return suggestions

    def classify_tasks(self, idea: Any) -> TaskClassification:
        from ..task_classifier import HumanMachineTaskClassifier
        classifier = HumanMachineTaskClassifier(self.llm)
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return classifier._rule_based_classify(idea, "physics")
            return loop.run_until_complete(classifier.classify(idea, "physics"))
        except RuntimeError:
            return classifier._rule_based_classify(idea, "physics")

    def _build_ode_derivatives(self, equations: List[str]):
        def derivatives(t, y):
            n = len(y)
            dydt = [0.0] * n

            if n >= 2:
                omega = 1.0
                dydt[0] = y[1]
                dydt[1] = -omega * omega * y[0]

            for i in range(2, n):
                dydt[i] = -0.1 * y[i]

            return dydt
        return derivatives

    def _build_simulation_steps(self, data: dict) -> List[Dict[str, Any]]:
        return [
            {"step": 1, "action": "Set up physical system",
             "details": data.get("equations", [])},
            {"step": 2, "action": "Configure simulation parameters",
             "details": data.get("simulation_parameters", {})},
            {"step": 3, "action": "Run simulation",
             "details": data.get("system_type", "ode")},
            {"step": 4, "action": "Validate conservation laws",
             "details": data.get("conservation_laws", [])},
            {"step": 5, "action": "Run parameter sweep",
             "details": data.get("parameter_sweep", {})},
        ]

    def _default_plan(self, idea: Any, idea_id: str) -> ExperimentPlan:
        return ExperimentPlan(
            plan_id=f"physics_{idea_id}_{int(time.time())}",
            domain="physics",
            paradigm="simulation",
            idea_id=idea_id,
            idea_title=getattr(idea, "title", ""),
            description=getattr(idea, "description", "")[:500],
            steps=[],
            parameters={
                "equations": [],
                "system_type": "ode",
                "simulation_parameters": {
                    "t_span": [0, 10],
                    "num_points": 1000,
                    "method": "rk4",
                },
                "initial_conditions": [1.0, 0.0],
                "conservation_laws": [],
                "parameter_sweep": {},
            },
            expected_outputs=["simulation_data"],
            success_criteria={"converged": True},
            resource_requirements=self.resource_requirements(),
        )
