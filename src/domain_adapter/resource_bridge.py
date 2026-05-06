from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

from .models import GPUInfo, LocalResourceProfile, ResourceSpec

logger = logging.getLogger(__name__)


class LocalResourceBridge:
    """Detect and manage local compute resources.

    Provides a unified interface to query GPU, CPU, memory, and disk
    resources available on the local machine.
    """

    def __init__(self):
        self._profile: Optional[LocalResourceProfile] = None

    def detect(self, force_refresh: bool = False) -> LocalResourceProfile:
        if self._profile is not None and not force_refresh:
            return self._profile

        profile = LocalResourceProfile(
            gpus=self._detect_gpus(),
            cpu_count=self._detect_cpu_count(),
            cpu_freq_ghz=self._detect_cpu_freq(),
            ram_total_gb=self._detect_ram_total(),
            ram_available_gb=self._detect_ram_available(),
            disk_total_gb=self._detect_disk_total(),
            disk_available_gb=self._detect_disk_available(),
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            cuda_available=self._detect_cuda(),
            platform=f"{platform.system()} {platform.machine()}",
        )

        self._profile = profile
        logger.info(
            "Local resources: CPU=%d cores, RAM=%.1fGB, GPUs=%d, CUDA=%s",
            profile.cpu_count,
            profile.ram_total_gb,
            len(profile.gpus),
            profile.cuda_available,
        )
        return profile

    def can_satisfy(self, spec: ResourceSpec) -> Dict[str, Any]:
        profile = self.detect()
        issues = []

        if spec.gpu_required and not profile.gpus:
            issues.append("GPU required but none available")
        elif spec.gpu_required and profile.gpus:
            available_gpus = [g for g in profile.gpus if g.memory_free_mb >= spec.gpu_memory_gb * 1024]
            if len(available_gpus) < spec.gpu_count:
                issues.append(
                    f"Need {spec.gpu_count} GPU(s) with {spec.gpu_memory_gb}GB, "
                    f"but only {len(available_gpus)} available"
                )

        if spec.ram_gb > 0 and profile.ram_available_gb < spec.ram_gb:
            issues.append(
                f"Need {spec.ram_gb}GB RAM, but only {profile.ram_available_gb:.1f}GB available"
            )

        if spec.cpu_cores > 0 and profile.cpu_count < spec.cpu_cores:
            issues.append(
                f"Need {spec.cpu_cores} CPU cores, but only {profile.cpu_count} available"
            )

        if spec.disk_gb > 0 and profile.disk_available_gb < spec.disk_gb:
            issues.append(
                f"Need {spec.disk_gb}GB disk, but only {profile.disk_available_gb:.1f}GB available"
            )

        return {
            "can_satisfy": len(issues) == 0,
            "issues": issues,
            "profile": profile.to_dict(),
        }

    def _detect_gpus(self) -> List[GPUInfo]:
        gpus = []
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.free,utilization.gpu,driver_version",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 6:
                        gpus.append(GPUInfo(
                            index=int(parts[0]),
                            name=parts[1],
                            memory_total_mb=int(float(parts[2])),
                            memory_free_mb=int(float(parts[3])),
                            utilization_pct=float(parts[4]),
                            driver_version=parts[5],
                            cuda_version="",
                        ))
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError) as e:
            logger.debug("nvidia-smi not available: %s", e)

        if not gpus:
            try:
                result = subprocess.run(
                    ["rocm-smi", "--showid", "--showmeminfo", "vram", "--csv"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    logger.info("AMD GPU detected via rocm-smi")
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        return gpus

    def _detect_cpu_count(self) -> int:
        return os.cpu_count() or 1

    def _detect_cpu_freq(self) -> float:
        try:
            import psutil
            freq = psutil.cpu_freq()
            if freq:
                return round(freq.current / 1000.0, 2)
        except ImportError:
            pass
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "cpu MHz" in line:
                        return round(float(line.split(":")[1].strip()) / 1000.0, 2)
        except (FileNotFoundError, ValueError):
            pass
        return 0.0

    def _detect_ram_total(self) -> float:
        try:
            import psutil
            return round(psutil.virtual_memory().total / (1024 ** 3), 1)
        except ImportError:
            pass
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return round(int(line.split()[1]) / (1024 ** 2), 1)
        except (FileNotFoundError, ValueError):
            pass
        return 0.0

    def _detect_ram_available(self) -> float:
        try:
            import psutil
            return round(psutil.virtual_memory().available / (1024 ** 3), 1)
        except ImportError:
            pass
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        return round(int(line.split()[1]) / (1024 ** 2), 1)
        except (FileNotFoundError, ValueError):
            pass
        return 0.0

    def _detect_disk_total(self) -> float:
        try:
            usage = shutil.disk_usage("/")
            return round(usage.total / (1024 ** 3), 1)
        except OSError:
            return 0.0

    def _detect_disk_available(self) -> float:
        try:
            usage = shutil.disk_usage("/")
            return round(usage.free / (1024 ** 3), 1)
        except OSError:
            return 0.0

    def _detect_cuda(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            pass

        try:
            result = subprocess.run(
                ["nvcc", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
