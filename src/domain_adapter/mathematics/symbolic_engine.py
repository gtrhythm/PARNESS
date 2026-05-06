from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SymbolicEngine:
    """Symbolic computation engine for mathematical research.

    Uses SymPy for symbolic manipulation, equation solving,
    simplification, and verification.
    """

    def __init__(self):
        self._sympy = None

    def _get_sympy(self):
        if self._sympy is None:
            try:
                import sympy
                self._sympy = sympy
            except ImportError:
                raise ImportError(
                    "SymPy is required for mathematical symbolic computation. "
                    "Install with: pip install sympy"
                )
        return self._sympy

    def simplify(self, expression: str) -> Dict[str, Any]:
        sp = self._get_sympy()
        try:
            expr = sp.sympify(expression)
            simplified = sp.simplify(expr)
            return {
                "original": str(expr),
                "simplified": str(simplified),
                "is_equal": sp.simplify(expr - simplified) == 0,
            }
        except Exception as e:
            return {"error": str(e), "original": expression}

    def solve_equation(self, equation: str, variable: str = "x") -> Dict[str, Any]:
        sp = self._get_sympy()
        try:
            x = sp.Symbol(variable)
            if "=" in equation:
                lhs, rhs = equation.split("=", 1)
                expr = sp.sympify(lhs) - sp.sympify(rhs)
            else:
                expr = sp.sympify(equation)

            solutions = sp.solve(expr, x)
            return {
                "equation": equation,
                "variable": variable,
                "solutions": [str(s) for s in solutions],
                "num_solutions": len(solutions),
            }
        except Exception as e:
            return {"error": str(e), "equation": equation}

    def verify_identity(self, lhs: str, rhs: str) -> Dict[str, Any]:
        sp = self._get_sympy()
        try:
            left = sp.sympify(lhs)
            right = sp.sympify(rhs)
            diff = sp.simplify(left - right)
            is_identity = diff == 0

            if not is_identity:
                test_vals = self._numerical_check(left, right)

            return {
                "lhs": str(left),
                "rhs": str(right),
                "is_identity": is_identity,
                "difference": str(diff),
            }
        except Exception as e:
            return {"error": str(e), "lhs": lhs, "rhs": rhs, "is_identity": False}

    def differentiate(self, expression: str, variable: str = "x") -> Dict[str, Any]:
        sp = self._get_sympy()
        try:
            x = sp.Symbol(variable)
            expr = sp.sympify(expression)
            derivative = sp.diff(expr, x)
            return {
                "original": str(expr),
                "derivative": str(derivative),
                "variable": variable,
            }
        except Exception as e:
            return {"error": str(e), "original": expression}

    def integrate(self, expression: str, variable: str = "x") -> Dict[str, Any]:
        sp = self._get_sympy()
        try:
            x = sp.Symbol(variable)
            expr = sp.sympify(expression)
            integral = sp.integrate(expr, x)
            has_closed_form = integral is not sp.Integral(expr, x)
            return {
                "original": str(expr),
                "integral": str(integral),
                "variable": variable,
                "has_closed_form": has_closed_form,
            }
        except Exception as e:
            return {"error": str(e), "original": expression}

    def expand(self, expression: str) -> Dict[str, Any]:
        sp = self._get_sympy()
        try:
            expr = sp.sympify(expression)
            expanded = sp.expand(expr)
            return {"original": str(expr), "expanded": str(expanded)}
        except Exception as e:
            return {"error": str(e), "original": expression}

    def _numerical_check(self, left, right, n_tests: int = 20) -> Dict[str, Any]:
        import random
        sp = self._get_sympy()
        symbols = list(left.free_symbols.union(right.free_symbols))
        if not symbols:
            return {"numerical_match": sp.simplify(left - right) == 0}

        matches = 0
        mismatches = []
        for _ in range(n_tests):
            vals = {s: random.uniform(-10, 10) for s in symbols}
            try:
                l_val = float(left.subs(vals))
                r_val = float(right.subs(vals))
                if abs(l_val - r_val) < 1e-10:
                    matches += 1
                else:
                    mismatches.append({
                        "values": {str(k): v for k, v in vals.items()},
                        "lhs": l_val,
                        "rhs": r_val,
                    })
            except (TypeError, ValueError, ZeroDivisionError):
                continue

        return {
            "numerical_matches": matches,
            "numerical_mismatches": len(mismatches),
            "sample_mismatches": mismatches[:3],
        }
