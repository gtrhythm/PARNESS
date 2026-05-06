from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class AnalysisStatus(Enum):
    PENDING = "pending"
    SCANNING = "scanning"
    ANALYZING = "analyzing"
    MAPPING = "mapping"
    DONE = "done"
    FAILED = "failed"


class ConceptCategory(Enum):
    INNOVATION = "innovation"
    METHOD = "method"
    TECHNIQUE = "technique"
    ARCHITECTURE = "architecture"
    LOSS_FUNCTION = "loss_function"
    DATA_PIPELINE = "data_pipeline"
    TRAINING_STRATEGY = "training_strategy"
    EVALUATION = "evaluation"
    OTHER = "other"


class FileRole(Enum):
    ENTRY_POINT = "entry_point"
    MODEL = "model"
    TRAINING = "training"
    DATA_PROCESSING = "data_processing"
    EVALUATION = "evaluation"
    CONFIG = "config"
    UTILITY = "utility"
    TEST = "test"
    DOCUMENTATION = "documentation"
    OTHER = "other"


@dataclass
class CodeLocation:
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0
    symbol_name: str = ""
    code_snippet: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CodeLocation:
        return cls(
            file_path=data.get("file_path", ""),
            start_line=data.get("start_line", 0),
            end_line=data.get("end_line", 0),
            symbol_name=data.get("symbol_name", ""),
            code_snippet=data.get("code_snippet", ""),
        )


@dataclass
class FileSummary:
    file_path: str = ""
    role: str = ""
    description: str = ""
    key_classes: List[str] = field(default_factory=list)
    key_functions: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    line_count: int = 0
    language: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FileSummary:
        return cls(
            file_path=data.get("file_path", ""),
            role=data.get("role", ""),
            description=data.get("description", ""),
            key_classes=data.get("key_classes", []),
            key_functions=data.get("key_functions", []),
            imports=data.get("imports", []),
            line_count=data.get("line_count", 0),
            language=data.get("language", ""),
        )


@dataclass
class RepoStructure:
    repo_id: str = ""
    root_path: str = ""
    directory_tree: str = ""
    languages: Dict[str, int] = field(default_factory=dict)
    file_summaries: List[FileSummary] = field(default_factory=list)
    entry_points: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    total_files: int = 0
    total_lines: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["file_summaries"] = [f.to_dict() for f in self.file_summaries]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RepoStructure:
        return cls(
            repo_id=data.get("repo_id", ""),
            root_path=data.get("root_path", ""),
            directory_tree=data.get("directory_tree", ""),
            languages=data.get("languages", {}),
            file_summaries=[FileSummary.from_dict(f) for f in data.get("file_summaries", [])],
            entry_points=data.get("entry_points", []),
            dependencies=data.get("dependencies", []),
            total_files=data.get("total_files", 0),
            total_lines=data.get("total_lines", 0),
        )


@dataclass
class PaperCodeMapping:
    mapping_id: str = ""
    paper_id: str = ""
    repo_id: str = ""
    concept: str = ""
    concept_category: str = ""
    code_files: List[CodeLocation] = field(default_factory=list)
    code_pattern: str = ""
    key_functions: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    mapping_confidence: float = 0.0
    implementation_detail: str = ""

    def compute_id(self) -> str:
        raw = f"{self.paper_id}:{self.repo_id}:{self.concept}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def embedding_text(self) -> str:
        parts = [self.concept, self.code_pattern, self.implementation_detail]
        return " ".join(p for p in parts if p)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["code_files"] = [c.to_dict() for c in self.code_files]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PaperCodeMapping:
        code_files = [CodeLocation.from_dict(c) for c in data.get("code_files", [])]
        return cls(
            mapping_id=data.get("mapping_id", ""),
            paper_id=data.get("paper_id", ""),
            repo_id=data.get("repo_id", ""),
            concept=data.get("concept", ""),
            concept_category=data.get("concept_category", ""),
            code_files=code_files,
            code_pattern=data.get("code_pattern", ""),
            key_functions=data.get("key_functions", []),
            dependencies=data.get("dependencies", []),
            mapping_confidence=data.get("mapping_confidence", 0.0),
            implementation_detail=data.get("implementation_detail", ""),
        )


@dataclass
class ImplementationPattern:
    pattern_id: str = ""
    name: str = ""
    description: str = ""
    category: str = ""
    code_template: str = ""
    required_dependencies: List[str] = field(default_factory=list)
    applicable_scenarios: List[str] = field(default_factory=list)
    source_repos: List[str] = field(default_factory=list)

    def compute_id(self) -> str:
        raw = f"{self.category}:{self.name}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ImplementationPattern:
        return cls(
            pattern_id=data.get("pattern_id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            category=data.get("category", ""),
            code_template=data.get("code_template", ""),
            required_dependencies=data.get("required_dependencies", []),
            applicable_scenarios=data.get("applicable_scenarios", []),
            source_repos=data.get("source_repos", []),
        )


@dataclass
class PaperCodeAnalysis:
    analysis_id: str = ""
    paper_id: str = ""
    repo_id: str = ""
    paper_title: str = ""
    paper_innovations: List[str] = field(default_factory=list)
    repo_structure: Optional[RepoStructure] = None
    mappings: List[PaperCodeMapping] = field(default_factory=list)
    implementation_summary: str = ""
    reusable_patterns: List[ImplementationPattern] = field(default_factory=list)
    tech_stack: List[str] = field(default_factory=list)
    status: str = AnalysisStatus.PENDING.value
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def compute_analysis_id(self) -> str:
        raw = f"{self.paper_id}:{self.repo_id}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "analysis_id": self.analysis_id,
            "paper_id": self.paper_id,
            "repo_id": self.repo_id,
            "paper_title": self.paper_title,
            "paper_innovations": self.paper_innovations,
            "repo_structure": self.repo_structure.to_dict() if self.repo_structure else None,
            "mappings": [m.to_dict() for m in self.mappings],
            "implementation_summary": self.implementation_summary,
            "reusable_patterns": [p.to_dict() for p in self.reusable_patterns],
            "tech_stack": self.tech_stack,
            "status": self.status,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PaperCodeAnalysis:
        repo_struct = None
        if data.get("repo_structure"):
            repo_struct = RepoStructure.from_dict(data["repo_structure"])
        return cls(
            analysis_id=data.get("analysis_id", ""),
            paper_id=data.get("paper_id", ""),
            repo_id=data.get("repo_id", ""),
            paper_title=data.get("paper_title", ""),
            paper_innovations=data.get("paper_innovations", []),
            repo_structure=repo_struct,
            mappings=[PaperCodeMapping.from_dict(m) for m in data.get("mappings", [])],
            implementation_summary=data.get("implementation_summary", ""),
            reusable_patterns=[ImplementationPattern.from_dict(p) for p in data.get("reusable_patterns", [])],
            tech_stack=data.get("tech_stack", []),
            status=data.get("status", AnalysisStatus.PENDING.value),
            error_message=data.get("error_message", ""),
            metadata=data.get("metadata", {}),
        )

    def save_json(self, path: str) -> None:
        from pathlib import Path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load_json(cls, path: str) -> PaperCodeAnalysis:
        from pathlib import Path
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)
