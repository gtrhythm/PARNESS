import asyncio
import hashlib
import logging
from typing import Dict, List, Optional

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight, FullIdea, IdeaExplorationResult, ExplorationConfig, ResearchDirection

logger = logging.getLogger(__name__)

_QUERY_GEN_PROMPT = """You are a research literature scout. Given a research idea, generate 3-5 search queries \
to find related academic papers.

## Idea:
Title: {title}
Category: {category}
Methodology: {methodology}
Description: {description}
{direction_block}

Return JSON:
{{
  "queries": ["search query 1", "search query 2", "search query 3"]
}}

Rules:
- Queries should cover different aspects: problem domain, methodology, expected outcomes
- Use academic search terms, not casual language
- Include both broad and specific queries
"""

_ANALYSIS_PROMPT = """You are a research novelty analyst. Analyze the following research idea against related literature.

## Idea:
Title: {title}
Category: {category}
Methodology: {methodology}
Description: {description}

{papers_block}

Return JSON:
{{
  "related_work": "2-3 sentence summary of how this idea relates to existing work",
  "novelty_validation": "Is this idea novel? Explain why or why not in 2-3 sentences",
  "innovation_gaps": ["gap 1 that this idea addresses or could address", "gap 2"],
  "references_needed": ["reference topic 1 that should be cited", "reference topic 2"]
}}

Rules:
- Be specific about what makes this idea novel (or not)
- innovation_gaps should describe concrete missing pieces in the literature
- references_needed should be topics/papers that anyone pursuing this idea must read
"""


class ScoutAgent:
    def __init__(self, llm_client, max_concurrent: int = 4):
        self.llm = llm_client
        self.max_concurrent = max_concurrent

    async def explore(
        self,
        idea: FullIdea,
        config: ExplorationConfig = None,
        direction: ResearchDirection = None,
    ) -> IdeaExplorationResult:
        if config is None:
            config = ExplorationConfig()

        idea_id = hashlib.sha256(idea.title.lower().strip().encode()).hexdigest()[:16]

        direction_block = ""
        if direction:
            direction_block = f"\n## Research Direction:\n{direction.prompt_block()}"

        query_prompt = _QUERY_GEN_PROMPT.format(
            title=idea.title,
            category=idea.category,
            methodology=idea.methodology,
            description=idea.description,
            direction_block=direction_block,
        )

        try:
            resp = await call_llm(self.llm, query_prompt)
            query_data = parse_json_response(resp)
            queries = query_data.get("queries", [])
        except Exception as e:
            logger.warning("Scout query generation failed for '%s': %s", idea.title[:50], e)
            queries = [idea.title]

        all_papers = []
        seen_titles = set()
        for query in queries:
            try:
                papers = await self._search_papers(query, max_results=config.max_papers_per_idea)
                for p in papers:
                    title_key = p.get("title", "").lower().strip()
                    if title_key and title_key not in seen_titles:
                        seen_titles.add(title_key)
                        all_papers.append(p)
            except Exception as e:
                logger.warning("Scout search failed for query '%s': %s", query[:50], e)

        papers_block = ""
        if all_papers:
            papers_text = ""
            for i, p in enumerate(all_papers):
                papers_text += f"\n[{i}] {p.get('title', 'Untitled')} ({p.get('year', 'n/a')})"
                if p.get("abstract"):
                    papers_text += f"\n    Abstract: {p['abstract'][:300]}"
            papers_block = f"## Found Related Papers:{papers_text}"
        else:
            papers_block = "## Found Related Papers:\nNo related papers found. Analyze the idea for novelty gaps based on general knowledge."

        analysis_prompt = _ANALYSIS_PROMPT.format(
            title=idea.title,
            category=idea.category,
            methodology=idea.methodology,
            description=idea.description,
            papers_block=papers_block,
        )

        try:
            resp = await call_llm(self.llm, analysis_prompt)
            analysis = parse_json_response(resp)
        except Exception as e:
            logger.warning("Scout analysis failed for '%s': %s", idea.title[:50], e)
            analysis = {}

        return IdeaExplorationResult(
            idea_id=idea_id,
            idea_title=idea.title,
            search_queries=queries,
            found_papers=all_papers,
            found_insights=[p.get("title", "") for p in all_papers],
            related_work=analysis.get("related_work", ""),
            novelty_validation=analysis.get("novelty_validation", ""),
            innovation_gaps=analysis.get("innovation_gaps", []),
            references_needed=analysis.get("references_needed", []),
        )

    async def explore_batch(
        self,
        ideas: List[FullIdea],
        config: ExplorationConfig = None,
        direction: ResearchDirection = None,
    ) -> List[IdeaExplorationResult]:
        sem = asyncio.Semaphore(self.max_concurrent)

        async def _explore_one(idea: FullIdea) -> IdeaExplorationResult:
            async with sem:
                try:
                    return await self.explore(idea, config=config, direction=direction)
                except Exception as e:
                    logger.warning("Scout explore failed for '%s': %s", idea.title[:50], e)
                    idea_id = hashlib.sha256(idea.title.lower().strip().encode()).hexdigest()[:16]
                    return IdeaExplorationResult(
                        idea_id=idea_id,
                        idea_title=idea.title,
                    )

        results = await asyncio.gather(*[_explore_one(idea) for idea in ideas])
        logger.info("Scout: explored %d ideas", len(results))
        return list(results)

    async def _search_papers(self, query: str, max_results: int = 10) -> List[Dict]:
        import httpx

        papers: List[Dict] = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {
                    "query": query,
                    "limit": min(max_results, 50),
                    "fields": "paperId,externalIds,title,abstract,year,venue,citationCount",
                }
                resp = await client.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

                for item in (data.get("data") or []):
                    if not item.get("abstract"):
                        continue
                    ext = item.get("externalIds") or {}
                    arxiv_id = ext.get("ArXiv", "")
                    papers.append({
                        "title": item.get("title", ""),
                        "abstract": item.get("abstract", ""),
                        "year": item.get("year"),
                        "venue": item.get("venue", ""),
                        "arxiv_id": arxiv_id,
                        "paper_id": item.get("paperId", ""),
                        "citation_count": item.get("citationCount", 0),
                    })
        except Exception as e:
            logger.warning("Scout Semantic Scholar search failed for '%s': %s", query[:50], e)

        await asyncio.sleep(1.0)
        return papers
