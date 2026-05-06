from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PhysicsDataValidator:
    """Validate physics simulation results against physical laws and constraints.

    Checks conservation laws, boundary conditions, symmetry properties,
    and consistency with known physical behavior.
    """

    def validate_conservation(
        self,
        data: Dict[str, Any],
        conserved_quantities: List[str],
        tolerance: float = 0.01,
    ) -> Dict[str, Any]:
        results = {}
        all_conserved = True

        for quantity in conserved_quantities:
            values = data.get(quantity, [])
            if not values:
                results[quantity] = {"conserved": False, "reason": "No data"}
                all_conserved = False
                continue

            initial = values[0]
            max_deviation = max(abs(v - initial) for v in values)
            relative_error = max_deviation / max(abs(initial), 1e-15)

            conserved = relative_error < tolerance
            results[quantity] = {
                "conserved": conserved,
                "initial_value": initial,
                "max_deviation": max_deviation,
                "relative_error": relative_error,
                "tolerance": tolerance,
            }
            if not conserved:
                all_conserved = False

        return {
            "all_conserved": all_conserved,
            "details": results,
        }

    def validate_boundary_conditions(
        self,
        data: Dict[str, Any],
        boundaries: Dict[str, Dict[str, float]],
    ) -> Dict[str, Any]:
        results = {}
        all_satisfied = True

        for var_name, conditions in boundaries.items():
            values = data.get(var_name, [])
            if not values:
                results[var_name] = {"satisfied": False, "reason": "No data"}
                all_satisfied = False
                continue

            checks = {}

            if "start" in conditions:
                start_match = abs(values[0] - conditions["start"]) < 1e-6
                checks["start"] = {
                    "expected": conditions["start"],
                    "actual": values[0],
                    "satisfied": start_match,
                }

            if "end" in conditions:
                end_match = abs(values[-1] - conditions["end"]) < 1e-6
                checks["end"] = {
                    "expected": conditions["end"],
                    "actual": values[-1],
                    "satisfied": end_match,
                }

            if "min" in conditions:
                min_ok = all(v >= conditions["min"] - 1e-10 for v in values)
                checks["min"] = {
                    "expected": conditions["min"],
                    "actual_min": min(values),
                    "satisfied": min_ok,
                }

            if "max" in conditions:
                max_ok = all(v <= conditions["max"] + 1e-10 for v in values)
                checks["max"] = {
                    "expected": conditions["max"],
                    "actual_max": max(values),
                    "satisfied": max_ok,
                }

            var_satisfied = all(c["satisfied"] for c in checks.values())
            results[var_name] = {
                "satisfied": var_satisfied,
                "checks": checks,
            }
            if not var_satisfied:
                all_satisfied = False

        return {
            "all_satisfied": all_satisfied,
            "details": results,
        }

    def validate_physical_constraints(
        self,
        data: Dict[str, Any],
        constraints: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        results = []
        all_valid = True

        for constraint in constraints:
            ctype = constraint.get("type", "")
            desc = constraint.get("description", ctype)

            if ctype == "positive":
                var = constraint["variable"]
                values = data.get(var, [])
                valid = all(v >= 0 for v in values)
                results.append({
                    "type": ctype,
                    "description": desc,
                    "valid": valid,
                    "min_value": min(values) if values else None,
                })

            elif ctype == "bounded":
                var = constraint["variable"]
                lo, hi = constraint["bounds"]
                values = data.get(var, [])
                valid = all(lo <= v <= hi for v in values)
                results.append({
                    "type": ctype,
                    "description": desc,
                    "valid": valid,
                    "range": [min(values) if values else None,
                              max(values) if values else None],
                })

            elif ctype == "monotone_increasing":
                var = constraint["variable"]
                values = data.get(var, [])
                valid = all(values[i] <= values[i + 1] + 1e-10
                            for i in range(len(values) - 1))
                results.append({
                    "type": ctype,
                    "description": desc,
                    "valid": valid,
                })

            elif ctype == "energy_positive":
                energy_values = data.get("energy", data.get("E", []))
                valid = all(e >= -1e-10 for e in energy_values)
                results.append({
                    "type": ctype,
                    "description": desc,
                    "valid": valid,
                    "min_energy": min(energy_values) if energy_values else None,
                })

            if not results[-1]["valid"]:
                all_valid = False

        return {
            "all_valid": all_valid,
            "details": results,
        }

    def compare_with_analytical(
        self,
        numerical: Dict[str, Any],
        analytical: Dict[str, Any],
        tolerance: float = 0.01,
    ) -> Dict[str, Any]:
        results = {}
        max_error = 0.0

        for var_name in analytical:
            num_values = numerical.get(var_name, [])
            ana_values = analytical[var_name]

            if not num_values or not ana_values:
                continue

            min_len = min(len(num_values), len(ana_values))
            errors = [
                abs(num_values[i] - ana_values[i])
                for i in range(min_len)
            ]

            max_err = max(errors) if errors else 0
            mean_err = sum(errors) / len(errors) if errors else 0

            results[var_name] = {
                "max_error": max_err,
                "mean_error": mean_err,
                "within_tolerance": max_err < tolerance,
            }
            max_error = max(max_error, max_err)

        return {
            "overall_max_error": max_error,
            "within_tolerance": max_error < tolerance,
            "tolerance": tolerance,
            "per_variable": results,
        }
