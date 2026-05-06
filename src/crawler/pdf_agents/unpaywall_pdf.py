import logging
from pathlib import Path
from typing import Optional

import httpx

from ..base import BasePDFAgent
from ..models import PaperContent, PDFDownloadResult
from ..tools.pdf_downloader import PDFDownloader
from ..tools.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

UNPAYWALL_API = "https://api.unpaywall.org/v2"


class UnpaywallPDFAgent(BasePDFAgent):
    def __init__(self, downloader: PDFDownloader = None, email: str = "research@example.com"):
        self._downloader = downloader or PDFDownloader()
        self._email = email
        self._rate_limiter = RateLimiter(min_interval=1.0)

    async def download(
        self,
        paper: PaperContent,
        output_dir: Path,
    ) -> PDFDownloadResult:
        if not paper.doi:
            return PDFDownloadResult(
                paper_id=paper.paper_id,
                success=False,
                error="no_doi_for_unpaywall",
            )

        oa_url = await self._lookup_oa(paper.doi)
        if not oa_url:
            return PDFDownloadResult(
                paper_id=paper.paper_id,
                success=False,
                error="no_oa_version_found",
            )

        filename = f"{PDFDownloader.sanitize_filename(paper.title, 80)}.pdf"
        output_path = output_dir / "unpaywall" / filename

        result = await self._downloader.download(oa_url, output_path)
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
        return bool(paper.doi)

    async def _lookup_oa(self, doi: str) -> Optional[str]:
        await self._rate_limiter.wait()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{UNPAYWALL_API}/{doi}",
                    params={"email": self._email},
                )
                resp.raise_for_status()
                data = resp.json()

                if not data.get("is_oa"):
                    return None

                best = data.get("best_oa_location")
                if best:
                    url = best.get("url_for_pdf") or best.get("url_for_landing_page")
                    if url:
                        return url

                for loc in data.get("oa_locations", []):
                    url = loc.get("url_for_pdf") or loc.get("url")
                    if url:
                        return url

                return None
        except Exception as e:
            logger.warning("Unpaywall lookup failed for %s: %s", doi, e)
            return None
