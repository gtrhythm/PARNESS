from __future__ import annotations

import logging
import os
import subprocess
from typing import Any, Dict, List, Optional

from ..base import DomainAdapter
from ..models import (
    CorrectionPlan,
    ExperimentFeedback,
    ExperimentPlan,
    ResourceSpec,
    TaskClassification,
    ToolSpec,
    TuningSuggestion,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class GPUBridge:
    """Detect and manage local GPU resources for CS/DL experiments."""

    def __init__(self, resource_bridge=None):
        self.resource_bridge = resource_bridge

    def detect_gpus(self) -> List[Dict[str, Any]]:
        if self.resource_bridge:
            profile = self.resource_bridge.detect()
            return [g.to_dict() for g in profile.gpus]

        gpus = []
        try:
            import torch
            if torch.cuda.is_available():
                for i in range(torch.cuda.device_count()):
                    props = torch.cuda.get_device_properties(i)
                    mem_free, mem_total = torch.cuda.mem_get_info(i)
                    mem_free, mem_total = torch.cuda.mem_get_info(i)
                    gpus.append({
                        "index": i,
                        "name": props.name,
                        "memory_total_mb": mem_total // (1024 * 1024),
                        "memory_free_mb": mem_free // (1024 * 1024),
                        "cuda_version": torch.version.cuda or "",
                    })
        except ImportError:
            logger.debug("PyTorch not available for GPU detection")

        if not gpus:
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.free",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        if not line.strip():
                            continue
                        parts = [p.strip() for p in line.split(",")]
                        if len(parts) >= 4:
                            gpus.append({
                                "index": int(parts[0]),
                                "name": parts[1],
                                "memory_total_mb": int(float(parts[2])),
                                "memory_free_mb": int(float(parts[3])),
                            })
            except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
                pass

        return gpus

    def suggest_batch_size(self, model_params_m: float, seq_length: int = 512,
                           precision: str = "fp32") -> int:
        gpus = self.detect_gpus()
        if not gpus:
            return 8

        gpu = max(gpus, key=lambda g: g.get("memory_free_mb", 0))
        free_mb = gpu.get("memory_free_mb", 0)

        bytes_per_param = 4 if precision == "fp32" else 2
        model_mem_mb = model_params_m * bytes_per_param
        overhead_mb = 2048

        per_sample_mb = model_mem_mb * seq_length / (1024 * 1024) * 0.1
        per_sample_mb = max(per_sample_mb, 10)

        available_mb = free_mb - overhead_mb - model_mem_mb
        if available_mb <= 0:
            return 1

        batch_size = max(1, int(available_mb / per_sample_mb))
        batch_size = min(batch_size, 256)

        if batch_size >= 64:
            batch_size = (batch_size // 8) * 8
        elif batch_size >= 16:
            batch_size = (batch_size // 4) * 4

        return batch_size

    def allocate_gpu(self, required_memory_mb: int = 0) -> Optional[int]:
        gpus = self.detect_gpus()
        if not gpus:
            return None

        for gpu in sorted(gpus, key=lambda g: g.get("memory_free_mb", 0), reverse=True):
            if gpu.get("memory_free_mb", 0) >= required_memory_mb:
                return gpu["index"]

        return gpus[0]["index"] if gpus else None
