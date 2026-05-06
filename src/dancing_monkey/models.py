from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RandomnessMode(Enum):
    FULL_RANDOM = "full_random"
    SEMANTIC_PERTURBATION = "semantic_perturbation"
    INTERPOLATION = "interpolation"


class ChaosLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


CHAOS_NOISE_SCALE = {
    ChaosLevel.LOW: 0.1,
    ChaosLevel.MEDIUM: 0.3,
    ChaosLevel.HIGH: 0.6,
    ChaosLevel.EXTREME: 1.0,
}


@dataclass
class DancingMonkeyConfig:
    mode: RandomnessMode = RandomnessMode.FULL_RANDOM
    chaos_level: ChaosLevel = ChaosLevel.MEDIUM
    embedding_dim: int = 128
    activation_probability: float = 0.3
    num_seeds: int = 3
    search_top_k: int = 5
    llm_temperature: float = 0.9
    perturbation_scale: Optional[float] = None
    interpolation_alpha: float = 0.5
    source_collections: List[str] = field(
        default_factory=lambda: ["ideas", "insights", "seeds"]
    )
    use_llm_inversion: bool = True
    inversion_rounds: int = 2


@dataclass
class VectorSeed:
    vector: List[float]
    source: str = ""
    source_description: str = ""
    mode: RandomnessMode = RandomnessMode.FULL_RANDOM
    noise_scale: float = 0.0
    nearest_neighbors: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class InversionResult:
    seed: VectorSeed
    generated_text: str
    embedding_distance: float = 0.0
    surprise_score: float = 0.0
    coherence_score: float = 0.0


@dataclass
class DancingMonkeyResult:
    mode: RandomnessMode
    seeds: List[VectorSeed]
    inversion_results: List[InversionResult]
    inspiration_prompt: str = ""
    chemistry_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
