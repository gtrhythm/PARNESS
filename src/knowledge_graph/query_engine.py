"""LLM-driven natural language query engine for the knowledge graph."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_STRATEGY_PROMPT = """\
Given the following question, generate a search strategy for querying a knowledge graph \
of research papers and scientific knowledge.

Return ONLY a JSON object with:
- "keywords": list of 3-7 search keywords or short phrases
- "traversal_direction": one of "outgoing", "incoming", "both"
- "focus_types": list of node types to prioritize (e.g. "method", "result", "definition", "claim")

Question: {question}
Additional context: {context}"""

_ANSWER_PROMPT = """\
Answer the following research question using the provided knowledge graph results.
Synthesize information from multiple sources. Reference source papers by their source_id.

Question: {question}
Context: {context}

Knowledge graph results:
{results_text}

Provenance information:
{provenance_text}

Subgraph traversal reached {hop_reached} hops and discovered {node_count} nodes.

Provide your answer as a JSON object:
{{
    "answer": "your comprehensive answer",
    "confidence": <float 0.0-1.0>,
    "reasoning": "brief explanation of your reasoning and source synthesis"
}}"""

_ENRICH_STRATEGY_PROMPT = """\
Analyze this research paper abstract and generate a search strategy to find related \
full-text papers that can provide methods, experimental details, and code.

Return ONLY a JSON object with:
- "keywords": list of 3-7 search keywords
- "focus_types": list of types to look for (e.g. "method", "result", "observation")
- "max_hops": recommended traversal depth (integer 1-5)

Abstract:
{abstract}"""

_ENRICH_SYNTHESIS_PROMPT = """\
Given a research paper abstract and knowledge graph results from related papers, \
synthesize an enriched context that fills in the gaps of the abstract.

Original abstract:
{abstract}

Related knowledge chunks:
{chunks_text}

Source papers:
{sources_text}

Provide a comprehensive enriched context that integrates the methods, experimental details, \
and code references from related papers with the original abstract.

Return a JSON object:
{{
    "enriched_context": "comprehensive synthesis",
    "key_methods": ["method1", "method2"],
    "key_experiments": ["experiment1", "experiment2"],
    "key_code_refs": ["ref1", "ref2"],
    "confidence": <float 0.0-1.0>
}}"""

_IDEA_SEARCH_PROMPT = """\
Analyze this seed research idea and generate a search strategy for discovering \
connected knowledge across domains using a knowledge graph.

Strategy: {strategy}

Return ONLY a JSON object with:
- "keywords": list of 3-7 search keywords
- "traversal_direction": "both"
- "focus_types": list of types to look for
- "cross_domain_hints": list of related fields or domains to explore

Seed idea: {seed_idea}"""

_IDEA_SYNTHESIS_PROMPT = """\
Based on the following knowledge graph paths discovered from a seed research idea, \
synthesize new, creative research ideas that connect different domains and knowledge areas.

Seed idea: {seed_idea}
Strategy: {strategy}

Discovered knowledge paths:
{paths_text}

Generate novel research ideas that combine insights from different paths. \
Each idea should be specific, actionable, and clearly state what makes it novel.

