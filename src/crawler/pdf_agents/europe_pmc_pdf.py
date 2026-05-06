import logging
from pathlib import Path
from typing import Optional

import httpx

from ..base import BasePDFAgent
from ..models import PaperContent, PDFDownloadResult
from ..tools.pdf_downloader import PDFDownloader
from ..tools.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

EUROPE_PMC_SEARCH_API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


class EuropePMCPDFAgent(BasePDFAgent):
    def __init__(self, downloader: PDFDownloader = None):
        self._downloader = downloader or PDFDownloader()
        self._rate_limiter = RateLimiter(min_interval=1.0)

    async def download(
        self,
        paper: PaperContent,
        output_dir: Path,
    ) -> PDFDownloadResult:
        pdf_url = await self._resolve_pdf_url(paper)
        if not pdf_url:
            return PDFDownloadResult(
                paper_id=paper.paper_id,
                success=False,
                error="no_europe_pmc_pdf",
            )

        filename = f"{PDFDownloader.sanitize_filename(paper.title, 80)}.pdf"
        output_path = output_dir / "europe_pmc" / filename

        result = await self._downloader.download(pdf_url, output_path)
        if result:
            return PDFDownloadResult(
                paper_id=paper.paper_id,
                success=True,
                pdf_path=str(result),
                file_size=result.stat().st_size,
            )
        return PDFDownloadResult(
            paper_id=paper.paper_id,
            success=False,
            error="download_failed",
        )

    def can_download(self, paper: PaperContent) -> bool:
        if paper.source == "europe_pmc":
            return True
        if paper.pdf_url and "europepmc" in paper.pdf_url:
            return True
        if paper.extra.get("europepmc") or paper.extra.get("pmcid"):
            return True
        if paper.doi:
            return True
        return False

    async def _resolve_pdf_url(self, paper: PaperContent) -> Optional[str]:
        pmcid = paper.extra.get("pmcid")
        if pmcid:
            return (
                f"https://europepmc.org/backend/ptpmcrender.fcgi"
                f"?accid={pmcid}&blobtype=pdf"
            )

        if not paper.doi:
            return None

        data = await self._lookup_by_doi(paper.doi)
        if not data:
            return None

        pmcid = data.get("pmcid")
        if pmcid:
            return (
                f"https://europepmc.org/backend/ptpmcrender.fcgi"
                f"?accid={pmcid}&blobtype=pdf"
            )

        if data.get("isOpenAccess") == "Y":
            url = data.get("url")
            if url:
                return url

        return None

    async def _lookup_by_doi(self, doi: str) -> Optional[dict]:
        await self._rate_limiter.wait()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    EUROPE_PMC_SEARCH_API,
                    params={"query": f"DOI:{doi}", "format": "json"},
                )
                resp.raise_for_status()
                payload = resp.json()

                results = payload.get("resultList", {}).get("result", [])
                if results:
                    return results[0]
                return None
        except Exception as e:
            logger.warning("Europe PMC lookup failed for %s: %s", doi, e)
            return None
