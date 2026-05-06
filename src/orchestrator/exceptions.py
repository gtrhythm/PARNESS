from typing import List, Optional


class SchedulerError(Exception):
    def __init__(self, message: str = ""):
        super().__init__(message)
        self.message = message


class StageSkipped(SchedulerError):
    def __init__(self, stage_name: str, reason: str = ""):
        self.stage_name = stage_name
        self.reason = reason
        super().__init__(f"Stage '{stage_name}' skipped: {reason}")


class StageFailed(SchedulerError):
    def __init__(self, stage_name: str, cause: Optional[Exception] = None):
        self.stage_name = stage_name
        self.cause = cause
        msg = f"Stage '{stage_name}' failed"
        if cause:
            msg += f": {cause}"
        super().__init__(msg)


class StageTimeout(StageFailed):
    def __init__(self, stage_name: str, timeout_seconds: int):
        self.timeout_seconds = timeout_seconds
        super().__init__(stage_name, cause=TimeoutError(f"exceeded {timeout_seconds}s"))


class PipelineFatalError(SchedulerError):
    def __init__(self, message: str, stage_name: str = ""):
        self.stage_name = stage_name
        super().__init__(message)


class ModuleNotRegisteredError(SchedulerError):
    def __init__(self, module_name: str, available: Optional[List[str]] = None):
        self.module_name = module_name
        self.available = available or []
        avail_str = ", ".join(self.available) if self.available else "none"
        super().__init__(f"Module '{module_name}' not registered. Available: [{avail_str}]")


class CircularDependencyError(SchedulerError):
    def __init__(self, stages: Optional[List[str]] = None):
        self.stages = stages or []
        stages_str = ", ".join(self.stages) if self.stages else "unknown"
        super().__init__(f"Circular dependency detected among stages: [{stages_str}]")


class ConditionEvalError(SchedulerError):
    def __init__(self, expression: str, error: str = ""):
        self.expression = expression
        self.error = error
        super().__init__(f"Failed to evaluate condition '{expression}': {error}")
