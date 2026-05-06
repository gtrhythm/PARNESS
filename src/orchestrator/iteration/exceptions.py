"""
Iteration-specific exceptions."""


class IterationError(Exception):
    """Base exception for iteration-related errors."""
    pass


class IterationMaxReached(IterationError):
    """Raised when maximum iterations have been reached."""

    def __init__(self, phase: str, max_iterations: int):
        self.phase = phase
        self.max_iterations = max_iterations
        super().__init__(f"Maximum iterations ({max_iterations}) reached for phase: {phase}")



class InvalidStateTransition(IterationError):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: str, to_state: str):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"Invalid transition from {from_state} to {to_state}")


class IterationGateError(IterationError):
    """Raised when a decision gate evaluation fails."""
    pass