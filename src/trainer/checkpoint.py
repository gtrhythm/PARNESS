import os
import json
import torch
from pathlib import Path
from typing import Dict, Any, Optional


class CheckpointManager:
    def __init__(self, checkpoint_dir: str):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save(self, path: str, state: Dict[str, Any], metadata: Optional[Dict] = None) -> str:
        full_path = self.checkpoint_dir / path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        checkpoint = {"state": state, "metadata": metadata or {}}
        torch.save(checkpoint, full_path)
        return str(full_path)

    def load(self, path: str) -> Dict[str, Any]:
        full_path = self.checkpoint_dir / path if not Path(path).is_absolute() else Path(path)
        if not full_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {full_path}")
        checkpoint = torch.load(full_path, map_location="cpu")
        return checkpoint

    def exists(self, path: str) -> bool:
        full_path = self.checkpoint_dir / path if not Path(path).is_absolute() else Path(path)
        return full_path.exists()

    def list_checkpoints(self) -> list:
        if not self.checkpoint_dir.exists():
            return []
        return [str(p.relative_to(self.checkpoint_dir)) 
                for p in self.checkpoint_dir.rglob("*.pt")]
