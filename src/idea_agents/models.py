import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class ResearchDirection:
    name: str = ""
    description: str = ""
    keywords: List[str] = field(default_factory=list)
    sub_topics: List[str] = field(default_factory=list)
    depth: str = "explore"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchDirection":
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            keywords=data.get("keywords", []),
            sub_topics=data.get("sub_topics", []),
            depth=data.get("depth", "explore"),
        )

    def prompt_block(self) -> str:
        lines = [f"## Research Direction: {self.name}"]
        if self.description:
            lines.append(f"Description: {self.description}")
        if self.keywords:
            lines.append(f"Keywords: {', '.join(self.keywords)}")
        if self.sub_topics:
            lines.append(f"Sub-topics: {', '.join(self.sub_topics)}")
        lines.append(f"Depth: {self.depth}")
        return "\n".join(lines)


@dataclass
class LiteratureSurvey:
    direction: str = ""
    summary: str = ""
    key_papers: List[str] = field(default_factory=list)
    research_threads: List[str] = field(default_factory=list)
    open_problems: List[str] = field(default_factory=list)
    trend_analysis: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LiteratureSurvey":
        return cls(
            direction=data.get("direction", ""),
            summary=data.get("summary", ""),
            key_papers=data.get("key_papers", []),
            research_threads=data.get("research_threads", []),
            open_problems=data.get("open_problems", []),
            trend_analysis=data.get("trend_analysis", ""),
        )


@dataclass
class ExplorationConfig:
    max_papers_per_idea: int = 10
    search_sources: List[str] = field(default_factory=lambda: ["semantic_scholar"])
    refine_with_literature: bool = True
    concurrency_per_idea: int = 2

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IdeaExplorationResult:
    idea_id: str = ""
    idea_title: str = ""
    search_queries: List[str] = field(default_factory=list)
    found_papers: List[Dict[str, Any]] = field(default_factory=list)
    found_insights: List[str] = field(default_factory=list)
    related_work: str = ""
    novelty_validation: str = ""
    refined_idea: Optional[Dict[str, Any]] = None
    references_needed: List[str] = field(default_factory=list)
    innovation_gaps: List[str] = field(default_factory=list)
    direction_alignment: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IdeaExplorationResult":
        return cls(
            idea_id=data.get("idea_id", ""),
            idea_title=data.get("idea_title", ""),
            search_queries=data.get("search_queries", []),
            found_papers=data.get("found_papers", []),
            found_insights=data.get("found_insights", []),
            related_work=data.get("related_work", ""),
            novelty_validation=data.get("novelty_validation", ""),
            refined_idea=data.get("refined_idea"),
            references_needed=data.get("references_needed", []),
            innovation_gaps=data.get("innovation_gaps", []),
            direction_alignment=data.get("direction_alignment", 0.0),
        )


@dataclass
class CompressedInsight:
    paper_id: str = ""
    title: str = ""
    year: int = 0
    core_insight: str = ""
    problem_solved: str = ""
    key_trick: str = ""
    limitations: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    reusable_components: List[str] = field(default_factory=list)
    assumed_but_not_proven: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompressedInsight":
        return cls(
            paper_id=data.get("paper_id", ""),
            title=data.get("title", ""),
            year=data.get("year", 0),
            core_insight=data.get("core_insight", ""),
            problem_solved=data.get("problem_solved", ""),
            key_trick=data.get("key_trick", ""),
            limitations=data.get("limitations", []),
            open_questions=data.get("open_questions", []),
            reusable_components=data.get("reusable_components", []),
            assumed_but_not_proven=data.get("assumed_but_not_proven", []),
        )


@dataclass
class IdeaSeed:
    seed: str = ""
    source_papers: List[str] = field(default_factory=list)
    rationale: str = ""
    seed_type: str = ""
    related_insights: List[str] = field(default_factory=list)
    novelty_signal: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IdeaSeed":
        return cls(
            seed=data.get("seed", ""),
            source_papers=data.get("source_papers", []),
            rationale=data.get("rationale", ""),
            seed_type=data.get("seed_type", ""),
            related_insights=data.get("related_insights", []),
            novelty_signal=data.get("novelty_signal", ""),
        )


