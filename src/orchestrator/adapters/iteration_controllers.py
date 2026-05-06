"""
Iteration Controller Agents.

These replace the framework's built-in iteration logic (ITERATIVE node type
+ DecisionGate) with independent Agent nodes on the DAG graph.

Each controller receives the execution Agent's output and decides whether
to continue iterating or exit, outputting the routing protocol fields
(_route, _score, _metadata).

Usage in YAML:
    - id: iteration_control
      module: threshold_iteration_controller  # or patience_, improving_, etc.
      depends_on: [idea_gen]
      routes:
        continue: idea_gen
        exit: idea_eval
      params:
        max_attempts: 5
        target_score: 7.0
"""

import logging
from typing import Any, Dict, List, Optional

from .base import BaseModule

logger = logging.getLogger(__name__)


class ThresholdIterationControllerModule(BaseModule):
    module_name = "threshold_iteration_controller"

    INPUT_SPEC = {
        "outputs": {"type": "dict", "required": False, "default": {}},
        "_score": {"type": "float", "required": False, "default": 0.0},
        "score": {"type": "float", "required": False, "default": 0.0},
        "_iteration_attempt": {"type": "int", "required": False, "default": 0},
    }
    OUTPUT_SPEC = {
        "_route": {"type": "str"},
        "final_outputs": {"type": "dict"},
        "_score": {"type": "float"},
        "_metadata": {"type": "dict"},
        "refined_inputs": {"type": "dict"},
        "_iteration_attempt": {"type": "int"},
        "_iteration_prev_score": {"type": "float"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        outputs = inputs.get("outputs", inputs)
        score = inputs.get("_score", inputs.get("score", 0.0))
        attempt = inputs.get("_iteration_attempt", 0) + 1
        max_attempts = self.config.get("max_attempts", 5)
        target_score = self.config.get("target_score", 7.0)

        if score >= target_score:
            return {
                "_route": "exit",
                "final_outputs": outputs,
                "_score": score,
                "_metadata": {
                    "attempts": attempt,
                    "final_score": score,
                    "exit_reason": "threshold_met",
                },
            }

        if attempt >= max_attempts:
            return {
                "_route": "exit",
                "final_outputs": outputs,
                "_score": score,
                "_metadata": {
                    "attempts": attempt,
                    "final_score": score,
                    "exit_reason": "max_attempts_reached",
                },
            }

        return {
            "_route": "continue",
            "refined_inputs": outputs,
            "_iteration_attempt": attempt,
            "_iteration_prev_score": score,
            "_score": score,
        }


class PatienceIterationControllerModule(BaseModule):
    module_name = "patience_iteration_controller"

    INPUT_SPEC = {
        "outputs": {"type": "dict", "required": False, "default": {}},
        "_score": {"type": "float", "required": False, "default": 0.0},
        "score": {"type": "float", "required": False, "default": 0.0},
        "_iteration_prev_score": {"type": "float", "required": False, "default": 0.0},
        "_iteration_no_improve": {"type": "int", "required": False, "default": 0},
        "_iteration_attempt": {"type": "int", "required": False, "default": 0},
    }
    OUTPUT_SPEC = {
        "_route": {"type": "str"},
        "final_outputs": {"type": "dict"},
        "_score": {"type": "float"},
        "_metadata": {"type": "dict"},
        "refined_inputs": {"type": "dict"},
        "_iteration_attempt": {"type": "int"},
        "_iteration_prev_score": {"type": "float"},
        "_iteration_no_improve": {"type": "int"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        outputs = inputs.get("outputs", inputs)
        score = inputs.get("_score", inputs.get("score", 0.0))
        prev_score = inputs.get("_iteration_prev_score", 0.0)
        no_improve = inputs.get("_iteration_no_improve", 0)
        attempt = inputs.get("_iteration_attempt", 0) + 1
        max_attempts = self.config.get("max_attempts", 10)
        patience = self.config.get("patience", 3)
        min_delta = self.config.get("min_delta", 0.01)

        improved = score > prev_score + min_delta
        no_improve = 0 if improved else no_improve + 1

        if no_improve >= patience:
            return {
                "_route": "exit",
                "final_outputs": outputs,
                "_score": score,
                "_metadata": {
                    "attempts": attempt,
                    "final_score": score,
                    "exit_reason": "patience_exhausted",
                    "rounds_without_improvement": no_improve,
                },
            }

        if attempt >= max_attempts:
            return {
                "_route": "exit",
                "final_outputs": outputs,
                "_score": score,
                "_metadata": {
                    "attempts": attempt,
                    "final_score": score,
                    "exit_reason": "max_attempts_reached",
                },
            }

        return {
            "_route": "continue",
            "refined_inputs": outputs,
            "_iteration_attempt": attempt,
            "_iteration_prev_score": score,
            "_iteration_no_improve": no_improve,
            "_score": score,
        }


class ImprovingIterationControllerModule(BaseModule):
    module_name = "improving_iteration_controller"

    INPUT_SPEC = {
        "outputs": {"type": "dict", "required": False, "default": {}},
        "_score": {"type": "float", "required": False, "default": 0.0},
        "score": {"type": "float", "required": False, "default": 0.0},
        "_iteration_prev_score": {"type": "float", "required": False, "default": 0.0},
        "_iteration_attempt": {"type": "int", "required": False, "default": 0},
    }
    OUTPUT_SPEC = {
        "_route": {"type": "str"},
        "final_outputs": {"type": "dict"},
        "_score": {"type": "float"},
        "_metadata": {"type": "dict"},
        "refined_inputs": {"type": "dict"},
        "_iteration_attempt": {"type": "int"},
        "_iteration_prev_score": {"type": "float"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        outputs = inputs.get("outputs", inputs)
        score = inputs.get("_score", inputs.get("score", 0.0))
        prev_score = inputs.get("_iteration_prev_score", 0.0)
        attempt = inputs.get("_iteration_attempt", 0) + 1
        max_attempts = self.config.get("max_attempts", 10)
        min_delta = self.config.get("min_delta", 0.01)

        still_improving = score > prev_score + min_delta

        if not still_improving or attempt >= max_attempts:
            reason = "max_attempts_reached" if attempt >= max_attempts else "no_improvement"
            return {
                "_route": "exit",
                "final_outputs": outputs,
                "_score": score,
                "_metadata": {
                    "attempts": attempt,
                    "final_score": score,
                    "exit_reason": reason,
                },
            }

        return {
            "_route": "continue",
            "refined_inputs": outputs,
            "_iteration_attempt": attempt,
            "_iteration_prev_score": score,
            "_score": score,
        }


class LLMIterationControllerModule(BaseModule):
    module_name = "llm_iteration_controller"

    INPUT_SPEC = {
        "outputs": {"type": "dict", "required": False, "default": {}},
        "_score": {"type": "float", "required": False, "default": 0.0},
        "score": {"type": "float", "required": False, "default": 0.0},
        "_iteration_attempt": {"type": "int", "required": False, "default": 0},
        "_iteration_history": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "_route": {"type": "str"},
        "final_outputs": {"type": "dict"},
        "_score": {"type": "float"},
        "_metadata": {"type": "dict"},
        "refined_inputs": {"type": "dict"},
        "_iteration_attempt": {"type": "int"},
        "_iteration_prev_score": {"type": "float"},
        "_iteration_history": {"type": "list"},
        "feedback": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        outputs = inputs.get("outputs", inputs)
        score = inputs.get("_score", inputs.get("score", 0.0))
        attempt = inputs.get("_iteration_attempt", 0) + 1
        history = list(inputs.get("_iteration_history", []))
        max_attempts = self.config.get("max_attempts", 5)

        history.append({"attempt": attempt, "score": score})

        if attempt >= max_attempts:
            return {
                "_route": "exit",
                "final_outputs": outputs,
                "_score": score,
                "_metadata": {
                    "attempts": attempt,
                    "final_score": score,
                    "history": history,
                    "exit_reason": "max_attempts_reached",
                },
            }

        llm_client = self.config.get("llm_client")
        if llm_client is None:
            if score >= self.config.get("target_score", 7.0):
                return {
                    "_route": "exit",
                    "final_outputs": outputs,
                    "_score": score,
                    "_metadata": {"attempts": attempt, "exit_reason": "threshold_fallback"},
                }
            return {
                "_route": "continue",
                "refined_inputs": outputs,
                "_iteration_attempt": attempt,
                "_iteration_prev_score": score,
                "_iteration_history": history,
                "_score": score,
            }

        evaluation_prompt = self.config.get("evaluation_prompt", "").format(
            outputs=outputs,
            score=score,
            attempt=attempt,
            history=history,
            max_attempts=max_attempts,
        )

        judgment = {}
        try:
            judgment = await llm_client.generate(evaluation_prompt)
            should_continue = bool(judgment.get("should_continue", False))
        except Exception as e:
            logger.warning(f"LLM iteration judgment failed: {e}")
            should_continue = score < self.config.get("target_score", 7.0)

        if should_continue:
            return {
                "_route": "continue",
                "refined_inputs": outputs,
                "_iteration_attempt": attempt,
                "_iteration_prev_score": score,
                "_iteration_history": history,
                "_score": score,
                "feedback": judgment.get("feedback", "") if isinstance(judgment, dict) else "",
            }

        return {
            "_route": "exit",
            "final_outputs": outputs,
            "_score": score,
            "_metadata": {
                "attempts": attempt,
                "final_score": score,
                "history": history,
                "exit_reason": "llm_judgment",
            },
        }


class MultiCriteriaIterationControllerModule(BaseModule):
    module_name = "multi_criteria_iteration_controller"

    INPUT_SPEC = {
        "outputs": {"type": "dict", "required": False, "default": {}},
        "_iteration_attempt": {"type": "int", "required": False, "default": 0},
    }
    OUTPUT_SPEC = {
        "_route": {"type": "str"},
        "final_outputs": {"type": "dict"},
        "_score": {"type": "float"},
        "_metadata": {"type": "dict"},
        "refined_inputs": {"type": "dict"},
        "_iteration_attempt": {"type": "int"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    @staticmethod
    def _extract(obj: Any, path: str) -> Optional[float]:
        parts = path.split(".")
        cur = obj
        for p in parts:
            if isinstance(cur, dict):
                cur = cur.get(p)
            else:
                return None
            if cur is None:
                return None
        try:
            return float(cur)
        except (TypeError, ValueError):
            return None

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        outputs = inputs.get("outputs", inputs)
        criteria = self.config.get("criteria", [])
        attempt = inputs.get("_iteration_attempt", 0) + 1
        max_attempts = self.config.get("max_attempts", 5)
        target_score = self.config.get("target_score", 7.0)

        weighted_sum = 0.0
        total_weight = 0.0
        score_details = {}
        for c in criteria:
            val = self._extract(outputs, c.get("path", ""))
            weight = c.get("weight", 1.0)
            if val is not None:
                weighted_sum += val * weight
                total_weight += weight
                score_details[c.get("name", c.get("path"))] = val

        score = weighted_sum / total_weight if total_weight > 0 else 0.0

        if score >= target_score or attempt >= max_attempts:
            reason = "threshold_met" if score >= target_score else "max_attempts_reached"
            return {
                "_route": "exit",
                "final_outputs": outputs,
                "_score": score,
                "_metadata": {
                    "attempts": attempt,
                    "final_score": score,
                    "exit_reason": reason,
                    "score_details": score_details,
                },
            }

        return {
            "_route": "continue",
            "refined_inputs": outputs,
            "_iteration_attempt": attempt,
            "_score": score,
            "_metadata": {"score_details": score_details},
        }


class ResultAggregatorModule(BaseModule):
    """Domain-aware merge of multiple upstream outputs.

    Replaces the old MERGE node type's shallow dict merge with configurable
    strategies.  Designed to be used as a regular SEQUENTIAL node whose
    ``depends_on`` lists the branches to aggregate.

    Strategies:
    - ``concat`` (default): concatenate lists from each source key.
    - ``merge_dict``: shallow-merge dicts, last writer wins.
    - ``best_score``: pick the output with the highest ``_score``.
    - ``all``: wrap all upstream outputs in a dict keyed by node id.
    """

    module_name = "result_aggregator"

    INPUT_SPEC = {
        "_merged_upstream": {"type": "dict", "required": False, "default": {}},
    }
    OUTPUT_SPEC = {
        "aggregated": {"type": "dict"},
        "source_count": {"type": "int"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        strategy = self.config.get("strategy", "all")
        keys = self.config.get("keys", [])
        upstream: Dict[str, Any] = inputs.get("_merged_upstream", {})
        if not upstream:
            upstream = {k: v for k, v in inputs.items() if not k.startswith("_")}

        if strategy == "concat":
            return self._strategy_concat(upstream, keys)
        elif strategy == "merge_dict":
            return self._strategy_merge_dict(upstream)
        elif strategy == "best_score":
            return self._strategy_best_score(inputs, upstream)
        else:
            return {"aggregated": upstream, "source_count": len(upstream)}

    @staticmethod
    def _strategy_concat(upstream: Dict[str, Any], keys: list) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for source_key, source_val in upstream.items():
            if keys and source_key not in keys:
                continue
            if isinstance(source_val, list):
                result.setdefault(source_key, []).extend(source_val)
            elif isinstance(source_val, dict):
                for k, v in source_val.items():
                    result.setdefault(k, []).append(v)
            else:
                result.setdefault(source_key, []).append(source_val)
        return result

    @staticmethod
    def _strategy_merge_dict(upstream: Dict[str, Any]) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        for source_val in upstream.values():
            if isinstance(source_val, dict):
                merged.update(source_val)
        return merged

    @staticmethod
    def _strategy_best_score(inputs: Dict[str, Any], upstream: Dict[str, Any]) -> Dict[str, Any]:
        best_key = None
        best_score = float("-inf")
        for k, v in upstream.items():
            score = v.get("score", float("-inf")) if isinstance(v, dict) else float("-inf")
            if score > best_score:
                best_score = score
                best_key = k
        if best_key is not None:
            return {"best": upstream[best_key], "best_source": best_key, "best_score": best_score}
        return {"aggregated": upstream}


class QualityScorerModule(BaseModule):
    """Evaluate upstream output and emit a routing decision.

    Replaces the old DECISION node type.  Reads upstream output,
    computes a score (via config or LLM), and returns ``_route``
    to control flow.

    Params:
        pass_threshold: float (default 7.0)
        fail_threshold: float (default 4.0)
        score_key: str — dot-path to read score from upstream output
        llm_client: optional LLM client for LLM-based scoring
        scoring_prompt: prompt template for LLM scoring
    """

    module_name = "quality_scorer"

    INPUT_SPEC = {}
    OUTPUT_SPEC = {
        "_route": {"type": "str"},
        "_score": {"type": "float"},
        "quality_score": {"type": "float"},
        "quality_route": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        pass_threshold = self.config.get("pass_threshold", 7.0)
        fail_threshold = self.config.get("fail_threshold", 4.0)
        score_key = self.config.get("score_key", "score")

        score = self._extract_score(inputs, score_key)

        llm_client = self.config.get("llm_client")
        if llm_client is not None and score is None:
            score = await self._llm_score(inputs)

        if score is None:
            score = 0.0

        if score >= pass_threshold:
            route = "pass"
        elif score <= fail_threshold:
            route = "fail"
        else:
            route = "review"

        return {
            "_route": route,
            "_score": score,
            "quality_score": score,
            "quality_route": route,
        }

    @staticmethod
    def _extract_score(inputs: Dict[str, Any], key: str) -> Optional[float]:
        parts = key.split(".")
        cur: Any = inputs
        for p in parts:
            if isinstance(cur, dict):
                cur = cur.get(p)
            else:
                return None
            if cur is None:
                return None
        try:
            return float(cur)
        except (TypeError, ValueError):
            return None

    async def _llm_score(self, inputs: Dict[str, Any]) -> Optional[float]:
        llm_client = self.config.get("llm_client")
        prompt_template = self.config.get("scoring_prompt", "")
        if not prompt_template or not llm_client:
            return None
        prompt = prompt_template.format(inputs=inputs)
        try:
            result = await llm_client.generate(prompt)
            if isinstance(result, dict):
                return float(result.get("score", 0))
            return None
        except Exception:
            return None
