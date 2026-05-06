from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class TrainConfig:
    epochs: int = 10
    batch_size: int = 32
    learning_rate: float = 0.001
    optimizer: str = "adam"
    weight_decay: float = 0.0
    gradient_clip: float = 1.0
    warmup_steps: int = 0
    checkpoint_dir: str = "./checkpoints"
    log_interval: int = 10
    eval_interval: int = 100
    save_interval: int = 500
    device: str = "cuda"
    mixed_precision: bool = False
    num_workers: int = 4
    seed: int = 42
    extra_config: Dict = field(default_factory=dict)

    def __post_init__(self):
        if self.optimizer not in ["adam", "sgd", "adamw"]:
            raise ValueError(f"Unsupported optimizer: {self.optimizer}")
        if self.device not in ["cuda", "cpu", "mps"]:
            raise ValueError(f"Unsupported device: {self.device}")
