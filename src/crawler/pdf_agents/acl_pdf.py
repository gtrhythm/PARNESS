import logging
from pathlib import Path
from typing import Optional

from ..base import BasePDFAgent
from ..models import PaperContent, PDFDownloadResult
from ..tools.pdf_downloader import PDFDownloader

logger = logging.getLogger(__name__)


class ACLPDFAgent(BasePDFAgent):
    def __init__(self, downloader: PDFDownloader = None):
        self._downloader = downloader or PDFDownloader()

    async def download(
        self,
        paper: PaperContent,
        output_dir: Path,
    ) -> PDFDownloadResult:
        pdf_url = self._get_pdf_url(paper)
        if not pdf_url:
            return PDFDownloadResult(
                paper_id=paper.paper_id,
                success=False,
                error="no_acl_pdf_url",
            )

        filename = f"{PDFDownloader.sanitize_filename(paper.title, 80)}.pdf"
        output_path = output_dir / "acl" / filename

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
        if paper.pdf_url and "aclanthology.org" in paper.pdf_url:
            return True
        if paper.source == "acl":
            return True
        return False

    def _get_pdf_url(self, paper: PaperContent) -> Optional[str]:
        if paper.pdf_url and "aclanthology.org" in paper.pdf_url:
            if paper.pdf_url.endswith(".pdf"):
                return paper.pdf_url
            url = paper.pdf_url.rstrip("/")
            return f"{url}.pdf"
        if paper.source == "acl" and paper.extra.get("acl_id"):
            return f"https://aclanthology.org/{paper.extra['acl_id']}.pdf"
        return None
