import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..base import BasePDFAgent, BaseSummaryAgent
from ..models import PaperContent, PDFDownloadResult, SearchIntent
from ..summary_agents import (
    ArxivSummaryAgent,
    NCBISummaryAgent,
    BioRxivSummaryAgent,
    S2SummaryAgent,
    OpenReviewSummaryAgent,
    CrossRefSummaryAgent,
    OpenAlexSummaryAgent,
    DBLPSummaryAgent,
    PLOSSummaryAgent,
    EuropePMCSummaryAgent,
    ACLSummaryAgent,
    CVFSummaryAgent,
    IEEESummaryAgent,
    FrontiersSummaryAgent,
    SSRNSummaryAgent,
    SpringerSummaryAgent,
    ACSSummaryAgent,
)
from ..pdf_agents import (
    ArxivPDFAgent,
    NCBIPDFAgent,
    BioRxivPDFAgent,
    S2PDFAgent,
    UnpaywallPDFAgent,
    OpenReviewPDFAgent,
    PLOSPDFAgent,
    EuropePMCPDFAgent,
    CrossRefPDFAgent,
)
from ..tools.dedup import deduplicate_papers

logger = logging.getLogger(__name__)

DOMAIN_SUMMARY_AGENTS: Dict[str, List[str]] = {
    "cs": ["arxiv", "s2", "dblp", "openalex"],
    "physics": ["arxiv", "s2"],
    "math": ["arxiv", "s2"],
    "stat": ["arxiv", "s2"],
    "nlp": ["arxiv", "s2", "openreview", "acl"],
    "cv": ["arxiv", "s2", "openreview", "cvf"],
    "eess": ["arxiv", "s2", "ieee"],
    "bio": ["s2", "ncbi", "biorxiv"],
    "neuroscience": ["s2", "ncbi", "biorxiv"],
    "psychology": ["s2", "ncbi"],
    "biology": ["s2", "ncbi", "biorxiv", "plos", "europe_pmc"],
    "medicine": ["s2", "ncbi", "biorxiv", "plos", "frontiers", "europe_pmc"],
    "chemistry": ["s2", "crossref", "springer", "acs"],
    "materials": ["s2", "crossref", "springer"],
    "economics": ["s2", "crossref", "ssrn"],
    "social_science": ["s2", "crossref", "ssrn", "openalex"],
    "engineering": ["s2", "crossref", "ieee", "springer"],
}

PDF_AGENT_PRIORITY: List[str] = [
    "arxiv",
    "openreview",
    "biorxiv",
    "plos",
    "s2",
    "acl",
    "cvf",
    "frontiers",
    "europe_pmc",
    "ncbi",
    "crossref",
    "springer",
    "ssrn",
    "unpaywall",
    "ieee",
    "acs",
]


@dataclass
class CrawlResult:
    domain: str
    papers: List[PaperContent]
    pdf_results: List[PDFDownloadResult]
    total: int = 0
    downloaded: int = 0
    paywalled: int = 0
    source_stats: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "total": self.total,
            "downloaded": self.downloaded,
            "paywalled": self.paywalled,
            "source_stats": self.source_stats,
            "papers": [p.to_dict() for p in self.papers],
            "pdf_results": [r.to_dict() for r in self.pdf_results],
        }


class CrawlOrchestrator:
    def __init__(
        self,
        output_dir: str = "downloaded_papers",
        ncbi_api_key: str = "",
        s2_api_key: str = "",
        unpaywall_email: str = "research@example.com",
    ):
        self._output_dir = Path(output_dir)
        self._summary_agents: Dict[str, BaseSummaryAgent] = {
            "arxiv": ArxivSummaryAgent(),
            "ncbi": NCBISummaryAgent(api_key=ncbi_api_key),
            "biorxiv": BioRxivSummaryAgent(),
            "s2": S2SummaryAgent(api_key=s2_api_key),
            "openreview": OpenReviewSummaryAgent(),
            "crossref": CrossRefSummaryAgent(),
            "openalex": OpenAlexSummaryAgent(),
            "dblp": DBLPSummaryAgent(),
            "plos": PLOSSummaryAgent(),
            "europe_pmc": EuropePMCSummaryAgent(),
            "acl": ACLSummaryAgent(),
            "cvf": CVFSummaryAgent(),
            "ieee": IEEESummaryAgent(),
            "frontiers": FrontiersSummaryAgent(),
            "ssrn": SSRNSummaryAgent(),
            "springer": SpringerSummaryAgent(),
            "acs": ACSSummaryAgent(),
        }
        self._pdf_agents: Dict[str, BasePDFAgent] = {
            "arxiv": ArxivPDFAgent(),
            "ncbi": NCBIPDFAgent(api_key=ncbi_api_key),
            "biorxiv": BioRxivPDFAgent(),
            "s2": S2PDFAgent(),
            "unpaywall": UnpaywallPDFAgent(email=unpaywall_email),
            "openreview": OpenReviewPDFAgent(),
            "plos": PLOSPDFAgent(),
            "europe_pmc": EuropePMCPDFAgent(),
            "crossref": CrossRefPDFAgent(),
        }

    async def crawl(
        self,
        intent: SearchIntent,
        download_pdf: bool = True,
        summary_agents: Optional[List[str]] = None,
    ) -> CrawlResult:
        agent_names = summary_agents or DOMAIN_SUMMARY_AGENTS.get(
            intent.domain, ["s2"]
        )

        all_contents: List[PaperContent] = []
        source_stats: Dict[str, int] = {}

        for name in agent_names:
            agent = self._summary_agents.get(name)
            if not agent:
                logger.warning("Unknown summary agent: %s", name)
                continue
            try:
                contents = await agent.fetch(intent)
                all_contents.extend(contents)
                source_stats[name] = len(contents)
                logger.info(
                    "SummaryAgent %s: %d papers", name, len(contents)
                )
                await asyncio.sleep(agent.rate_limit())
            except Exception as e:
                logger.error("SummaryAgent %s failed: %s", name, e)

        unique_contents = deduplicate_papers(all_contents)

        pdf_results: List[PDFDownloadResult] = []
        if download_pdf:
            for content in unique_contents:
                result = await self._download_pdf(content)
                pdf_results.append(result)

        return CrawlResult(
            domain=intent.domain,
            papers=unique_contents,
            pdf_results=pdf_results,
            total=len(unique_contents),
            downloaded=sum(1 for r in pdf_results if r.success),
            paywalled=sum(
                1 for r in pdf_results if not r.success and r.error in ("paywalled", "no_oa_version_found")
            ),
            source_stats=source_stats,
        )

    async def _download_pdf(
        self,
        paper: PaperContent,
    ) -> PDFDownloadResult:
        for agent_name in PDF_AGENT_PRIORITY:
            agent = self._pdf_agents.get(agent_name)
            if not agent:
                continue
            if not agent.can_download(paper):
                continue
            try:
                result = await agent.download(paper, self._output_dir)
                if result.success:
                    return result
            except Exception as e:
                logger.debug("PDFAgent %s failed for %s: %s", agent_name, paper.paper_id, e)

        return PDFDownloadResult(
            paper_id=paper.paper_id,
            success=False,
            pdf_path=None,
            error="paywalled",
        )
