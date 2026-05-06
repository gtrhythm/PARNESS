"""
Iteration Types Module.

Defines enums and dataclasses for multi-round iteration rules and scheduling.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class IterationStrategy(str, Enum):
    """Iteration strategy types."""
    FIXED = "fixed"
    CONDITIONAL = "conditional"
    ADAPTIVE = "adaptive"
    CONVERGENCE = "convergence"
    EXPLORATION = "exploration"


class IterationDecision(str, Enum):
    """Iteration decision types."""
    CONTINUE = "continue"
    EXIT = "exit"
    RETRY = "retry"
    REFINE = "refine"

    ESCALATE = "escalate"
    RESTRUCTURE = "restructure"


class RoundRelation(str, Enum):
    """Round dependency types."""
    INDEPENDENT = "independent"
    SEQUENTIAL = "sequential"
    BRANCH_MERGE = "branch_merge"
    CUMULATIVE = "cumulative"
    CONDITIONAL = "conditional"


class IterationStatus(str, Enum):
    """Iteration state machine states."""
    INIT = "init"
    RUNNING = "running"
    EVALUATING = "evaluating"
    DECIDING = "deciding"
    CHECKPOINTED = "checkpointed"

    EXITED = "exited"
    FAILED = "failed"


class SchedulingPriority(int, Enum):
    """Task scheduling priority levels."""
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    BACKGROUND = 5


class ParallelExecutionMode(str, Enum):
    """Parallel execution modes."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    PIPELINED = "pipelined"


@dataclass
class IterationRule:
    """Multi-round iteration rule configuration."""
    strategy: IterationStrategy = IterationStrategy.FIXED
    max_rounds: int = 5
    min_rounds: int = 1
    
    trigger_conditions: List[Dict[str, Any]] = field(default_factory=list)
    
    convergence_threshold: float = 0.8
    convergence_window: int = 3
    
    early_stop_patience: int = 2
    escalation_threshold: float = 0.3
    
    add_only: bool = False
    merge_strategy: str = "concat"


@dataclass
class IterationDecisionRule:
    """Rule that maps conditions to a decision."""
    decision: IterationDecision
    conditions: List[Dict[str, Any]]
    priority: int = 0
    action_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConvergenceRule:
    """Convergence detection rule."""
    metric_name: str
    direction: str = "maximize"
    threshold: float = 0.05
    window_size: int = 3
    patience: int = 2
    min_delta: float = 0.01
    min_quality: float = 0.6
    max_no_improve: int = 3


@dataclass
class RoundDependency:
    """Round dependency configuration."""
    round_id: int
    relation: RoundRelation = RoundRelation.INDEPENDENT
    depends_on: List[int] = field(default_factory=list)
    condition: Optional[str] = None
    merge_strategy: str = "concat"
    isolation_level: str = "full"


@dataclass
class RoundConfig:
    """Configuration for a single iteration round."""
    round_id: int
    agents: List[str] = field(default_factory=list)
    
    input_sources: List[str] = field(default_factory=list)
    input_relation: RoundRelation = RoundRelation.INDEPENDENT
    depends_on_rounds: List[int] = field(default_factory=list)
    
    output_formats: List[str] = field(default_factory=list)
    accumulation_mode: str = "independent"
    
    parallel_execution: bool = True
    max_parallel_agents: int = 4
    
    exit_conditions: List[Dict[str, Any]] = field(default_factory=list)
    retry_on_failure: bool = True
    max_retries: int = 2


@dataclass
class ParallelExecutionConfig:
    """Configuration for parallel execution."""
    global_max_parallel: int = 8
    max_memory_per_agent: int = 8 * 1024 * 1024 * 1024
    
    reserve_gpu_for_agents: List[str] = field(default_factory=list)
    reserve_memory_percent: float = 0.2
    
    load_balancing_strategy: str = "round_robin"
    max_queue_size_per_agent: int = 10
    
    partial_failure_threshold: float = 0.5
    continue_on_branch_failure: bool = True
    
    agent_affinity: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class SchedulingRule:
    """Scheduling priority rule."""
    condition: str
    priority: SchedulingPriority = SchedulingPriority.NORMAL
    preemption_allowed: bool = False
    timeout_seconds: Optional[int] = None


@dataclass
class AgentParallelConfig:
    """Per-agent parallel execution configuration."""
    agent_type: str
    max_parallel: int = 1
    is_gpu_intensive: bool = False
    is_memory_intensive: bool = False
    preferred_modules: List[str] = field(default_factory=list)


GPU_INTENSIVE_AGENTS = {"replication", "hypothesis", "evidence"}
MEMORY_INTENSIVE_AGENTS = {"survey", "meta_analysis"}
IO_INTENSIVE_AGENTS = {"transfer", "critique", "limitation"}
