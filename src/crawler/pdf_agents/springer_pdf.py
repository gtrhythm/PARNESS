import logging
from pathlib import Path
from typing import Optional

import httpx

from ..base import BasePDFAgent
from ..models import PaperContent, PDFDownloadResult
from ..tools.pdf_downloader import PDFDownloader
from ..tools.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

SPRINGER_OA_API = "https://api.springernature.com/openaccess/json"


class SpringerPDFAgent(BasePDFAgent):
    def __init__(self, downloader: PDFDownloader = None, api_key: str = ""):
        self._downloader = downloader or PDFDownloader()
        self._api_key = api_key
        self._rate_limiter = RateLimiter(min_interval=0.5)

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
                error="no_springer_pdf",
            )

        filename = f"{PDFDownloader.sanitize_filename(paper.title, 80)}.pdf"
        output_path = output_dir / "springer" / filename

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
        if paper.pdf_url and "springer.com" in paper.pdf_url:
            return True
        if paper.source == "springer":
            return True
        return False

    async def _resolve_pdf_url(self, paper: PaperContent) -> Optional[str]:
        if paper.pdf_url:
            return paper.pdf_url

        if not paper.doi or not self._api_key:
            return None

        await self._rate_limiter.wait()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    SPRINGER_OA_API,
                    params={"q": f"doi:{paper.doi}", "api_key": self._api_key},
                )
                resp.raise_for_status()
                data = resp.json()

                records = data.get("records", [])
                if not records:
                    return None

                record = records[0]
                for url_entry in record.get("url", []):
                    if isinstance(url_entry, dict):
                        fmt = url_entry.get("format", "")
                        if "pdf" in fmt.lower():
                            return url_entry.get("value")
                    elif isinstance(url_entry, str) and "pdf" in url_entry.lower():
                        return url_entry

                return None
        except Exception as e:
            logger.warning("Springer OA lookup failed for %s: %s", paper.doi, e)
            return None