@dataclass
class SeedCluster:
    theme: str = ""
    insight_indices: List[int] = field(default_factory=list)
    common_limitations: List[str] = field(default_factory=list)
    gaps: List[IdeaSeed] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "theme": self.theme,
            "insight_indices": self.insight_indices,
            "common_limitations": self.common_limitations,
            "gaps": [g.to_dict() for g in self.gaps],
        }


@dataclass
class CrossDomainPair:
    insight_a_idx: int = 0
    insight_b_idx: int = 0
    surface_similarity: float = 0.0
    structural_analogy: str = ""
    transfer_direction: str = ""
    idea_seed: Optional[IdeaSeed] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "insight_a_idx": self.insight_a_idx,
            "insight_b_idx": self.insight_b_idx,
            "surface_similarity": self.surface_similarity,
            "structural_analogy": self.structural_analogy,
            "transfer_direction": self.transfer_direction,
        }
        if self.idea_seed:
            d["idea_seed"] = self.idea_seed.to_dict()
        return d


@dataclass
class FullIdea:
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
    novelty_score: float = 0.0
    feasibility_score: float = 0.0
    impact_score: float = 0.0
    overall_score: float = 0.0
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    direction_alignment_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FullIdea":
        return cls(
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
            novelty_score=data.get("novelty_score", 0.0),
            feasibility_score=data.get("feasibility_score", 0.0),
            impact_score=data.get("impact_score", 0.0),
            overall_score=data.get("overall_score", 0.0),
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            direction_alignment_score=data.get("direction_alignment_score", 0.0),
        )


# AgentKnowledgeBase moved after all new type definitions (below)


@dataclass
class IdeaReference:
    """Tracks a reference from one idea to another idea or paper."""
    source_idea_id: str = ""
    target_type: str = ""
    target_id: str = ""
    reference_kind: str = ""
    context: str = ""
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IdeaReference":
        return cls(
            source_idea_id=data.get("source_idea_id", ""),
            target_type=data.get("target_type", ""),
            target_id=data.get("target_id", ""),
            reference_kind=data.get("reference_kind", ""),
            context=data.get("context", ""),
            confidence=data.get("confidence", 1.0),
        )


@dataclass
class RichIdea(FullIdea):
    """FullIdea with reference tracking and provenance."""
    idea_id: str = ""
    parent_seed_ids: List[str] = field(default_factory=list)
    parent_insight_ids: List[str] = field(default_factory=list)
    references: List[IdeaReference] = field(default_factory=list)
    derived_idea_ids: List[str] = field(default_factory=list)
    pdf_content_available: bool = False
    pdf_extraction_status: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["references"] = [r.to_dict() for r in self.references]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RichIdea":
        base = FullIdea.from_dict(data)
        refs_data = data.get("references", [])
        references = [IdeaReference.from_dict(r) if isinstance(r, dict) else r for r in refs_data]
        return cls(
            title=base.title,
            description=base.description,
            category=base.category,
            methodology=base.methodology,
            expected_results=base.expected_results,
            required_resources=base.required_resources,
            risk_analysis=base.risk_analysis,
            source_papers=base.source_papers,
            seed_type=base.seed_type,
            rationale=base.rationale,
            novelty_score=data.get("novelty_score", 0.0),
            feasibility_score=data.get("feasibility_score", 0.0),
            impact_score=data.get("impact_score", 0.0),
            overall_score=data.get("overall_score", 0.0),
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            idea_id=data.get("idea_id", ""),
            parent_seed_ids=data.get("parent_seed_ids", []),
            parent_insight_ids=data.get("parent_insight_ids", []),
            references=references,
            derived_idea_ids=data.get("derived_idea_ids", []),
            pdf_content_available=data.get("pdf_content_available", False),
            pdf_extraction_status=data.get("pdf_extraction_status", ""),
        )

    def compute_id(self) -> str:
        """Generate deterministic ID from title."""
        import hashlib
        return hashlib.sha256(self.title.lower().strip().encode()).hexdigest()[:16]


class ConclusionForm(str):
    SUMMARY = "summary"
    KEY_POINTS = "key_points"
    QUESTIONS = "questions"
    GAPS = "gaps"
    HYPOTHESES = "hypotheses"
    IDEAS = "ideas"
    CONNECTIONS = "connections"
    CRITIQUES = "critiques"
    EVIDENCE = "evidence"
    METRICS = "metrics"


