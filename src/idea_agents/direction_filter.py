import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List

from .llm_utils import call_llm, parse_json_response
from .models import ResearchDirection

logger = logging.getLogger(__name__)

_SCORING_PROMPT = """You are a research relevance evaluator. Score each paper's relevance to the given research direction.

## Research Direction:
{name}
Description: {description}
Keywords: {keywords}
Sub-topics: {sub_topics}

## Papers:
{papers_text}

Return JSON:
{{
  "scores": [
    {{"index": 0, "relevance": 0.85, "reason": "brief reason"}},
    {{"index": 1, "relevance": 0.3, "reason": "brief reason"}}
  ]
}}

Rules:
- Score 0.8-1.0: directly addresses the direction
- Score 0.5-0.8: tangentially related, useful background
- Score 0.0-0.5: not relevant to this direction
- Be strict: only papers scoring >= 0.5 should be kept
"""

_BATCH_SIZE = 20
_KEYWORD_THRESHOLD = 0.15


@dataclass
class FilterResult:
    filtered_papers: List[Dict[str, Any]] = field(default_factory=list)
    relevance_scores: List[float] = field(default_factory=list)
    filter_stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DirectionFilter:
    def __init__(self, llm_client):
        self.llm = llm_client

    def validate_inputs(self, papers: List[Dict]) -> List[str]:
        errors = []
        if not isinstance(papers, list) or len(papers) == 0:
            errors.append("papers must be a non-empty list")
        return errors

    def _keyword_prefilter(self, papers: List[Dict], direction: ResearchDirection) -> List[Dict]:
        all_keywords = set()
        for kw in direction.keywords:
            all_keywords.add(kw.lower())
        for st in direction.sub_topics:
            all_keywords.add(st.lower())
        if direction.name:
            for word in direction.name.lower().split():
                if len(word) > 2:
                    all_keywords.add(word)

        if not all_keywords:
            return papers

        total_keywords = len(all_keywords)
        kept = []
        for paper in papers:
            abstract = paper.get("abstract", "")
            if not abstract:
                continue
            text = (paper.get("title", "") + " " + abstract).lower()
            matched = sum(1 for kw in all_keywords if kw in text)
            ratio = matched / total_keywords
            if ratio >= _KEYWORD_THRESHOLD:
                kept.append(paper)
        return kept

    async def _score_batch(self, batch: List[Dict], direction: ResearchDirection) -> List[Dict]:
        papers_text = ""
        for i, p in enumerate(batch):
            title = p.get("title", "Untitled")
            abstract = p.get("abstract", "")
            papers_text += f"\n[{i}] {title}\n  Abstract: {abstract}\n"

        prompt = _SCORING_PROMPT.format(
            name=direction.name,
            description=direction.description,
            keywords=", ".join(direction.keywords),
            sub_topics=", ".join(direction.sub_topics),
            papers_text=papers_text,
        )

        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        scores = []
        scored_indices = set()
        raw_scores = data.get("scores", [])
        for item in raw_scores:
            idx = item.get("index", -1)
            if 0 <= idx < len(batch):
                scores.append({
                    "paper": batch[idx],
                    "relevance": float(item.get("relevance", 0.0)),
                })
                scored_indices.add(idx)

        for i in range(len(batch)):
            if i not in scored_indices:
                scores.append({
                    "paper": batch[i],
                    "relevance": 0.0,
                })

        return scores

    async def filter(
        self,
        papers: List[Dict],
        direction: ResearchDirection,
        max_papers: int = 50,
        relevance_threshold: float = 0.5,
    ) -> FilterResult:
        errors = self.validate_inputs(papers)
        if errors:
            return FilterResult(filter_stats={
                "input_count": len(papers) if isinstance(papers, list) else 0,
                "keyword_filtered": 0,
                "llm_filtered": 0,
                "final_count": 0,
                "avg_relevance": 0.0,
            })

        input_count = len(papers)

        keyword_filtered = self._keyword_prefilter(papers, direction)

        all_scored = []
        for i in range(0, len(keyword_filtered), _BATCH_SIZE):
            batch = keyword_filtered[i:i + _BATCH_SIZE]
            batch_scores = await self._score_batch(batch, direction)
            all_scored.extend(batch_scores)

        above_threshold = [s for s in all_scored if s["relevance"] >= relevance_threshold]
        above_threshold.sort(key=lambda x: x["relevance"], reverse=True)
        above_threshold = above_threshold[:max_papers]

        filtered_papers = [s["paper"] for s in above_threshold]
        relevance_scores = [s["relevance"] for s in above_threshold]

        avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0

        stats = {
            "input_count": input_count,
            "keyword_filtered": len(keyword_filtered),
            "llm_filtered": len(above_threshold),
            "final_count": len(filtered_papers),
            "avg_relevance": avg_relevance,
        }

        logger.info(
            "DirectionFilter: %d -> %d (keyword) -> %d (LLM, threshold=%.2f, avg=%.2f)",
            input_count, len(keyword_filtered), len(filtered_papers),
            relevance_threshold, avg_relevance,
        )

        return FilterResult(
            filtered_papers=filtered_papers,
            relevance_scores=relevance_scores,
            filter_stats=stats,
        )
