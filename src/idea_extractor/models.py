"""Idea Extractor 数据模型定义"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
import json
import uuid
import time


class InnovationType(str, Enum):
    ARCHITECTURE = "architecture"
    METHOD = "method"
    SCENARIO = "scenario"
    DATA = "data"
    LOSS_FUNCTION = "loss_function"
    TRAINING_TRICK = "training_trick"
    OTHER = "other"


@dataclass
class ExtractedInnovation:
    title: str = ""
    description: str = ""
    innovation_type: str = InnovationType.OTHER.value
    confidence: float = 0.0
    location: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "innovation_type": self.innovation_type,
            "confidence": self.confidence,
            "location": self.location,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExtractedInnovation":
        return cls(
            title=data.get("title", ""),
            description=data.get("description", ""),
            innovation_type=data.get("innovation_type", InnovationType.OTHER.value),
            confidence=data.get("confidence", 0.0),
            location=data.get("location", ""),
        )


@dataclass
class ExtractedMethod:
    name: str = ""
    description: str = ""
    key_components: List[str] = field(default_factory=list)
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    differences_from_prior: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "key_components": self.key_components,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "differences_from_prior": self.differences_from_prior,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExtractedMethod":
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            key_components=data.get("key_components", []),
            inputs=data.get("inputs", []),
            outputs=data.get("outputs", []),
            differences_from_prior=data.get("differences_from_prior", []),
        )


@dataclass
class ExtractedScenario:
    large_scenario: str = ""
    small_scenario: str = ""
    extendable_scenarios: List[str] = field(default_factory=list)
    data_type: str = ""
    task_type: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "large_scenario": self.large_scenario,
            "small_scenario": self.small_scenario,
            "extendable_scenarios": self.extendable_scenarios,
            "data_type": self.data_type,
            "task_type": self.task_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExtractedScenario":
        return cls(
            large_scenario=data.get("large_scenario", ""),
            small_scenario=data.get("small_scenario", ""),
            extendable_scenarios=data.get("extendable_scenarios", []),
            data_type=data.get("data_type", ""),
            task_type=data.get("task_type", ""),
        )


@dataclass
class ExtractedTechnique:
    name: str = ""
    category: str = ""
    description: str = ""
    formula: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "formula": self.formula,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExtractedTechnique":
        return cls(
            name=data.get("name", ""),
            category=data.get("category", ""),
            description=data.get("description", ""),
            formula=data.get("formula"),
        )


@dataclass
class ExtractedIdeas:
    innovations: List[ExtractedInnovation] = field(default_factory=list)
    methods: List[ExtractedMethod] = field(default_factory=list)
    scenarios: List[ExtractedScenario] = field(default_factory=list)
    techniques: List[ExtractedTechnique] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "innovations": [i.to_dict() for i in self.innovations],
            "methods": [m.to_dict() for m in self.methods],
            "scenarios": [s.to_dict() for s in self.scenarios],
            "techniques": [t.to_dict() for t in self.techniques],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExtractedIdeas":
        return cls(
            innovations=[ExtractedInnovation.from_dict(d) for d in data.get("innovations", [])],
            methods=[ExtractedMethod.from_dict(d) for d in data.get("methods", [])],
            scenarios=[ExtractedScenario.from_dict(d) for d in data.get("scenarios", [])],
            techniques=[ExtractedTechnique.from_dict(d) for d in data.get("techniques", [])],
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "ExtractedIdeas":
        return cls.from_dict(json.loads(json_str))

    def is_empty(self) -> bool:
        return not any([self.innovations, self.methods, self.scenarios, self.techniques])

    def summary(self) -> str:
        return (
            f"ExtractedIdeas: "
            f"{len(self.innovations)} innovations, "
            f"{len(self.methods)} methods, "
            f"{len(self.scenarios)} scenarios, "
            f"{len(self.techniques)} techniques"
        )


@dataclass
class ExtractionConfig:
    llm_api_key: Optional[str] = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096
    llm_timeout: int = 120
    max_retries: int = 3
    retry_delay: float = 2.0
    max_concurrent_extractions: int = 4

    def to_dict(self) -> Dict[str, Any]:
        return {
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "llm_temperature": self.llm_temperature,
            "llm_max_tokens": self.llm_max_tokens,
            "llm_timeout": self.llm_timeout,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "max_concurrent_extractions": self.max_concurrent_extractions,
        }


@dataclass
class PaperContent:
    full_text: str = ""
    title: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    introduction: str = ""
    method: str = ""
    experiments: str = ""
    conclusion: str = ""
    other_sections: Dict[str, str] = field(default_factory=dict)

    def get_method_context(self) -> str:
        parts = []
        if self.abstract:
            parts.append(f"## Abstract\n{self.abstract}")
        if self.introduction:
            parts.append(f"## Introduction\n{self.introduction}")
        if self.method:
            parts.append(f"## Method\n{self.method}")
        return "\n\n".join(parts)

    def get_innovation_context(self) -> str:
        parts = []
        if self.abstract:
            parts.append(f"## Abstract\n{self.abstract}")
        if self.introduction:
            parts.append(f"## Introduction\n{self.introduction}")
        if self.conclusion:
            parts.append(f"## Conclusion\n{self.conclusion}")
        return "\n\n".join(parts)

    def get_scenario_context(self) -> str:
        parts = []
        if self.abstract:
            parts.append(f"## Abstract\n{self.abstract}")
        if self.experiments:
            parts.append(f"## Experiments\n{self.experiments}")
        if self.conclusion:
            parts.append(f"## Conclusion\n{self.conclusion}")
        return "\n\n".join(parts)

    def get_full_context(self) -> str:
        return self.full_text