Return a JSON object:
{{
    "ideas": [
        {{
            "title": "short descriptive title",
            "description": "detailed description",
            "novelty": "what makes this idea novel",
            "feasibility": "high/medium/low",
            "source_connections": ["references to specific knowledge paths used"]
        }}
    ]
}}"""


def _parse_json_response(response: str) -> dict:
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", response, re.DOTALL)
    if fence_match:
        body = fence_match.group(1).strip()
    else:
        brace_match = re.search(r"\{.*\}", response, re.DOTALL)
        body = brace_match.group(0) if brace_match else response.strip()
    return json.loads(body)


def _format_results_text(results: List[dict], max_items: int = 30) -> str:
    parts: List[str] = []
    for i, r in enumerate(results[:max_items]):
        parts.append(
            f"[{i + 1}] (score={r.get('score', 0):.3f}, "
            f"type={r.get('source_type', 'unknown')}) "
            f"{r.get('chunk_text', '')}"
        )
    return "\n".join(parts)


def _format_provenances(provenances: List[dict]) -> str:
    if not provenances:
        return "(no provenance data)"
    parts: List[str] = []
    for p in provenances:
        parts.append(
            f"- node {p.get('node_id', '?')}: "
            f"{p.get('title', 'untitled')} "
            f"({p.get('source_type', '')} {p.get('source_id', '')})"
        )
    return "\n".join(parts)


def _format_paths(subgraph: dict, results: List[dict]) -> str:
    parts: List[str] = []
    for edge in subgraph.get("edges", []):
        parts.append(
            f"{edge.get('source', '?')} --[{edge.get('relation_type', 'RELATED')} "
            f"(conf={edge.get('confidence', 0):.2f})]--> {edge.get('target', '?')}"
        )
    for node in subgraph.get("nodes", []):
        text = node.get("chunk_text", "")
        if text:
            parts.append(
                f"Node {node.get('node_id', '?')}: {text[:200]}"
            )
    return "\n".join(parts)


class KGQueryEngine:
    def __init__(self, retriever, config: Optional[Dict] = None):
        self.retriever = retriever
        self._config = config or {}
        self._embedder = self._config.get("embedder")

    async def answer_question(
        self,
        llm_client,
        question: str,
        context: str = "",
        max_hops: int = 3,
        top_k: int = 20,
    ) -> dict:
        strategy_prompt = _STRATEGY_PROMPT.format(question=question, context=context or "(none)")
        strategy_raw = await llm_client.chat(strategy_prompt)
        try:
            strategy = _parse_json_response(strategy_raw)
        except Exception:
            logger.warning("Failed to parse search strategy, using defaults")
            strategy = {
                "keywords": question.split()[:5],
                "traversal_direction": "both",
                "focus_types": [],
            }

        keywords = strategy.get("keywords", [])
        query_text = " ".join(keywords) if keywords else question

        search_result = await self.retriever.search(
            query_text,
            top_k=top_k,
            max_hops=max_hops,
            embedder=self._embedder,
        )

        results = search_result.get("results", [])
        subgraph = search_result.get("subgraph", {})
        provenances = subgraph.get("provenances", [])

        results_text = _format_results_text(results)
        provenance_text = _format_provenances(provenances)

        answer_prompt = _ANSWER_PROMPT.format(
            question=question,
            context=context or "(none)",
            results_text=results_text,
            provenance_text=provenance_text,
            hop_reached=subgraph.get("hop_reached", 0),
            node_count=len(subgraph.get("nodes", [])),
        )
        answer_raw = await llm_client.chat(answer_prompt)

        try:
            answer_data = _parse_json_response(answer_raw)
        except Exception:
            logger.warning("Failed to parse answer JSON, using raw response")
            answer_data = {
                "answer": answer_raw,
                "confidence": 0.5,
                "reasoning": "Raw LLM response (JSON parse failed)",
            }

        sources_used = list(
            {f"{r['source_type']}:{r['source_id']}" for r in results if r.get("source_type") and r.get("source_id")}
        )
        traversal_path = [
            {"source": e["source"], "target": e["target"], "relation": e.get("relation_type", "RELATED")}
            for e in subgraph.get("edges", [])[:50]
        ]

        return {
            "answer": answer_data.get("answer", ""),
            "sources_used": sources_used,
            "traversal_path": traversal_path,
            "confidence": answer_data.get("confidence", 0.0),
            "reasoning": answer_data.get("reasoning", ""),
            "strategy": strategy,
            "total_results": len(results),
        }

    async def enrich_abstract(
        self,
        llm_client,
        abstract: str,
        top_k: int = 10,
        max_hops: int = 3,
    ) -> dict:
        strategy_prompt = _ENRICH_STRATEGY_PROMPT.format(abstract=abstract)
        strategy_raw = await llm_client.chat(strategy_prompt)
        try:
            strategy = _parse_json_response(strategy_raw)
        except Exception:
            logger.warning("Failed to parse enrich strategy, using defaults")
            strategy = {"keywords": abstract.split()[:7], "focus_types": ["method", "result"], "max_hops": max_hops}

        keywords = strategy.get("keywords", [])
        effective_hops = min(strategy.get("max_hops", max_hops), max_hops)
        query_text = " ".join(keywords) if keywords else abstract[:500]

        search_result = await self.retriever.search(
            query_text,
            top_k=top_k,
            max_hops=effective_hops,
            embedder=self._embedder,
        )

        results = search_result.get("results", [])
        subgraph = search_result.get("subgraph", {})
        provenances = subgraph.get("provenances", [])

        chunks_text = _format_results_text(results)
        source_papers = list(
            {
                p.get("source_id", "")
                for p in provenances
                if p.get("source_id")
            }
        )
        sources_text = "\n".join(
            f"- {p.get('title', 'untitled')} ({p.get('source_type', '')} {p.get('source_id', '')})"
            for p in provenances
        ) or "(no source papers found)"

        synthesis_prompt = _ENRICH_SYNTHESIS_PROMPT.format(
            abstract=abstract,
            chunks_text=chunks_text,
            sources_text=sources_text,
        )
        synthesis_raw = await llm_client.chat(synthesis_prompt)

        try:
            synthesis_data = _parse_json_response(synthesis_raw)
        except Exception:
            logger.warning("Failed to parse enrichment JSON, using raw response")
            synthesis_data = {
                "enriched_context": synthesis_raw,
                "key_methods": [],
                "key_experiments": [],
                "key_code_refs": [],
                "confidence": 0.5,
            }

        related_methods = synthesis_data.get("key_methods", [])
        related_experiments = synthesis_data.get("key_experiments", [])
        related_code = synthesis_data.get("key_code_refs", [])

        for r in results:
            rtype = (r.get("chunk_text", "") or "").lower()
            if rtype and "method" in rtype and not related_methods:
                related_methods.append(r.get("chunk_text", "")[:200])
            if rtype and ("experiment" in rtype or "evaluation" in rtype) and not related_experiments:
                related_experiments.append(r.get("chunk_text", "")[:200])

        return {
            "enriched_context": synthesis_data.get("enriched_context", ""),
            "related_methods": related_methods,
            "related_experiments": related_experiments,
            "related_code": related_code,
            "source_papers": source_papers,
            "confidence": synthesis_data.get("confidence", 0.0),
            "total_chunks_found": len(results),
        }

    async def synthesize_ideas(
        self,
        llm_client,
        seed_idea: str,
        max_depth: int = 5,
        strategy: str = "cross_domain",
    ) -> dict:
        search_prompt = _IDEA_SEARCH_PROMPT.format(seed_idea=seed_idea, strategy=strategy)
        search_raw = await llm_client.chat(search_prompt)
        try:
            search_data = _parse_json_response(search_raw)
        except Exception:
            logger.warning("Failed to parse idea search strategy, using defaults")
            search_data = {
                "keywords": seed_idea.split()[:5],
                "traversal_direction": "both",
                "focus_types": [],
                "cross_domain_hints": [],
            }

        keywords = search_data.get("keywords", [])
        query_text = " ".join(keywords) if keywords else seed_idea

        search_result = await self.retriever.search(
            query_text,
            top_k=30,
            max_hops=max_depth,
            embedder=self._embedder,
        )

        results = search_result.get("results", [])
        subgraph = search_result.get("subgraph", {})

        paths_text = _format_paths(subgraph, results)
        if not paths_text:
            paths_text = "(no knowledge paths discovered)"

        synth_prompt = _IDEA_SYNTHESIS_PROMPT.format(
            seed_idea=seed_idea,
            strategy=strategy,
            paths_text=paths_text,
        )
        synth_raw = await llm_client.chat(synth_prompt)

        try:
            synth_data = _parse_json_response(synth_raw)
        except Exception:
            logger.warning("Failed to parse idea synthesis JSON, using raw response")
            synth_data = {
                "ideas": [
                    {
                        "title": "Synthesis from knowledge graph",
                        "description": synth_raw,
                        "novelty": "unknown",
                        "feasibility": "medium",
                        "source_connections": [],
                    }
                ]
            }

        ideas = synth_data.get("ideas", [])

        source_paths: List[dict] = []
        seen_edges: set = set()
        for edge in subgraph.get("edges", []):
            key = (edge.get("source", ""), edge.get("target", ""))
            if key not in seen_edges:
                seen_edges.add(key)
                source_paths.append(
                    {
                        "from": edge.get("source", ""),
                        "to": edge.get("target", ""),
                        "relation": edge.get("relation_type", "RELATED"),
                        "confidence": edge.get("confidence", 0.0),
                    }
                )

        return {
            "synthesized_ideas": ideas,
            "source_paths": source_paths[:100],
            "idea_count": len(ideas),
            "search_strategy": search_data,
            "total_nodes_explored": len(subgraph.get("nodes", [])),
            "total_edges_traversed": len(subgraph.get("edges", [])),
        }
