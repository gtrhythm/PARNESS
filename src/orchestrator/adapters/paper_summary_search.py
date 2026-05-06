import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseModule
from ...crawler.models import PaperContent, SearchIntent

logger = logging.getLogger(__name__)

_DEFAULT_ORDER = [
    "s2",
    "crossref",
    "openalex",
    "openreview",
    "arxiv",
    "ncbi",
    "dblp",
    "europe_pmc",
    "cvf",
    "acl",
    "biorxiv",
    "ieee",
    "frontiers",
    "plos",
    "springer",
    "ssrn",
    "acs",
]


def _build_agent(name: str, config: dict):
    s2_key = config.get("s2_api_key") or os.getenv("S2_API_KEY", "")
    ncbi_key = config.get("ncbi_api_key") or os.getenv("NCBI_API_KEY", "")
    mailto = config.get("mailto", "research@example.com")
    s2_key_shared = config.get("s2_api_key_shared") or s2_key

    agents = {
        "s2": ("src.crawler.summary_agents.s2_summary", "S2SummaryAgent", lambda: s2_key),
        "crossref": ("src.crawler.summary_agents.crossref_summary", "CrossRefSummaryAgent", lambda: ""),
        "openalex": ("src.crawler.summary_agents.openalex_summary", "OpenAlexSummaryAgent", lambda: mailto),
        "openreview": ("src.crawler.summary_agents.openreview_summary", "OpenReviewSummaryAgent", lambda: None),
        "arxiv": ("src.crawler.summary_agents.arxiv_summary", "ArxivSummaryAgent", lambda: None),
        "ncbi": ("src.crawler.summary_agents.ncbi_summary", "NCBISummaryAgent", lambda: ncbi_key),
        "dblp": ("src.crawler.summary_agents.dblp_summary", "DBLPSummaryAgent", lambda: None),
        "europe_pmc": ("src.crawler.summary_agents.europe_pmc_summary", "EuropePMCSummaryAgent", lambda: None),
        "cvf": ("src.crawler.summary_agents.cvf_summary", "CVFSummaryAgent", lambda: s2_key_shared),
        "acl": ("src.crawler.summary_agents.acl_summary", "ACLSummaryAgent", lambda: s2_key_shared),
        "biorxiv": ("src.crawler.summary_agents.biorxiv_summary", "BioRxivSummaryAgent", lambda: None),
        "ieee": ("src.crawler.summary_agents.ieee_summary", "IEEESummaryAgent", lambda: s2_key),
        "frontiers": ("src.crawler.summary_agents.frontiers_summary", "FrontiersSummaryAgent", lambda: s2_key_shared),
        "plos": ("src.crawler.summary_agents.plos_summary", "PLOSSummaryAgent", lambda: None),
        "springer": ("src.crawler.summary_agents.springer_summary", "SpringerSummaryAgent", lambda: ""),
        "ssrn": ("src.crawler.summary_agents.ssrn_summary", "SSRNSummaryAgent", lambda: s2_key_shared),
        "acs": ("src.crawler.summary_agents.acs_summary", "ACSSummaryAgent", lambda: s2_key_shared),
    }

    if name not in agents:
        return None

    import importlib
    mod_path, cls_name, arg_fn = agents[name]
    try:
        mod = importlib.import_module(mod_path)
        cls = getattr(mod, cls_name)
        arg = arg_fn()
        if arg is None:
            return cls()
        return cls(arg)
    except Exception as e:
        logger.warning("Failed to init agent '%s': %s", name, e)
        return None


class PaperSummarySearchModule(BaseModule):
    """Search paper summary by title across multiple sources in fallback order.

    Stops at the first source that returns results.

    Params:
        search_order: List[str] — ordered source names (default: s2, crossref, openalex, ...)
        s2_api_key: str
        ncbi_api_key: str
        mailto: str
        s2_api_key_shared: str — key for agents that use S2 as secondary lookup

    Input:
        title: str — paper title to search
        keywords: List[str] — alternative: used if title is empty

    Output:
        metadata: Dict — first matched paper (PaperContent.to_dict())
        source: str — which source matched
        paper_count: int — 0 or 1
        _route: "success" | "fail"
    """

    module_name = "paper_summary_search"

    INPUT_SPEC = {
        "title": {"type": "str", "required": False, "default": ""},
        "keywords": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "dict"},
        "source": {"type": "str"},
        "paper_count": {"type": "int"},
        "_route": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        title = inputs.get("title", "")
        if not title:
            kw = inputs.get("keywords", [])
            if isinstance(kw, list) and kw:
                title = kw[0] if isinstance(kw[0], str) else str(kw[0])
            elif isinstance(kw, str):
                title = kw

        if not title:
            logger.warning("PaperSummarySearch: no title or keywords provided")
            return {"metadata": {}, "source": "", "paper_count": 0, "_route": "fail"}

        intent = SearchIntent(keywords=[title], max_papers=1)

        search_order = self.config.get("search_order", _DEFAULT_ORDER)

        for source_name in search_order:
            agent = _build_agent(source_name, self.config)
            if agent is None:
                continue

            try:
                results: List[PaperContent] = await agent.fetch(intent)
            except Exception as e:
                logger.debug("PaperSummarySearch: %s failed: %s", source_name, e)
                continue

            if not results:
                logger.debug("PaperSummarySearch: %s returned 0 results for '%s'",
                             source_name, title[:80])
                continue

            paper = results[0]
            logger.info("PaperSummarySearch: found '%s' via %s",
                        (paper.title or title)[:80], source_name)

            return {
                "metadata": paper.to_dict(),
                "source": source_name,
                "paper_count": 1,
                "_route": "success",
            }

        logger.warning("PaperSummarySearch: all sources exhausted for '%s'", title[:80])
        return {"metadata": {}, "source": "", "paper_count": 0, "_route": "fail"}
