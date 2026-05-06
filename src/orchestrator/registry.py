from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from .exceptions import ModuleNotRegisteredError

if TYPE_CHECKING:
    from .protocols import ProgressDispatcher


@dataclass
class ModuleSpec:
    name: str
    display_name: str
    description: str = ""
    input_schema: Dict[str, str] = field(default_factory=dict)
    output_schema: Dict[str, str] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    conflicts_with: List[str] = field(default_factory=list)
    tags: Set[str] = field(default_factory=set)
    factory: Optional[Callable] = None


class ModuleRegistry:
    def __init__(self, hook_dispatcher: Optional["ProgressDispatcher"] = None):
        self._modules: Dict[str, ModuleSpec] = {}
        self._dispatcher = hook_dispatcher

    def register(self, spec: ModuleSpec) -> None:
        if spec.name in self._modules:
            raise ValueError(f"Module '{spec.name}' already registered")
        self._modules[spec.name] = spec

    def get(self, name: str) -> Optional[ModuleSpec]:
        return self._modules.get(name)

    def get_or_raise(self, name: str) -> ModuleSpec:
        spec = self._modules.get(name)
        if not spec:
            raise ModuleNotRegisteredError(name, list(self._modules.keys()))
        return spec

    def has(self, name: str) -> bool:
        return name in self._modules

    def list_modules(self) -> List[ModuleSpec]:
        return list(self._modules.values())

    def list_names(self) -> List[str]:
        return list(self._modules.keys())

    def create_instance(self, name: str, config: Dict = None, node_id: str = None) -> Any:
        spec = self.get_or_raise(name)
        if spec.factory is None:
            raise ValueError(f"Module '{name}' has no factory")
        instance = spec.factory(config or {})
        return instance

    def validate_dependencies(self, enabled: Set[str]) -> List[str]:
        errors = []
        for name in enabled:
            spec = self._modules.get(name)
            if not spec:
                continue
            for dep in spec.depends_on:
                if dep not in enabled:
                    errors.append(f"Module '{name}' depends on '{dep}' which is not enabled")
        return errors
