import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class IdeaStatus(str, Enum):
    DRAFT = "draft"
    GENERATED = "generated"
    EVALUATING = "evaluating"
    EVALUATED = "evaluated"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REFINED = "refined"
    ARCHIVED = "archived"


@dataclass
class EvaluationReport:
    evaluator: str = ""
    novelty_score: float = 0.0
    feasibility_score: float = 0.0
    impact_score: float = 0.0
    overall_score: float = 0.0
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    recommendation: str = ""
    timestamp: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluationReport":
        return cls(
            evaluator=data.get("evaluator", ""),
            novelty_score=data.get("novelty_score", 0.0),
            feasibility_score=data.get("feasibility_score", 0.0),
            impact_score=data.get("impact_score", 0.0),
            overall_score=data.get("overall_score", 0.0),
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            recommendation=data.get("recommendation", ""),
            timestamp=data.get("timestamp", ""),
            notes=data.get("notes", ""),
        )


@dataclass
class IdeaRecord:
    idea_id: str = ""
    title: str = ""
    description: str = ""
    category: str = ""
    methodology: str = ""
    expected_results: str = ""
    required_resources: str = ""
    risk_analysis: str = ""
    source_papers: List[str] = field(default_factory=list)
    seed_type: str = ""
    rationale: str = ""
    status: IdeaStatus = IdeaStatus.DRAFT
    evaluations: List[EvaluationReport] = field(default_factory=list)
    best_score: float = 0.0
    created_at: str = ""
    updated_at: str = ""
    tags: List[str] = field(default_factory=list)
    batch_id: str = ""
    paper_count: int = 0
    insight_count: int = 0
    seed_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["evaluations"] = [e.to_dict() for e in self.evaluations]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IdeaRecord":
        status_val = data.get("status", "draft")
        if isinstance(status_val, str):
            status_val = IdeaStatus(status_val)

        evals_data = data.get("evaluations", [])
        evaluations = [EvaluationReport.from_dict(e) if isinstance(e, dict) else e for e in evals_data]

        return cls(
            idea_id=data.get("idea_id", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            category=data.get("category", ""),
            methodology=data.get("methodology", ""),
            expected_results=data.get("expected_results", ""),
            required_resources=data.get("required_resources", ""),
            risk_analysis=data.get("risk_analysis", ""),
            source_papers=data.get("source_papers", []),
            seed_type=data.get("seed_type", ""),
            rationale=data.get("rationale", ""),
            status=status_val,
            evaluations=evaluations,
            best_score=data.get("best_score", 0.0),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            tags=data.get("tags", []),
            batch_id=data.get("batch_id", ""),
            paper_count=data.get("paper_count", 0),
            insight_count=data.get("insight_count", 0),
            seed_count=data.get("seed_count", 0),
        )

    def compute_id(self) -> str:
        import hashlib
        return hashlib.sha256(self.title.lower().strip().encode()).hexdigest()[:16]