@dataclass
class Conclusion:
    form: str = ""
    content: str = ""
    items: List[str] = field(default_factory=list)
    source_papers: List[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Conclusion":
        return cls(
            form=data.get("form", ""),
            content=data.get("content", ""),
            items=data.get("items", []),
            source_papers=data.get("source_papers", []),
            confidence=data.get("confidence", 0.0),
        )


@dataclass
class GapItem:
    gap_description: str = ""
    domain: str = ""
    evidence_papers: List[str] = field(default_factory=list)
    opportunity_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GapItem":
        return cls(
            gap_description=data.get("gap_description", ""),
            domain=data.get("domain", ""),
            evidence_papers=data.get("evidence_papers", []),
            opportunity_score=data.get("opportunity_score", 0.0),
        )


@dataclass
class TransferIdea:
    source_domain: str = ""
    target_domain: str = ""
    method_name: str = ""
    method_description: str = ""
    transfer_rationale: str = ""
    adaptation_needed: str = ""
    feasibility_score: float = 0.0
    source_papers: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TransferIdea":
        return cls(
            source_domain=data.get("source_domain", ""),
            target_domain=data.get("target_domain", ""),
            method_name=data.get("method_name", ""),
            method_description=data.get("method_description", ""),
            transfer_rationale=data.get("transfer_rationale", ""),
            adaptation_needed=data.get("adaptation_needed", ""),
            feasibility_score=data.get("feasibility_score", 0.0),
            source_papers=data.get("source_papers", []),
        )


@dataclass
class CritiqueItem:
    paper_id: str = ""
    claim: str = ""
    flaw: str = ""
    severity: str = ""
    suggested_improvement: str = ""
    evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CritiqueItem":
        return cls(
            paper_id=data.get("paper_id", ""),
            claim=data.get("claim", ""),
            flaw=data.get("flaw", ""),
            severity=data.get("severity", ""),
            suggested_improvement=data.get("suggested_improvement", ""),
            evidence=data.get("evidence", ""),
        )


@dataclass
class TheoryImprovement:
    paper_id: str = ""
    original_assumption: str = ""
    theoretical_issue: str = ""
    proposed_correction: str = ""
    mathematical_sketch: str = ""
    impact_assessment: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TheoryImprovement":
        return cls(
            paper_id=data.get("paper_id", ""),
            original_assumption=data.get("original_assumption", ""),
            theoretical_issue=data.get("theoretical_issue", ""),
            proposed_correction=data.get("proposed_correction", ""),
            mathematical_sketch=data.get("mathematical_sketch", ""),
            impact_assessment=data.get("impact_assessment", ""),
        )


@dataclass
class ReplicationProblem:
    paper_id: str = ""
    paper_title: str = ""
    claimed_result: str = ""
    reproduction_issue: str = ""
    missing_details: List[str] = field(default_factory=list)
    suggested_experiment: str = ""
    potential_improvement: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReplicationProblem":
        return cls(
            paper_id=data.get("paper_id", ""),
            paper_title=data.get("paper_title", ""),
            claimed_result=data.get("claimed_result", ""),
            reproduction_issue=data.get("reproduction_issue", ""),
            missing_details=data.get("missing_details", []),
            suggested_experiment=data.get("suggested_experiment", ""),
            potential_improvement=data.get("potential_improvement", ""),
        )


@dataclass
class TrendItem:
    trend_name: str = ""
    description: str = ""
    supporting_papers: List[str] = field(default_factory=list)
    growth_rate: str = ""
    related_gaps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrendItem":
        return cls(
            trend_name=data.get("trend_name", ""),
            description=data.get("description", ""),
            supporting_papers=data.get("supporting_papers", []),
            growth_rate=data.get("growth_rate", ""),
            related_gaps=data.get("related_gaps", []),
        )


@dataclass
class FollowUpIdea:
    original_paper_id: str = ""
    original_paper_title: str = ""
    future_work_claim: str = ""
    extension_idea: str = ""
    feasibility: str = ""
    novelty_assessment: str = ""
    required_resources: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FollowUpIdea":
        return cls(
            original_paper_id=data.get("original_paper_id", ""),
            original_paper_title=data.get("original_paper_title", ""),
            future_work_claim=data.get("future_work_claim", ""),
            extension_idea=data.get("extension_idea", ""),
            feasibility=data.get("feasibility", ""),
            novelty_assessment=data.get("novelty_assessment", ""),
            required_resources=data.get("required_resources", ""),
        )


@dataclass
class FailureCase:
    paper_id: str = ""
    paper_title: str = ""
    method_description: str = ""
    failure_scenario: str = ""
    why_it_fails: str = ""
    counter_example: str = ""
    suggested_fix: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FailureCase":
        return cls(
            paper_id=data.get("paper_id", ""),
            paper_title=data.get("paper_title", ""),
            method_description=data.get("method_description", ""),
            failure_scenario=data.get("failure_scenario", ""),
            why_it_fails=data.get("why_it_fails", ""),
            counter_example=data.get("counter_example", ""),
            suggested_fix=data.get("suggested_fix", ""),
        )


@dataclass
class LimitationExtension:
    paper_id: str = ""
    paper_title: str = ""
    stated_limitation: str = ""
    extension_direction: str = ""
    proposed_approach: str = ""
    expected_contribution: str = ""
    difficulty: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LimitationExtension":
        return cls(
            paper_id=data.get("paper_id", ""),
            paper_title=data.get("paper_title", ""),
            stated_limitation=data.get("stated_limitation", ""),
            extension_direction=data.get("extension_direction", ""),
            proposed_approach=data.get("proposed_approach", ""),
            expected_contribution=data.get("expected_contribution", ""),
            difficulty=data.get("difficulty", ""),
        )


@dataclass
class Hypothesis:
    hypothesis_id: str = ""
    statement: str = ""
    rationale: str = ""
    testability: str = ""
    source_papers: List[str] = field(default_factory=list)
    predicted_outcome: str = ""
    required_experiment: str = ""
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Hypothesis":
        return cls(
            hypothesis_id=data.get("hypothesis_id", ""),
            statement=data.get("statement", ""),
            rationale=data.get("rationale", ""),
            testability=data.get("testability", ""),
            source_papers=data.get("source_papers", []),
            predicted_outcome=data.get("predicted_outcome", ""),
            required_experiment=data.get("required_experiment", ""),
            confidence=data.get("confidence", 0.0),
        )


@dataclass
class EvidenceItem:
    hypothesis_id: str = ""
    paper_id: str = ""
    paper_title: str = ""
    stance: str = ""
    evidence_description: str = ""
    strength: str = ""
    relevance: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceItem":
        return cls(
            hypothesis_id=data.get("hypothesis_id", ""),
            paper_id=data.get("paper_id", ""),
            paper_title=data.get("paper_title", ""),
            stance=data.get("stance", ""),
            evidence_description=data.get("evidence_description", ""),
            strength=data.get("strength", ""),
            relevance=data.get("relevance", 0.0),
        )


@dataclass
class ReadingStrategy:
    paper_selection_mode: str = "mixed"
    independence_mode: str = "comparative"
    integration_mode: str = "realtime"
    accumulation_mode: str = "cumulative"
    relevance_threshold: float = 0.7
    diversity_min_subdomains: int = 3
    paper_limit: int = 20

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReadingStrategy":
        return cls(
            paper_selection_mode=data.get("paper_selection_mode", "mixed"),
            independence_mode=data.get("independence_mode", "comparative"),
            integration_mode=data.get("integration_mode", "realtime"),
            accumulation_mode=data.get("accumulation_mode", "cumulative"),
            relevance_threshold=data.get("relevance_threshold", 0.7),
            diversity_min_subdomains=data.get("diversity_min_subdomains", 3),
            paper_limit=data.get("paper_limit", 20),
        )


@dataclass
class AgentKnowledgeBase:
    insights: List[CompressedInsight] = field(default_factory=list)
    analyst_seeds: List[IdeaSeed] = field(default_factory=list)
    connector_seeds: List[IdeaSeed] = field(default_factory=list)
    contrarian_seeds: List[IdeaSeed] = field(default_factory=list)
    clusters: List[SeedCluster] = field(default_factory=list)
    cross_domain_pairs: List[CrossDomainPair] = field(default_factory=list)
    replication_problems: List[ReplicationProblem] = field(default_factory=list)
    transfer_ideas: List[TransferIdea] = field(default_factory=list)
    critiques: List[CritiqueItem] = field(default_factory=list)
    theory_improvements: List[TheoryImprovement] = field(default_factory=list)
    trends: List[TrendItem] = field(default_factory=list)
    meta_gaps: List[GapItem] = field(default_factory=list)
    follow_up_ideas: List[FollowUpIdea] = field(default_factory=list)
    failure_cases: List[FailureCase] = field(default_factory=list)
    limitation_extensions: List[LimitationExtension] = field(default_factory=list)
    hypotheses: List[Hypothesis] = field(default_factory=list)
    evidence_items: List[EvidenceItem] = field(default_factory=list)

    def all_seeds(self) -> List[IdeaSeed]:
        return self.analyst_seeds + self.connector_seeds + self.contrarian_seeds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "insights": [i.to_dict() for i in self.insights],
            "analyst_seeds": [s.to_dict() for s in self.analyst_seeds],
            "connector_seeds": [s.to_dict() for s in self.connector_seeds],
            "contrarian_seeds": [s.to_dict() for s in self.contrarian_seeds],
            "clusters": [c.to_dict() for c in self.clusters],
            "cross_domain_pairs": [p.to_dict() for p in self.cross_domain_pairs],
            "replication_problems": [r.to_dict() for r in self.replication_problems],
            "transfer_ideas": [t.to_dict() for t in self.transfer_ideas],
            "critiques": [c.to_dict() for c in self.critiques],
            "theory_improvements": [t.to_dict() for t in self.theory_improvements],
            "trends": [t.to_dict() for t in self.trends],
            "meta_gaps": [g.to_dict() for g in self.meta_gaps],
            "follow_up_ideas": [f.to_dict() for f in self.follow_up_ideas],
            "failure_cases": [f.to_dict() for f in self.failure_cases],
            "limitation_extensions": [e.to_dict() for e in self.limitation_extensions],
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "evidence_items": [e.to_dict() for e in self.evidence_items],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentKnowledgeBase":
        return cls(
            insights=[CompressedInsight.from_dict(d) for d in data.get("insights", [])],
            analyst_seeds=[IdeaSeed.from_dict(d) for d in data.get("analyst_seeds", [])],
            connector_seeds=[IdeaSeed.from_dict(d) for d in data.get("connector_seeds", [])],
            contrarian_seeds=[IdeaSeed.from_dict(d) for d in data.get("contrarian_seeds", [])],
            clusters=[SeedCluster(theme=c.get("theme", ""),
                                  insight_indices=c.get("insight_indices", []),
                                  common_limitations=c.get("common_limitations", []),
                                  gaps=[IdeaSeed.from_dict(g) for g in c.get("gaps", [])])
                      for c in data.get("clusters", [])],
            cross_domain_pairs=[CrossDomainPair(
                insight_a_idx=p.get("insight_a_idx", 0),
                insight_b_idx=p.get("insight_b_idx", 0),
                surface_similarity=p.get("surface_similarity", 0.0),
                structural_analogy=p.get("structural_analogy", ""),
                transfer_direction=p.get("transfer_direction", ""),
                idea_seed=IdeaSeed.from_dict(p["idea_seed"]) if p.get("idea_seed") else None,
            ) for p in data.get("cross_domain_pairs", [])],
            replication_problems=[ReplicationProblem.from_dict(d) for d in data.get("replication_problems", [])],
            transfer_ideas=[TransferIdea.from_dict(d) for d in data.get("transfer_ideas", [])],
            critiques=[CritiqueItem.from_dict(d) for d in data.get("critiques", [])],
            theory_improvements=[TheoryImprovement.from_dict(d) for d in data.get("theory_improvements", [])],
            trends=[TrendItem.from_dict(d) for d in data.get("trends", [])],
            meta_gaps=[GapItem.from_dict(d) for d in data.get("meta_gaps", [])],
            follow_up_ideas=[FollowUpIdea.from_dict(d) for d in data.get("follow_up_ideas", [])],
            failure_cases=[FailureCase.from_dict(d) for d in data.get("failure_cases", [])],
            limitation_extensions=[LimitationExtension.from_dict(d) for d in data.get("limitation_extensions", [])],
            hypotheses=[Hypothesis.from_dict(d) for d in data.get("hypotheses", [])],
            evidence_items=[EvidenceItem.from_dict(d) for d in data.get("evidence_items", [])],
        )
