import yaml
from pathlib import Path
from typing import Any, Dict, List


class ResourceConfig:
    def __init__(self, config: Dict[str, Any]):
        self._config = config

    @classmethod
    def from_file(cls, path: str) -> "ResourceConfig":
        p = Path(path)
        if not p.exists():
            return cls({})
        with open(p, "r", encoding="utf-8") as f:
            return cls(yaml.safe_load(f) or {})

    @property
    def gpu_available(self) -> bool:
        return self._config.get("hardware", {}).get("gpu", {}).get("available", False)

    @property
    def gpu_type(self) -> str:
        return self._config.get("hardware", {}).get("gpu", {}).get("type", "")

    @property
    def gpu_count(self) -> int:
        return self._config.get("hardware", {}).get("gpu", {}).get("count", 0)

    @property
    def gpu_memory_gb(self) -> int:
        return self._config.get("hardware", {}).get("gpu", {}).get("memory_gb", 0)

    @property
    def cpu_cores(self) -> int:
        return self._config.get("hardware", {}).get("cpu", {}).get("cores", 0)

    @property
    def memory_total_gb(self) -> int:
        return self._config.get("hardware", {}).get("memory", {}).get("total_gb", 0)

    @property
    def storage_total_gb(self) -> int:
        return self._config.get("hardware", {}).get("storage", {}).get("total_gb", 0)

    @property
    def software(self) -> List[Dict[str, str]]:
        return self._config.get("software", [])

    @property
    def network(self) -> List[Dict[str, Any]]:
        return self._config.get("network", [])

    def summary_text(self) -> str:
        lines = []
        hw = self._config.get("hardware", {})
        gpu = hw.get("gpu", {})
        if gpu.get("available"):
            lines.append(
                f"GPU: {gpu.get('type', 'Unknown')} x{gpu.get('count', 0)}, "
                f"{gpu.get('memory_gb', 0)}GB VRAM"
            )
        else:
            lines.append("GPU: Not available")
        lines.append(f"CPU: {hw.get('cpu', {}).get('cores', 0)} cores ({hw.get('cpu', {}).get('architecture', 'unknown')})")
        lines.append(f"Memory: {hw.get('memory', {}).get('total_gb', 0)}GB")
        lines.append(f"Storage: {hw.get('storage', {}).get('total_gb', 0)}GB")
        sw = self._config.get("software", [])
        if sw:
            sw_list = ", ".join(f"{s.get('name', '?')} {s.get('version', '')}" for s in sw)
            lines.append(f"Software: {sw_list}")
        return "\n".join(lines)
