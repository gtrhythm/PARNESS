from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DirectorDecision(str, Enum):
    ACCEPT = "accept"
    RETRY_WITH_FIX = "retry_with_fix"
    CHANGE_APPROACH = "change_approach"
    CHANGE_DATASET = "change_dataset"
    REDUCE_SCOPE = "reduce_scope"
    ABORT = "abort"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Issue:
    severity: Severity
    category: str
    message: str
    suggestion: str = ""


@dataclass
class ReviewVerdict:
    overall_score: float
    result_quality: str
    issues: List[Issue] = field(default_factory=list)
    metric_assessment: Dict[str, str] = field(default_factory=dict)
    recommendation: str = ""
    is_acceptable: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "result_quality": self.result_quality,
            "issues": [
                {"severity": i.severity.value, "category": i.category,
                 "message": i.message, "suggestion": i.suggestion}
                for i in self.issues
            ],
            "metric_assessment": self.metric_assessment,
            "recommendation": self.recommendation,
            "is_acceptable": self.is_acceptable,
        }


@dataclass
class DirectorAction:
    decision: DirectorDecision
    reasoning: str
    refined_spec: Optional[Dict[str, Any]] = None
    feedback_to_opencode: str = ""
    confidence: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "decision": self.decision.value,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "feedback_to_opencode": self.feedback_to_opencode,
        }
        if self.refined_spec:
            d["refined_spec"] = self.refined_spec
        return d


@dataclass
class ExperimentRound:
    round_number: int
    spec_snapshot: Dict[str, Any]
    result_snapshot: Dict[str, Any]
    review: Optional[ReviewVerdict] = None
    director_action: Optional[DirectorAction] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "round_number": self.round_number,
            "spec": self.spec_snapshot,
            "result": self.result_snapshot,
        }
        if self.review:
            d["review"] = self.review.to_dict()
        if self.director_action:
            d["director_action"] = self.director_action.to_dict()
        return d


@dataclass
class IterativeExperimentResult:
    idea_id: str
    rounds: List[ExperimentRound] = field(default_factory=list)
    final_result: Optional[Dict[str, Any]] = None
    final_metrics: Dict[str, float] = field(default_factory=dict)
    total_rounds: int = 0
    accepted: bool = False
    director_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "idea_id": self.idea_id,
            "rounds": [r.to_dict() for r in self.rounds],
            "final_result": self.final_result,
            "final_metrics": self.final_metrics,
            "total_rounds": self.total_rounds,
            "accepted": self.accepted,
            "director_summary": self.director_summary,
        }
