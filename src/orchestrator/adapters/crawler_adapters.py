import logging
from typing import Any, Dict

from src.orchestrator.adapters.base import LLMAgentModule

logger = logging.getLogger(__name__)


def _build_search_intent(module, inputs: Dict[str, Any]):
    from src.crawler.models import SearchIntent

    keyword_data = inputs.get("keyword")
    if isinstance(keyword_data, dict):
        keywords = [keyword_data.get("keyword", "")]
    elif isinstance(keyword_data, str):
        keywords = [keyword_data]
    else:
        keywords = inputs.get("keywords", module.config.get("keywords", []))
        if isinstance(keywords, str):
            keywords = [keywords]

    return SearchIntent(
        keywords=keywords,
        categories=inputs.get("categories", module.config.get("categories", [])),
        domain=inputs.get("domain", module.config.get("domain", "")),
        venue=inputs.get("venue", module.config.get("venue", "")),
        year_from=inputs.get("year_from", module.config.get("year_from", 0)),
        year_to=inputs.get("year_to", module.config.get("year_to", 0)),
        max_papers=inputs.get("max_papers", module.config.get("max_papers", 100)),
        sort_by=inputs.get("sort_by", module.config.get("sort_by", "date")),
    )


class LLMKeywordProviderModule(LLMAgentModule):
    module_name = "llm_keyword_provider"

    INPUT_SPEC = {
        "content": {"type": "str", "required": False, "default": ""},
        "domain": {"type": "str", "required": False, "default": ""},
        "max_keywords": {"type": "int", "required": False, "default": 10},
    }
    OUTPUT_SPEC = {
        "keywords": {"type": "list"},
        "keyword_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.keyword_providers import LLMKeywordProvider
        from src.crawler.models import KeywordResult

        content = inputs.get("content", self.config.get("content", ""))
        domain = inputs.get("domain", self.config.get("domain", ""))
        max_keywords = inputs.get("max_keywords", self.config.get("max_keywords", 10))
        llm_client = self._get_llm_client() if self.config.get("llm_client") else None

        provider = LLMKeywordProvider(llm_client=llm_client, max_keywords=max_keywords)
        results = await provider.generate(
            content=content,
            domain=domain,
            max_keywords=max_keywords,
            llm_client=llm_client,
        )

        return {
            "keywords": [kw.to_dict() for kw in results],
            "keyword_count": len(results),
        }


class ManualKeywordProviderModule(LLMAgentModule):
    module_name = "manual_keyword_provider"

    INPUT_SPEC = {
        "keywords": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "keywords": {"type": "list"},
        "keyword_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.keyword_providers import ManualListProvider

        keywords = inputs.get("keywords", self.config.get("keywords", []))
        domain = inputs.get("domain", self.config.get("domain", ""))

        provider = ManualListProvider(keywords=keywords, domain=domain)
        results = await provider.generate(keywords=keywords, domain=domain)

        return {
            "keywords": [kw.to_dict() for kw in results],
            "keyword_count": len(results),
        }


class TaxonomyExpanderModule(LLMAgentModule):
    module_name = "taxonomy_expander"

    INPUT_SPEC = {
        "domain": {"type": "str", "required": False, "default": ""},
        "category": {"type": "str", "required": False, "default": ""},
        "max_keywords": {"type": "int", "required": False, "default": 20},
    }
    OUTPUT_SPEC = {
        "keywords": {"type": "list"},
        "keyword_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.keyword_providers import TaxonomyExpander

        domain = inputs.get("domain", self.config.get("domain", ""))
        category = inputs.get("category", self.config.get("category", ""))
        max_keywords = inputs.get("max_keywords", self.config.get("max_keywords", 20))
        db_path = self.config.get("db_path", "output/papers.db")

        provider = TaxonomyExpander(db_path=db_path)
        results = await provider.generate(
            domain=domain, category=category, max_keywords=max_keywords
        )

        return {
            "keywords": [kw.to_dict() for kw in results],
            "keyword_count": len(results),
        }


class TrendKeywordProviderModule(LLMAgentModule):
    module_name = "trend_keyword_provider"

    INPUT_SPEC = {
        "domain": {"type": "str", "required": False, "default": ""},
        "days": {"type": "int", "required": False, "default": 7},
        "max_keywords": {"type": "int", "required": False, "default": 10},
    }
    OUTPUT_SPEC = {
        "keywords": {"type": "list"},
        "keyword_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.keyword_providers import TrendKeywordProvider

        domain = inputs.get("domain", self.config.get("domain", ""))
        days = inputs.get("days", self.config.get("days", 7))
        max_keywords = inputs.get("max_keywords", self.config.get("max_keywords", 10))

        provider = TrendKeywordProvider()
        results = await provider.generate(
            domain=domain, days=days, max_keywords=max_keywords
        )

        return {
            "keywords": [kw.to_dict() for kw in results],
            "keyword_count": len(results),
        }


class KeywordSelectorModule(LLMAgentModule):
    module_name = "keyword_selector"

    INPUT_SPEC = {
        "strategy": {"type": "str", "required": False, "default": "sequential"},
        "keywords": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "keyword": {"type": "dict"},
        "keyword_count": {"type": "int"},
        "selected_keyword": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        super().__init__(config)
        self._selector = None

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.keyword_selectors import (
            SequentialSelector, RandomSelector, ConfidenceSelector,
        )
        from src.crawler.models import KeywordResult

        strategy = inputs.get("strategy", self.config.get("strategy", "sequential"))
        keywords_data = inputs.get("keywords", [])

        keywords = [KeywordResult.from_dict(kw) for kw in keywords_data]
        if not keywords:
            return {"keyword": None, "keyword_count": 0}

        if self._selector is None:
            if strategy == "random":
                self._selector = RandomSelector()
            elif strategy == "confidence":
                self._selector = ConfidenceSelector()
            else:
                self._selector = SequentialSelector()

        selected = self._selector.select(keywords)
        return {
            "keyword": selected.to_dict(),
            "keyword_count": len(keywords),
            "selected_keyword": selected.keyword,
        }


class ArxivSummaryModule(LLMAgentModule):
    module_name = "arxiv_summary"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.summary_agents import ArxivSummaryAgent

        intent = _build_search_intent(self, inputs)
        agent = ArxivSummaryAgent()
        papers = await agent.fetch(intent)

        return {
            "metadata": [p.to_dict() for p in papers],
            "paper_count": len(papers),
            "source": "arxiv",
        }


class NCBISummaryModule(LLMAgentModule):
    module_name = "ncbi_summary"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.summary_agents import NCBISummaryAgent

        intent = _build_search_intent(self, inputs)
        api_key = self.config.get("ncbi_api_key", "")
        agent = NCBISummaryAgent(api_key=api_key)
        papers = await agent.fetch(intent)

        return {
            "metadata": [p.to_dict() for p in papers],
            "paper_count": len(papers),
            "source": "ncbi",
        }


class BioRxivSummaryModule(LLMAgentModule):
    module_name = "biorxiv_summary"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
        "server": {"type": "str", "required": False, "default": "biorxiv"},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.summary_agents import BioRxivSummaryAgent

        intent = _build_search_intent(self, inputs)
        server = inputs.get("server", self.config.get("server", "biorxiv"))
        agent = BioRxivSummaryAgent(server=server)
        papers = await agent.fetch(intent)

        return {
            "metadata": [p.to_dict() for p in papers],
            "paper_count": len(papers),
            "source": server,
        }


class S2SummaryModule(LLMAgentModule):
    module_name = "s2_summary"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.summary_agents import S2SummaryAgent

        intent = _build_search_intent(self, inputs)
        api_key = self.config.get("s2_api_key", "")
        agent = S2SummaryAgent(api_key=api_key)
        papers = await agent.fetch(intent)

        return {
            "metadata": [p.to_dict() for p in papers],
            "paper_count": len(papers),
            "source": "semantic_scholar",
        }


class OpenReviewSummaryModule(LLMAgentModule):
    module_name = "openreview_summary"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.summary_agents import OpenReviewSummaryAgent

        intent = _build_search_intent(self, inputs)
        agent = OpenReviewSummaryAgent()
        papers = await agent.fetch(intent)

        return {
            "metadata": [p.to_dict() for p in papers],
            "paper_count": len(papers),
            "source": "openreview",
        }


class CrawlOrchestratorModule(LLMAgentModule):
    module_name = "crawl_orchestrator"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
        "download_pdf": {"type": "bool", "required": False, "default": True},
        "output_dir": {"type": "str", "required": False, "default": "downloaded_papers"},
    }
    OUTPUT_SPEC = {
        "domain": {"type": "str"},
        "total": {"type": "int"},
        "downloaded": {"type": "int"},
        "paywalled": {"type": "int"},
        "source_stats": {"type": "dict"},
        "papers": {"type": "list"},
        "pdf_results": {"type": "list"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.orchestrator.crawl_orchestrator import CrawlOrchestrator

        intent = _build_search_intent(self, inputs)
        download_pdf = inputs.get("download_pdf", self.config.get("download_pdf", True))
        output_dir = inputs.get("output_dir", self.config.get("output_dir", "downloaded_papers"))

        orchestrator = CrawlOrchestrator(
            output_dir=output_dir,
            ncbi_api_key=self.config.get("ncbi_api_key", ""),
            s2_api_key=self.config.get("s2_api_key", ""),
            unpaywall_email=self.config.get("unpaywall_email", "research@example.com"),
        )
        result = await orchestrator.crawl(intent, download_pdf=download_pdf)

        return result.to_dict()


class CrossRefSummaryModule(LLMAgentModule):
    module_name = "crossref_summary"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.summary_agents import CrossRefSummaryAgent

        intent = _build_search_intent(self, inputs)
        agent = CrossRefSummaryAgent()
        papers = await agent.fetch(intent)

        return {
            "metadata": [p.to_dict() for p in papers],
            "paper_count": len(papers),
            "source": "crossref",
        }


class OpenAlexSummaryModule(LLMAgentModule):
    module_name = "openalex_summary"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.summary_agents import OpenAlexSummaryAgent

        intent = _build_search_intent(self, inputs)
        agent = OpenAlexSummaryAgent()
        papers = await agent.fetch(intent)

        return {
            "metadata": [p.to_dict() for p in papers],
            "paper_count": len(papers),
            "source": "openalex",
        }


class DBLPSummaryModule(LLMAgentModule):
    module_name = "dblp_summary"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.summary_agents import DBLPSummaryAgent

        intent = _build_search_intent(self, inputs)
        agent = DBLPSummaryAgent()
        papers = await agent.fetch(intent)

        return {
            "metadata": [p.to_dict() for p in papers],
            "paper_count": len(papers),
            "source": "dblp",
        }


class PLOSSummaryModule(LLMAgentModule):
    module_name = "plos_summary"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.summary_agents import PLOSSummaryAgent

        intent = _build_search_intent(self, inputs)
        agent = PLOSSummaryAgent()
        papers = await agent.fetch(intent)

        return {
            "metadata": [p.to_dict() for p in papers],
            "paper_count": len(papers),
            "source": "plos",
        }


class EuropePMCSummaryModule(LLMAgentModule):
    module_name = "europe_pmc_summary"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.summary_agents import EuropePMCSummaryAgent

        intent = _build_search_intent(self, inputs)
        agent = EuropePMCSummaryAgent()
        papers = await agent.fetch(intent)

        return {
            "metadata": [p.to_dict() for p in papers],
            "paper_count": len(papers),
            "source": "europe_pmc",
        }


class ACLSummaryModule(LLMAgentModule):
    module_name = "acl_summary"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.summary_agents import ACLSummaryAgent

        intent = _build_search_intent(self, inputs)
        agent = ACLSummaryAgent()
        papers = await agent.fetch(intent)

        return {
            "metadata": [p.to_dict() for p in papers],
            "paper_count": len(papers),
            "source": "acl",
        }


class CVFSummaryModule(LLMAgentModule):
    module_name = "cvf_summary"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.summary_agents import CVFSummaryAgent

        intent = _build_search_intent(self, inputs)
        agent = CVFSummaryAgent()
        papers = await agent.fetch(intent)

        return {
            "metadata": [p.to_dict() for p in papers],
            "paper_count": len(papers),
            "source": "cvf",
        }


class IEEESummaryModule(LLMAgentModule):
    module_name = "ieee_summary"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.summary_agents import IEEESummaryAgent

        intent = _build_search_intent(self, inputs)
        agent = IEEESummaryAgent()
        papers = await agent.fetch(intent)

        return {
            "metadata": [p.to_dict() for p in papers],
            "paper_count": len(papers),
            "source": "ieee",
        }


class FrontiersSummaryModule(LLMAgentModule):
    module_name = "frontiers_summary"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.summary_agents import FrontiersSummaryAgent

        intent = _build_search_intent(self, inputs)
        agent = FrontiersSummaryAgent()
        papers = await agent.fetch(intent)

        return {
            "metadata": [p.to_dict() for p in papers],
            "paper_count": len(papers),
            "source": "frontiers",
        }


class SSRNSummaryModule(LLMAgentModule):
    module_name = "ssrn_summary"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.summary_agents import SSRNSummaryAgent

        intent = _build_search_intent(self, inputs)
        agent = SSRNSummaryAgent()
        papers = await agent.fetch(intent)

        return {
            "metadata": [p.to_dict() for p in papers],
            "paper_count": len(papers),
            "source": "ssrn",
        }


class SpringerSummaryModule(LLMAgentModule):
    module_name = "springer_summary"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.summary_agents import SpringerSummaryAgent

        intent = _build_search_intent(self, inputs)
        api_key = self.config.get("springer_api_key", "")
        agent = SpringerSummaryAgent(api_key=api_key)
        papers = await agent.fetch(intent)

        return {
            "metadata": [p.to_dict() for p in papers],
            "paper_count": len(papers),
            "source": "springer",
        }


class ACSSummaryModule(LLMAgentModule):
    module_name = "acs_summary"

    INPUT_SPEC = {
        "keyword": {"type": "dict", "required": False, "default": None},
        "keywords": {"type": "list", "required": False, "default": []},
        "categories": {"type": "list", "required": False, "default": []},
        "domain": {"type": "str", "required": False, "default": ""},
        "venue": {"type": "str", "required": False, "default": ""},
        "year_from": {"type": "int", "required": False, "default": 0},
        "year_to": {"type": "int", "required": False, "default": 0},
        "max_papers": {"type": "int", "required": False, "default": 100},
        "sort_by": {"type": "str", "required": False, "default": "date"},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "source": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.summary_agents import ACSSummaryAgent

        intent = _build_search_intent(self, inputs)
        agent = ACSSummaryAgent()
        papers = await agent.fetch(intent)

        return {
            "metadata": [p.to_dict() for p in papers],
            "paper_count": len(papers),
            "source": "acs",
        }


class GenericPDFDownloadModule(LLMAgentModule):
    module_name = "pdf_download"

    INPUT_SPEC = {
        "papers": {"type": "list", "required": False, "default": []},
        "metadata": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "results": {"type": "list"},
        "downloaded": {"type": "int"},
        "failed": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.crawler.orchestrator.crawl_orchestrator import CrawlOrchestrator
        from src.crawler.models import PaperContent

        papers = inputs.get("papers", inputs.get("metadata", []))
        output_dir = self.config.get("output_dir", "downloaded_papers")
        orchestrator = CrawlOrchestrator(output_dir=output_dir)
        results = []
        for p in papers:
            paper = PaperContent.from_dict(p) if isinstance(p, dict) else p
            result = await orchestrator._download_pdf(paper)
            results.append({
                "paper_id": result.paper_id,
                "success": result.success,
                "pdf_path": result.pdf_path,
            })

        return {
            "results": results,
            "downloaded": sum(1 for r in results if r["success"]),
            "failed": sum(1 for r in results if not r["success"]),
        }
