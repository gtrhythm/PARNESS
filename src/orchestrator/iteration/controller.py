"""
Iteration Controller.

Orchestrates the iteration loop including state management, 
decision gates.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Optional, Protocol

from .state import IterationPhase, IterationState
from .gate import Decision, DecisionGate
from .exceptions import (
    IterationMaxReached,
    InvalidStateTransition,
)

logger = logging.getLogger(__name__)


class StageExecutor(Protocol):
    """Protocol for stage execution functions."""

    async def __call__(self, inputs: Dict[str, Any], state: IterationState) -> Dict[str, Any]:
        ...


class IterationController:
    """
    Controls the iteration loop for research phases.
    
    Minimal implementation:
    - Manages iteration state
    - Evaluates decisions via gates
    """

    def __init__(
        self,
        max_iterations: int = 5,
        default_exit_threshold: float = 7.0,
        default_retry_threshold: float = 4.0,
    ):
        """
        Initialize IterationController.
        
        Args:
            max_iterations: Maximum iterations per phase
            default_exit_threshold: Default score to exit successfully
            default_retry_threshold: Default score to trigger retry
        """
        self.max_iterations = max_iterations
        self.default_exit_threshold = default_exit_threshold
        self.default_retry_threshold = default_retry_threshold
        self.state = IterationState(max_iterations=max_iterations)

    def run_iteration_loop(
        self,
        executor: StageExecutor,
        phase: IterationPhase,
        inputs: Dict[str, Any],
        gate: Optional[DecisionGate] = None,
        pre_hook: Optional[Callable] = None,
        post_hook: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Run an iteration loop until decision is EXIT or max iterations reached.
        
        Args:
            executor: Async function that executes one iteration
            phase: Current iteration phase
            inputs: Initial inputs for the first iteration
            gate: Decision gate for evaluating outputs
            pre_hook: Optional hook called before each iteration
            post_hook: Optional hook called after each iteration
            
        Returns:
            Final outputs after iterations complete
            
        Raises:
            IterationMaxReached: When max iterations is reached
        """
        if gate is None:
            gate = DecisionGate.for_phase(phase.value, exit_threshold=self.default_exit_threshold, retry_threshold=self.default_retry_threshold)

        self.state.phase = phase
        self.state.iteration_count = 0
        current_inputs = dict(inputs)

        while self.state.can_iterate():
            logger.info(f"Iteration {self.state.iteration_count + 1}/{self.max_iterations} for phase {phase.value}")

            if pre_hook:
                pre_hook(current_inputs, self.state)

            if asyncio.iscoroutinefunction(executor):
                outputs = asyncio.run(executor(current_inputs, self.state))
            else:
                outputs = executor(current_inputs, self.state)

            if post_hook:
                post_hook(outputs, self.state)

            decision = gate.evaluate(outputs)
            logger.info(f"Decision: {decision.value}, outputs: {self._summarize_outputs(outputs)}")

            if decision == Decision.EXIT:
                logger.info(f"EXIT decision - iteration loop completed successfully")
                return outputs

            if decision == Decision.CONTINUE:
                self.state.advance_iteration()
                current_inputs = self._prepare_next_iteration(inputs, outputs)
                continue

            if decision == Decision.RETRY:
                self.state.advance_iteration()
                current_inputs = self._prepare_retry(inputs, outputs)
                continue

        raise IterationMaxReached(phase.value, self.max_iterations)

    async def run_iteration_loop_async(
        self,
        executor: StageExecutor,
        phase: IterationPhase,
        inputs: Dict[str, Any],
        gate: Optional[DecisionGate] = None,
        pre_hook: Optional[Callable] = None,
        post_hook: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Async version of run_iteration_loop."""
        if gate is None:
            gate = DecisionGate.for_phase(phase.value, exit_threshold=self.default_exit_threshold, retry_threshold=self.default_retry_threshold)

        self.state.phase = phase
        self.state.iteration_count = 0
        current_inputs = dict(inputs)

        while self.state.can_iterate():
            logger.info(f"Async Iteration {self.state.iteration_count + 1}/{self.max_iterations} for phase {phase.value}")

            if pre_hook:
                await self._call_hook(pre_hook, current_inputs, self.state)

            outputs = await executor(current_inputs, self.state)

            if post_hook:
                await self._call_hook(post_hook, outputs, self.state)

            decision = gate.evaluate(outputs)
            logger.info(f"Decision: {decision.value}, outputs: {self._summarize_outputs(outputs)}")

            if decision == Decision.EXIT:
                logger.info(f"EXIT decision - iteration loop completed successfully")
                return outputs

            if decision == Decision.CONTINUE:
                self.state.advance_iteration()
                current_inputs = self._prepare_next_iteration(inputs, outputs)
                continue

            if decision == Decision.RETRY:
                self.state.advance_iteration()
                current_inputs = self._prepare_retry(inputs, outputs)
                continue

        raise IterationMaxReached(phase.value, self.max_iterations)

    def get_state(self) -> IterationState:
        """Get the current iteration state."""
        return self.state

    def reset(self) -> None:
        """Reset the controller to initial state."""
        self.state = IterationState(max_iterations=self.max_iterations)

    def _prepare_next_iteration(self, original_inputs: Dict[str, Any], outputs: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare inputs for the next iteration based on current outputs."""
        next_inputs = dict(original_inputs)
        next_inputs["_prev_outputs"] = outputs
        next_inputs["_iteration"] = self.state.iteration_count
        return next_inputs

    def _prepare_retry(self, original_inputs: Dict[str, Any], outputs: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare inputs for retry, incorporating lessons from failed attempt."""
        retry_inputs = dict(original_inputs)
        retry_inputs["_prev_outputs"] = outputs
        retry_inputs["_iteration"] = self.state.iteration_count
        retry_inputs["_is_retry"] = True
        return retry_inputs

    def _summarize_outputs(self, outputs: Dict[str, Any]) -> str:
        """Create a brief summary of outputs for logging."""
        if not outputs:
            return "empty"
        summary = {}
        for key, value in outputs.items():
            if isinstance(value, (int, float, str, bool)):
                summary[key] = value
            elif isinstance(value, dict):
                summary[key] = f"dict({len(value)})"
            elif isinstance(value, list):
                summary[key] = f"list({len(value)})"
            else:
                summary[key] = type(value).__name__
        return str(summary)

    async def _call_hook(self, hook: Callable, *args) -> None:
        """Call a hook function, handling both sync and async hooks."""
        if asyncio.iscoroutinefunction(hook):
            await hook(*args)
        else:
            hook(*args)