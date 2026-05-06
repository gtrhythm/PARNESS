from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class PipelineContext:
    session_id: str
    config: Dict[str, Any]
    _data: Dict[str, Any] = field(default_factory=dict)
    _metadata: Dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def require(self, key: str) -> Any:
        if key not in self._data:
            raise KeyError(
                f"PipelineContext missing required key: '{key}'. "
                f"Available keys: {list(self._data.keys())}"
            )
        return self._data[key]

    def has(self, key: str) -> bool:
        return key in self._data

    def keys(self) -> List[str]:
        return list(self._data.keys())

    def snapshot(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "data_keys": list(self._data.keys()),
            "metadata": dict(self._metadata),
        }
