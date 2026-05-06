import logging
from pathlib import Path
from typing import Optional

import httpx

from ..base import BasePDFAgent
from ..models import PaperContent, PDFDownloadResult
from ..tools.pdf_downloader import PDFDownloader
from ..tools.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

NCBI_OA_API = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"


class NCBIPDFAgent(BasePDFAgent):
    def __init__(self, downloader: PDFDownloader = None, api_key: str = ""):
        self._downloader = downloader or PDFDownloader()
        self._api_key = api_key
        self._rate_limiter = RateLimiter(min_interval=0.5)

    async def download(
        self,
        paper: PaperContent,
        output_dir: Path,
    ) -> PDFDownloadResult:
        pmid = paper.extra.get("pmid", "")
        doi = paper.doi

        pdf_url = await self._find_oa_pdf(pmid, doi)
        if not pdf_url:
            return PDFDownloadResult(
                paper_id=paper.paper_id,
                success=False,
                error="not_in_pmc_oa",
            )

        filename = f"{PDFDownloader.sanitize_filename(paper.title, 80)}.pdf"
        output_path = output_dir / "pmc" / filename

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
        if paper.source in ("ncbi", "pubmed", "pmc"):
            return True
        if paper.extra.get("pmid"):
            return True
        return False

    async def _find_oa_pdf(self, pmid: str, doi: Optional[str]) -> Optional[str]:
        await self._rate_limiter.wait()
        params = {}
        if pmid:
            params["id"] = pmid
        elif doi:
            params["id"] = f"doi:{doi}"
        else:
            return None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(NCBI_OA_API, params=params)
                resp.raise_for_status()
                import xml.etree.ElementTree as ET
                root = ET.fromstring(resp.text)

                for error in root.findall(".//error"):
                    return None

                for record in root.findall(".//record"):
                    for link in record.findall("link"):
                        fmt = link.get("format", "")
                        if fmt == "pdf":
                            return link.text.strip()
                        if fmt == "tgz":
                            continue
                return None
        except Exception as e:
            logger.warning("NCBI OA lookup failed: %s", e)
            return None
