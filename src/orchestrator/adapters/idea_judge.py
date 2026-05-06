import logging
from typing import Any, Dict, List, Optional

from .base import BaseModule

logger = logging.getLogger(__name__)


class IdeaJudgeModule(BaseModule):
    """Score-based gate: accept idea if score >= threshold, otherwise reject.

    Params:
        threshold: float — minimum score to accept (default: 7.0)
        score_key: str — dot-path to read score from inputs (default: "overall_score")

    Input:
        idea: Dict or List[Dict] — the idea(s) to judge; if list, first item is used
        overall_score: float — the idea's score (or nested under score_key)

    Output:
        _route: "accept" | "reject"
        idea: Dict — the original idea (only meaningful on accept route)
        overall_score: float
        judge_decision: str — "accept" or "reject"
    """

    INPUT_SPEC = {
        "idea": {"type": "dict", "required": False, "default": None},
        "overall_score": {"type": "float", "required": False, "default": 0.0},
    }
    OUTPUT_SPEC = {
        "_route": {"type": "str"},
        "idea": {"type": "dict"},
        "overall_score": {"type": "float"},
        "judge_decision": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        threshold = self.config.get("threshold", 7.0)
        score_key = self.config.get("score_key", "overall_score")

        idea = inputs.get("idea", inputs)
        if isinstance(idea, list):
            idea = idea[0] if idea else {}

        score = self._extract_score(inputs, score_key)

        if score is None and isinstance(idea, dict):
            score = idea.get("overall_score", 0.0)
            if score is None:
                score = 0.0

        if score >= threshold:
            route = "accept"
            logger.info(
                "[IdeaJudge] ACCEPT idea '%s' (score=%.2f >= threshold=%.2f)",
                idea.get("title", "?")[:50] if isinstance(idea, dict) else "?",
                score, threshold,
            )
        else:
            route = "reject"
            logger.info(
                "[IdeaJudge] REJECT idea '%s' (score=%.2f < threshold=%.2f)",
                idea.get("title", "?")[:50] if isinstance(idea, dict) else "?",
                score, threshold,
            )

        return {
            "_route": route,
            "idea": idea if isinstance(idea, dict) else {},
            "overall_score": score,
            "judge_decision": route,
        }

    @staticmethod
    def _extract_score(inputs: Dict[str, Any], key: str) -> Optional[float]:
        parts = key.split(".")
        cur: Any = inputs
        for p in parts:
            if isinstance(cur, dict):
                cur = cur.get(p)
            else:
                return None
            if cur is None:
                return None
        try:
            return float(cur)
        except (TypeError, ValueError):
            return None
