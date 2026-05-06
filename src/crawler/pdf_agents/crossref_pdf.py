import logging
from pathlib import Path
from typing import Optional

import httpx

from ..base import BasePDFAgent
from ..models import PaperContent, PDFDownloadResult
from ..tools.pdf_downloader import PDFDownloader
from ..tools.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

CROSSREF_API = "https://api.crossref.org/works"

_OA_DOMAINS = (
    "plos.org",
    "biorxiv.org",
    "medrxiv.org",
    "ncbi.nlm.nih.gov",
    "europepmc.org",
    "doi.org",
)


class CrossRefPDFAgent(BasePDFAgent):
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
                error="no_crossref_pdf",
            )

        filename = f"{PDFDownloader.sanitize_filename(paper.title, 80)}.pdf"
        output_path = output_dir / "crossref" / filename

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
        if paper.pdf_url and any(d in paper.pdf_url for d in _OA_DOMAINS):
            return True
        if paper.extra.get("crossref"):
            return True
        if paper.doi:
            return True
        return False

    async def _resolve_pdf_url(self, paper: PaperContent) -> Optional[str]:
        if paper.pdf_url and any(d in paper.pdf_url for d in _OA_DOMAINS):
            return paper.pdf_url

        if not paper.doi:
            return None

        data = await self._lookup_by_doi(paper.doi)
        if not data:
            return None

        links = data.get("link", [])
        for link in links:
            if link.get("content-type") == "application/pdf":
                return link.get("URL")

        licenses = data.get("license", [])
        for lic in licenses:
            if "creativecommons" in lic.get("URL", "").lower():
                for link in links:
                    url = link.get("URL")
                    if url:
                        return url

        return None

    async def _lookup_by_doi(self, doi: str) -> Optional[dict]:
        await self._rate_limiter.wait()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(f"{CROSSREF_API}/{doi}")
                resp.raise_for_status()
                payload = resp.json()
                return payload.get("message")
        except Exception as e:
            logger.warning("CrossRef lookup failed for %s: %s", doi, e)
            return None
