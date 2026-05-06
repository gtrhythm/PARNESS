from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

import math

logger = logging.getLogger(__name__)


class NumericalSolver:
    """Numerical solvers for physics simulations.

    Provides ODE integration, PDE solving, root finding,
    and optimization routines using scipy/numpy when available,
    with pure-Python fallbacks.
    """

    def __init__(self):
        self._scipy = None
        self._numpy = None

    def _get_numpy(self):
        if self._numpy is None:
            try:
                import numpy
                self._numpy = numpy
            except ImportError:
                self._numpy = None
        return self._numpy

    def _get_scipy(self):
        if self._scipy is None:
            try:
                import scipy
                self._scipy = scipy
            except ImportError:
                self._scipy = None
        return self._scipy

    def solve_ode(
        self,
        derivatives: Callable,
        initial_conditions: List[float],
        t_span: Tuple[float, float],
        num_points: int = 1000,
        method: str = "rk4",
    ) -> Dict[str, Any]:
        t_start, t_end = t_span
        dt = (t_end - t_start) / num_points
        n_vars = len(initial_conditions)

        np = self._get_numpy()
        if np is not None:
            t_array = np.linspace(t_start, t_end, num_points)
            y_array = np.zeros((num_points, n_vars))
        else:
            t_array = [t_start + i * dt for i in range(num_points)]
            y_array = [[0.0] * n_vars for _ in range(num_points)]

        y = list(initial_conditions)
        for i in range(num_points):
            for j in range(n_vars):
                y_array[i][j] = y[j]

            if method == "rk4":
                y = self._rk4_step(derivatives, y, t_array[i], dt)
            else:
                dy = derivatives(t_array[i], y)
                y = [y[j] + dt * dy[j] for j in range(n_vars)]

        return {
            "t": t_array if np is None else t_array.tolist(),
            "y": y_array if np is None else y_array.tolist(),
            "num_points": num_points,
            "method": method,
            "t_span": list(t_span),
        }

    def _rk4_step(
        self,
        f: Callable,
        y: List[float],
        t: float,
        dt: float,
    ) -> List[float]:
        n = len(y)
        k1 = f(t, y)
        k2 = f(t + dt / 2, [y[i] + dt / 2 * k1[i] for i in range(n)])
        k3 = f(t + dt / 2, [y[i] + dt / 2 * k2[i] for i in range(n)])
        k4 = f(t + dt, [y[i] + dt * k3[i] for i in range(n)])

        return [
            y[i] + dt / 6 * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i])
            for i in range(n)
        ]

    def solve_system(
        self,
        equations: List[Callable],
        initial_guess: List[float],
        max_iter: int = 100,
        tol: float = 1e-8,
    ) -> Dict[str, Any]:
        scipy = self._get_scipy()
        if scipy is not None:
            try:
                from scipy.optimize import fsolve
                solution, info, ier, msg = fsolve(
                    equations, initial_guess, full_output=True
                )
                return {
                    "solution": solution.tolist(),
                    "converged": ier == 1,
                    "iterations": info.get("nfev", 0),
                    "message": msg if ier != 1 else "Converged",
                }
            except Exception as e:
                logger.warning("scipy.fsolve failed: %s", e)

        x = list(initial_guess)
        for iteration in range(max_iter):
            residuals = [eq(x) for eq in equations]
            max_residual = max(abs(r) for r in residuals)
            if max_residual < tol:
                return {
                    "solution": x,
                    "converged": True,
                    "iterations": iteration,
                    "message": "Converged",
                }

            for i in range(len(x)):
                eps = max(abs(x[i]) * 1e-7, 1e-10)
                x_plus = list(x)
                x_plus[i] += eps
                deriv = (equations[i](x_plus) - residuals[i]) / eps
                if abs(deriv) > 1e-15:
                    x[i] -= residuals[i] / deriv

        return {
            "solution": x,
            "converged": False,
            "iterations": max_iter,
            "message": "Did not converge",
        }

    def monte_carlo_integrate(
        self,
        func: Callable,
        bounds: List[Tuple[float, float]],
        num_samples: int = 100000,
    ) -> Dict[str, Any]:
        np = self._get_numpy()
        n_dims = len(bounds)

        volume = 1.0
        for lo, hi in bounds:
            volume *= (hi - lo)

        total = 0.0
        total_sq = 0.0

        for _ in range(num_samples):
            if np is not None:
                point = [np.random.uniform(lo, hi) for lo, hi in bounds]
            else:
                import random
                point = [random.uniform(lo, hi) for lo, hi in bounds]

            val = func(point)
            total += val
            total_sq += val * val

        mean = total / num_samples
        variance = (total_sq / num_samples - mean * mean) / num_samples
        std_error = math.sqrt(variance) if variance > 0 else 0.0

        result = volume * mean
        error = volume * std_error

        return {
            "result": result,
            "error": error,
            "num_samples": num_samples,
            "dimensions": n_dims,
            "relative_error": abs(error / result) if abs(result) > 1e-15 else float("inf"),
        }

    def parameter_sweep(
        self,
        func: Callable,
        param_ranges: Dict[str, List[float]],
    ) -> Dict[str, Any]:
        np = self._get_numpy()

        param_names = list(param_ranges.keys())
        param_values = list(param_ranges.values())

        if np is not None:
            grids = [np.array(v) for v in param_values]
            mesh = np.meshgrid(*grids, indexing="ij")
            total_points = 1
            for v in param_values:
                total_points *= len(v)
        else:
            mesh = None
            total_points = 1
            for v in param_values:
                total_points *= len(v)

        results = []
        best_value = None
        best_params = None

        indices = [0] * len(param_names)
        for flat_idx in range(total_points):
            params = {}
            for d in range(len(param_names)):
                params[param_names[d]] = param_values[d][indices[d]]

            try:
                value = func(params)
                results.append({"params": params, "value": value})

                if best_value is None or value > best_value:
                    best_value = value
                    best_params = dict(params)
            except Exception as e:
                results.append({"params": params, "error": str(e)})

            for d in range(len(param_names) - 1, -1, -1):
                indices[d] += 1
                if indices[d] < len(param_values[d]):
                    break
                indices[d] = 0

        return {
            "total_points": total_points,
            "best_params": best_params,
            "best_value": best_value,
            "results_summary": results[:100],
        }
