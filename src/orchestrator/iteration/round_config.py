"""
Round Configuration Module.

Manages multi-round iteration configuration and execution.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

from .iteration_types import (
    ConvergenceRule,
    IterationDecision,
    IterationRule,
    IterationStrategy,
    RoundConfig,
    RoundDependency,
    ParallelExecutionConfig,
)
from .rules import (
    ConvergenceDetector,
    DecisionRuleEngine,
    DEFAULT_DECISION_RULES,
)

logger = logging.getLogger(__name__)


class RoundExecutor:
    """Executes a single round with multiple agents."""
    
    def __init__(
        self,
        round_config: RoundConfig,
        executor_func: Callable,
        parallel_config: Optional[ParallelExecutionConfig] = None,
    ):
        self.round_config = round_config
        self.executor_func = executor_func
        self.parallel_config = parallel_config or ParallelExecutionConfig()
        self._results: List[Dict[str, Any]] = []
    
    async def execute(
        self,
        inputs: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute the round."""
        if self.round_config.parallel_execution and len(self.round_config.agents) > 1:
            return await self._execute_parallel(inputs, context)
        else:
            return await self._execute_sequential(inputs, context)
    
    async def _execute_parallel(
        self,
        inputs: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute agents in parallel."""
        max_parallel = min(
            self.round_config.max_parallel_agents,
            self.parallel_config.global_max_parallel,
            len(self.round_config.agents)
        )
        
        semaphore = asyncio.Semaphore(max_parallel)
        
        async def run_agent(agent: str) -> Dict[str, Any]:
            async with semaphore:
                agent_inputs = self._prepare_agent_inputs(inputs, agent, context)
                try:
                    result = await self.executor_func(agent, agent_inputs)
                    return {"agent": agent, "success": True, "outputs": result}
                except Exception as e:
                    logger.error(f"Agent {agent} failed: {e}")
                    return {"agent": agent, "success": False, "error": str(e)}
        
        tasks = [run_agent(agent) for agent in self.round_config.agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful = []
        errors = []
        for r in results:
            if isinstance(r, Exception):
                errors.append(str(r))
            elif r.get("success"):
                successful.append(r["outputs"])
            else:
                errors.append(r.get("error", "Unknown error"))
        
        return self._aggregate_results(successful, errors)
    
    async def _execute_sequential(
        self,
        inputs: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute agents sequentially."""
        results = []
        for agent in self.round_config.agents:
            agent_inputs = self._prepare_agent_inputs(inputs, agent, context)
            try:
                result = await self.executor_func(agent, agent_inputs)
                results.append({"agent": agent, "success": True, "outputs": result})
            except Exception as e:
                logger.error(f"Agent {agent} failed: {e}")
                results.append({"agent": agent, "success": False, "error": str(e)})
                if not self.round_config.retry_on_failure:
                    break
        
        successful = [r["outputs"] for r in results if r.get("success")]
        errors = [r.get("error", "Unknown error") for r in results if not r.get("success")]
        
        return self._aggregate_results(successful, errors)
    
    def _prepare_agent_inputs(
        self,
        inputs: Dict[str, Any],
        agent: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Prepare inputs for a specific agent."""
        agent_inputs = dict(inputs)
        agent_inputs["_agent_type"] = agent
        agent_inputs["_round_id"] = self.round_config.round_id
        
        if self.round_config.depends_on_rounds:
            prev_round_data = context.get("previous_rounds", {})
            for prev_round_id in self.round_config.depends_on_rounds:
                if prev_round_id in prev_round_data:
                    agent_inputs[f"_prev_round_{prev_round_id}"] = prev_round_data[prev_round_id]
        
        return agent_inputs
    
    def _aggregate_results(
        self,
        successful: List[Dict[str, Any]],
        errors: List[str],
    ) -> Dict[str, Any]:
        """Aggregate results from multiple agents."""
        if not successful:
            return {"success": False, "errors": errors}
        
        if self.round_config.accumulation_mode == "independent":
            return {
                "success": True,
                "results": successful,
                "round_id": self.round_config.round_id,
                "errors": errors,
            }
        elif self.round_config.accumulation_mode == "cumulative":
            merged = {}
            for result in successful:
                merged.update(result)
            return {
                "success": True,
                "results": successful,
                "merged": merged,
                "round_id": self.round_config.round_id,
                "errors": errors,
            }
        else:
            return {
                "success": True,
                "results": successful,
                "round_id": self.round_config.round_id,
                "errors": errors,
            }


class MultiRoundController:
    """Controls multi-round iteration execution."""
    
    def __init__(
        self,
        rounds: List[RoundConfig],
        iteration_rule: IterationRule,
        convergence_rules: Optional[List[ConvergenceRule]] = None,
        decision_rules: Optional[List] = None,
    ):
        self.rounds = rounds
        self.iteration_rule = iteration_rule
        self.convergence_detector = ConvergenceDetector(convergence_rules or [])
        self.decision_engine = DecisionRuleEngine(decision_rules or DEFAULT_DECISION_RULES)
        
        self._round_executors: Dict[int, RoundExecutor] = {}
        self._round_results: Dict[int, Dict[str, Any]] = {}
        self._current_round: int = 0
    
    def get_round_executor(self, round_id: int, executor_func: Callable) -> RoundExecutor:
        """Get or create executor for a round."""
        if round_id not in self._round_executors:
            round_config = self._get_round_config(round_id)
            self._round_executors[round_id] = RoundExecutor(round_config, executor_func)
        return self._round_executors[round_id]
    
    def _get_round_config(self, round_id: int) -> RoundConfig:
        """Get round config by ID."""
        for config in self.rounds:
            if config.round_id == round_id:
                return config
        raise ValueError(f"No round config found for round_id={round_id}")
    
    async def execute_round(
        self,
        round_id: int,
        inputs: Dict[str, Any],
        context: Dict[str, Any],
        executor_func: Callable,
    ) -> Dict[str, Any]:
        """Execute a specific round."""
        executor = self.get_round_executor(round_id, executor_func)
        result = await executor.execute(inputs, context)
        self._round_results[round_id] = result
        
        context = dict(context)
        context["previous_rounds"] = dict(self._round_results)
        
        return result
    
    def should_continue(self, outputs: Dict[str, Any], iteration_count: int) -> bool:
        """Determine if iteration should continue."""
        strategy = self.iteration_rule.strategy
        
        if strategy == IterationStrategy.FIXED:
            return iteration_count < self.iteration_rule.max_rounds
        
        elif strategy == IterationStrategy.CONDITIONAL:
            self.decision_engine.set_context({"iteration_count": iteration_count})
            decision = self.decision_engine.evaluate(outputs, iteration_count)
            return decision != IterationDecision.EXIT
        
        elif strategy == IterationStrategy.ADAPTIVE:
            if iteration_count >= self.iteration_rule.max_rounds:
                return False
            if iteration_count < self.iteration_rule.min_rounds:
                return True
            
            metrics = self._extract_metrics(outputs)
            if self.convergence_detector.is_converged(metrics):
                return False
            
            return True
        
        elif strategy == IterationStrategy.CONVERGENCE:
            metrics = self._extract_metrics(outputs)
            if self.convergence_detector.is_converged(metrics):
                return False
            return iteration_count < self.iteration_rule.max_rounds
        
        elif strategy == IterationStrategy.EXPLORATION:
            return iteration_count < self.iteration_rule.max_rounds
        
        return True
    
    def _extract_metrics(self, outputs: Dict[str, Any]) -> Dict[str, float]:
        """Extract metrics from outputs for convergence detection."""
        metrics = {}
        if "quality_score" in outputs:
            metrics["quality_score"] = outputs["quality_score"]
        if "score" in outputs:
            metrics["score"] = outputs["score"]
        if "convergence_metric" in outputs:
            metrics["convergence_metric"] = outputs["convergence_metric"]
        return metrics
    
    def get_decision(self, outputs: Dict[str, Any], iteration_count: int) -> IterationDecision:
        """Get decision for current iteration."""
        self.decision_engine.set_context({"iteration_count": iteration_count})
        return self.decision_engine.evaluate(outputs, iteration_count)
    
    def reset(self) -> None:
        """Reset controller state."""
        self._round_results.clear()
        self._current_round = 0
        self.convergence_detector.reset()
