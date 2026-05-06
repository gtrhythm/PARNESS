import logging
from typing import Any, Dict, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class SearchCrawlerModule(LLMAgentModule):
    module_name = "search_crawler"

    INPUT_SPEC = {
        "semantic_scholar_queries": {"type": "list", "required": False, "default": []},
        "arxiv_queries": {"type": "list", "required": False, "default": []},
        "max_papers_per_source": {"type": "int", "required": False, "default": 50},
        "year_from": {"type": "int", "required": False, "default": 2020},
        "year_to": {"type": "int", "required": False, "default": 2026},
        "use_semantic_scholar": {"type": "bool", "required": False, "default": True},
        "use_arxiv": {"type": "bool", "required": False, "default": True},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source_stats": {"type": "dict"},
        "total_found": {"type": "int"},
        "has_pdfs": {"type": "bool"},
        "_duplicate_removed": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.search_crawler.crawler import MultiSourceCrawler, SearchSourceConfig

        queries = inputs.get("semantic_scholar_queries", [])
        arxiv_queries = inputs.get("arxiv_queries", [])
        max_papers_per_source = inputs.get("max_papers_per_source", self.config.get("max_papers_per_source", 50))
        year_from = inputs.get("year_from", self.config.get("year_from", 2020))
        year_to = inputs.get("year_to", self.config.get("year_to", 2026))
        use_semantic_scholar = inputs.get("use_semantic_scholar", self.config.get("use_semantic_scholar", True))
        use_arxiv = inputs.get("use_arxiv", self.config.get("use_arxiv", True))

        if not queries and not arxiv_queries:
            raise ValueError("'queries' or 'arxiv_queries' is required")

        search_config = SearchSourceConfig(
            semantic_scholar=use_semantic_scholar,
            arxiv=use_arxiv,
            max_papers_per_source=max_papers_per_source,
            year_from=year_from,
            year_to=year_to,
        )

        crawler = MultiSourceCrawler(search_config)
        result = await crawler.search(queries, arxiv_queries)

        logger.info("SearchCrawler: found %d papers (deduped %d), sources: %s",
                     len(result.papers), result.duplicate_removed, result.source_stats)

        return {
            "metadata": result.papers,
            "paper_count": len(result.papers),
            "source_stats": result.source_stats,
            "total_found": result.total_found,
            "has_pdfs": any(p.get("pdf_url") for p in result.papers),
            "_duplicate_removed": result.duplicate_removed,
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        papers = result.get("metadata", [])
        total_found = result.get("total_found", 0)
        source_stats = result.get("source_stats", {})
        duplicate_removed = result.get("_duplicate_removed", 0)
        self._reporter.emit_output(AgentOutput(
            display_type="metrics",
            title="Search Results Summary",
            content=f"{len(papers)} papers returned from {len(source_stats)} sources",
            data={"total_found": total_found, "papers_returned": len(papers),
                  "sources": list(source_stats.keys()), "duplicates_removed": duplicate_removed},
            render_hints={"color": "blue", "icon": "layers"},
        ))
        rows = [[p.get("title","")[:80], str(p.get("year","")), p.get("venue",""),
                 str(p.get("citations",0)), p.get("paper_id","")]
                for p in papers[:50]]
        return AgentOutput(
            display_type="table",
            title=f"Papers Found ({len(papers)})",
            data={"headers": ["Title", "Year", "Venue", "Citations", "ID"], "rows": rows},
        )
