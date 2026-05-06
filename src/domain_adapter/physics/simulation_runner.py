from __future__ import annotations

import logging
import math
from typing import Any, Callable, Dict, List, Optional, Tuple

from .numerical_solver import NumericalSolver

logger = logging.getLogger(__name__)


class SimulationRunner:
    """Run physics simulations with configurable parameters.

    Wraps NumericalSolver with physics-specific simulation management,
    including convergence checking, stability analysis, and result collection.
    """

    def __init__(self, solver: Optional[NumericalSolver] = None):
        self.solver = solver or NumericalSolver()

    async def run_ode_simulation(
        self,
        derivatives: Callable,
        initial_conditions: List[float],
        t_span: Tuple[float, float],
        config: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        cfg = config or {}
        num_points = cfg.get("num_points", 1000)
        method = cfg.get("method", "rk4")

        result = self.solver.solve_ode(
            derivatives, initial_conditions, t_span,
            num_points=num_points, method=method,
        )

        convergence = self._check_convergence(result)
        stability = self._check_stability(result)

        result["convergence"] = convergence
        result["stability"] = stability
        result["config"] = cfg

        return result

    async def run_parameter_sweep(
        self,
        sim_func: Callable,
        param_ranges: Dict[str, List[float]],
        config: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        result = self.solver.parameter_sweep(sim_func, param_ranges)
        result["config"] = config or {}
        return result

    async def run_monte_carlo(
        self,
        func: Callable,
        bounds: List[Tuple[float, float]],
        num_samples: int = 100000,
    ) -> Dict[str, Any]:
        return self.solver.monte_carlo_integrate(func, bounds, num_samples)

    def _check_convergence(self, result: Dict[str, Any]) -> Dict[str, Any]:
        y = result.get("y", [])
        if not y:
            return {"converged": False, "reason": "No data"}

        last_points = y[-min(100, len(y)):]
        if len(last_points) < 10:
            return {"converged": True, "reason": "Insufficient data to assess"}

        n_vars = len(y[0]) if y else 0
        for j in range(n_vars):
            values = [p[j] for p in last_points]
            variance = sum((v - sum(values) / len(values))**2 for v in values) / len(values)
            if any(math.isnan(v) or math.isinf(v) for v in values):
                return {"converged": False, "reason": f"Variable {j} diverged (NaN/Inf)"}
            if variance > 1e6:
                return {"converged": False, "reason": f"Variable {j} oscillating wildly"}

        return {"converged": True, "reason": "Solution appears stable"}

    def _check_stability(self, result: Dict[str, Any]) -> Dict[str, Any]:
        y = result.get("y", [])
        if not y or len(y) < 10:
            return {"stable": True, "note": "Too few points to assess"}

        n_vars = len(y[0]) if y else 0
        max_values = [0.0] * n_vars
        growing_vars = []

        for j in range(n_vars):
            for i in range(1, len(y)):
                if abs(y[i][j]) > max_values[j]:
                    max_values[j] = abs(y[i][j])

            if max_values[j] > 1e10:
                growing_vars.append(j)

        if growing_vars:
            return {
                "stable": False,
                "growing_variables": growing_vars,
                "max_values": max_values,
            }

        return {"stable": True, "max_values": max_values}
