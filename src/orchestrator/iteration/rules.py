"""
Iteration Rules Module.

Implements convergence detection, decision rules, and scheduling rules.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

from .iteration_types import (
    ConvergenceRule,
    IterationDecision,
    IterationDecisionRule,
    IterationRule,
    IterationStrategy,
    SchedulingPriority,
    SchedulingRule,
    GPU_INTENSIVE_AGENTS,
    MEMORY_INTENSIVE_AGENTS,
    IO_INTENSIVE_AGENTS,
)

logger = logging.getLogger(__name__)


class ConvergenceDetector:
    """Detects convergence in iteration metrics."""
    
    def __init__(self, rules: List[ConvergenceRule]):
        self.rules = rules
        self._metric_history: Dict[str, List[float]] = {}
        self._no_improve_count: Dict[str, int] = {}
        self._best_values: Dict[str, float] = {}
    
    def is_converged(self, metrics: Dict[str, float]) -> bool:
        """Check if all metrics have converged."""
        for rule in self.rules:
            if rule.metric_name not in metrics:
                continue
            
            if not self._check_convergence(rule, metrics[rule.metric_name]):
                return False
        return True
    
    def _check_convergence(self, rule: ConvergenceRule, value: float) -> bool:
        """Check convergence for a single metric."""
        history = self._metric_history.setdefault(rule.metric_name, [])
        history.append(value)
        
        if len(history) < rule.window_size:
            return False
        
        if rule.metric_name not in self._best_values:
            self._best_values[rule.metric_name] = value
        else:
            if rule.direction == "maximize":
                if value > self._best_values[rule.metric_name] + rule.min_delta:
                    self._best_values[rule.metric_name] = value
                    self._no_improve_count[rule.metric_name] = 0
                else:
                    self._no_improve_count[rule.metric_name] = self._no_improve_count.get(rule.metric_name, 0) + 1
            elif rule.direction == "minimize":
                if value < self._best_values[rule.metric_name] - rule.min_delta:
                    self._best_values[rule.metric_name] = value
                    self._no_improve_count[rule.metric_name] = 0
                else:
                    self._no_improve_count[rule.metric_name] = self._no_improve_count.get(rule.metric_name, 0) + 1
        
        if rule.metric_name in self._no_improve_count:
            if self._no_improve_count[rule.metric_name] >= rule.max_no_improve:
                return True
        
        recent = history[-rule.window_size:]
        if len(recent) < 2:
            return False
        
        changes = [abs(recent[i] - recent[i-1]) for i in range(1, len(recent))]
        avg_change = sum(changes) / len(changes)
        
        return avg_change < rule.threshold
    
    def get_trend(self, metric_name: str) -> str:
        """Get trend direction for a metric."""
        history = self._metric_history.get(metric_name, [])
        if len(history) < 2:
            return "unknown"
        
        recent = history[-3:]
        if len(recent) < 2:
            return "unknown"
        
        slope = (recent[-1] - recent[0]) / len(recent)
        threshold = 0.01
        
        if slope > threshold:
            return "improving"
        elif slope < -threshold:
            return "declining"
        else:
            return "stable"
    
    def reset(self) -> None:
        """Reset all tracking state."""
        self._metric_history.clear()
        self._no_improve_count.clear()
        self._best_values.clear()


class DecisionRuleEngine:
    """Engine for evaluating iteration decision rules."""
    
    def __init__(self, rules: List[IterationDecisionRule]):
        self.rules = sorted(rules, key=lambda r: r.priority, reverse=True)
        self._context: Dict[str, Any] = {}
    
    def set_context(self, context: Dict[str, Any]) -> None:
        """Update evaluation context."""
        self._context = context
    
    def evaluate(self, outputs: Dict[str, Any], iteration_count: int) -> IterationDecision:
        """Evaluate rules and return decision."""
        self._context["iteration_count"] = iteration_count
        self._context["outputs"] = outputs
        
        for rule in self.rules:
            if self._check_conditions(rule.conditions):
                logger.info(f"Decision rule matched: {rule.decision.value} (priority={rule.priority})")
                return rule.decision
        
        return IterationDecision.CONTINUE
    
    def _check_conditions(self, conditions: List[Dict[str, Any]]) -> bool:
        """Check if all conditions are met."""
        for cond in conditions:
            if not self._evaluate_condition(cond):
                return False
        return True
    
    def _evaluate_condition(self, cond: Dict[str, Any]) -> bool:
        """Evaluate a single condition."""
        cond_type = cond.get("type", "")
        operator = cond.get("operator", "eq")
        threshold = cond.get("threshold")
        abs_tolerance = cond.get("abs_tolerance", 0.0)
        
        value = self._get_condition_value(cond_type)
        
        if value is None:
            return False
        
        if operator == "eq":
            return abs(value - threshold) <= abs_tolerance
        elif operator == "ne":
            return abs(value - threshold) > abs_tolerance
        elif operator == "gt":
            return value > threshold
        elif operator == "gte":
            return value >= threshold
        elif operator == "lt":
            return value < threshold
        elif operator == "lte":
            return value <= threshold
        else:
            return False
    
    def _get_condition_value(self, cond_type: str) -> Optional[float]:
        """Get value for condition type."""
        if cond_type == "quality_score":
            outputs = self._context.get("outputs", {})
            return outputs.get("quality_score") or outputs.get("score") or outputs.get("avg_score")
        elif cond_type == "quality_delta":
            outputs = self._context.get("outputs", {})
            history = outputs.get("quality_history", [])
            if len(history) >= 2:
                return history[-1] - history[-2]
            return 0.0
        elif cond_type == "conclusion_count":
            outputs = self._context.get("outputs", {})
            conclusions = outputs.get("conclusions", [])
            return float(len(conclusions))
        elif cond_type == "round_count":
            return float(self._context.get("iteration_count", 0))
        elif cond_type == "error_count":
            outputs = self._context.get("outputs", {})
            return float(len(outputs.get("errors", [])))
        elif cond_type == "consecutive_decline":
            outputs = self._context.get("outputs", {})
            return float(outputs.get("consecutive_decline", 0))
        elif cond_type == "novelty_ratio":
            outputs = self._context.get("outputs", {})
            return outputs.get("novelty_ratio", 0.0)
        elif cond_type == "coverage":
            outputs = self._context.get("outputs", {})
            return outputs.get("coverage", 0.0)
        elif cond_type == "hypothesis_quality":
            outputs = self._context.get("outputs", {})
            return outputs.get("hypothesis_quality", 0.0)
        elif cond_type == "evidence_strength":
            outputs = self._context.get("outputs", {})
            return outputs.get("evidence_strength", 0.0)
        elif cond_type == "critique_count":
            outputs = self._context.get("outputs", {})
            return float(len(outputs.get("critiques", [])))
        
        return None


class SchedulingRuleEngine:
    """Engine for evaluating scheduling priority rules."""
    
    def __init__(self, rules: List[SchedulingRule]):
        self.rules = rules
        self._context: Dict[str, Any] = {}
    
    def set_context(self, context: Dict[str, Any]) -> None:
        """Update evaluation context."""
        self._context = context
    
    def evaluate_priority(self, task_info: Dict[str, Any]) -> SchedulingPriority:
        """Evaluate and return scheduling priority for a task."""
        self._context.update(task_info)
        
        for rule in self.rules:
            if self._check_condition(rule.condition):
                return rule.priority
        
        return SchedulingPriority.NORMAL
    
    def _check_condition(self, condition: str) -> bool:
        """Check if a condition expression is true."""
        try:
            return eval(condition, {"context": self._context})
        except Exception:
            return False
    
    def should_preempt(self, task_info: Dict[str, Any]) -> bool:
        """Check if a task can be preempted."""
        priority = self.evaluate_priority(task_info)
        self._context.update(task_info)
        
        for rule in self.rules:
            if rule.priority == priority and rule.preemption_allowed:
                return True
        
        return False


DEFAULT_DECISION_RULES = [
    IterationDecisionRule(
        decision=IterationDecision.EXIT,
        conditions=[
            {"type": "quality_score", "operator": "gte", "threshold": 0.85},
            {"type": "conclusion_count", "operator": "gte", "threshold": 3},
        ],
        priority=10,
    ),
    IterationDecisionRule(
        decision=IterationDecision.REFINE,
        conditions=[
            {"type": "quality_delta", "operator": "eq", "threshold": 0, "abs_tolerance": 0.01},
            {"type": "round_count", "operator": "gte", "threshold": 3},
        ],
        priority=6,
    ),
    IterationDecisionRule(
        decision=IterationDecision.EXIT,
        conditions=[
            {"type": "round_count", "operator": "gte", "threshold": 5},
        ],
        priority=5,
    ),
    IterationDecisionRule(
        decision=IterationDecision.ESCALATE,
        conditions=[
            {"type": "quality_score", "operator": "lt", "threshold": 0.4},
            {"type": "error_count", "operator": "gte", "threshold": 3},
        ],
        priority=9,
        action_config={"new_strategy": "exploration"},
    ),
]

PRIORITY_RULES = [
    SchedulingRule(
        condition="context.get('criticality') == 'CRITICAL'",
        priority=SchedulingPriority.CRITICAL,
        preemption_allowed=True,
    ),
    SchedulingRule(
        condition="len(context.get('depends_on', [])) > 0",
        priority=SchedulingPriority.HIGH,
    ),
    SchedulingRule(
        condition="context.get('round_id', 0) >= context.get('max_rounds', 5) - 1",
        priority=SchedulingPriority.HIGH,
    ),
    SchedulingRule(
        condition="context.get('stage_type') == 'idea_generation'",
        priority=SchedulingPriority.BACKGROUND,
        preemption_allowed=True,
    ),
]

PARALLEL_EXECUTION_RULES = [
    {
        "condition": lambda ctx: ctx.get("agent_type") in GPU_INTENSIVE_AGENTS,
        "max_parallel": 1,
        "reason": "GPU resource intensive"
    },
    {
        "condition": lambda ctx: ctx.get("agent_type") in MEMORY_INTENSIVE_AGENTS,
        "max_parallel": 2,
        "reason": "Memory intensive"
    },
    {
        "condition": lambda ctx: ctx.get("agent_type") in IO_INTENSIVE_AGENTS,
        "max_parallel": 8,
        "reason": "IO bound - high parallelism beneficial"
    },
    {
        "condition": lambda ctx: ctx.get("stage_type") == "sequential",
        "max_parallel": 1,
        "reason": "Sequential stage required"
    },
]


def get_parallel_limit(context: Dict[str, Any], default: int = 4) -> int:
    """Get the parallel limit based on context and rules."""
    for rule in PARALLEL_EXECUTION_RULES:
        if rule["condition"](context):
            return rule["max_parallel"]
    return default
