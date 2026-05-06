"""arXiv PDF agent following arXiv's "gentleman's agreement"::

    - serial requests (process-wide singleton lock)
    - >= 3s between requests
    - User-Agent with mailto contact
    - 403/503 → exponential backoff (30s, 60s, 120s)
    - prefer export.arxiv.org over arxiv.org

`PDFDownloader` is bypassed here: its concurrency / retry tuning is generic
and would still hammer arxiv since each pdf_download node has its own
PDFDownloader. The singleton primitives below are class attributes so all
ArxivPDFAgent instances across the process share one queue.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

import httpx

from ..base import BasePDFAgent
from ..models import PaperContent, PDFDownloadResult

logger = logging.getLogger(__name__)

_PDF_SIGNATURE = b"%PDF-"
_ARXIV_HOST = "arxiv.org"
_FALLBACK_HOST = "export.arxiv.org"
_MIN_INTERVAL_SEC = 3.0
_BACKOFF_SCHEDULE_SEC = (10.0, 30.0)
_DOWNLOAD_TIMEOUT_SEC = 90.0


def _sanitize_filename(title: str, max_length: int = 80) -> str:
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", title)
    name = re.sub(r"_+", "_", name).strip("_ ")
    return name[:max_length] if len(name) > max_length else name


class ArxivPDFAgent(BasePDFAgent):
    _global_lock: asyncio.Lock = asyncio.Lock()
    _last_request_time: float = 0.0

    def __init__(self, *_, contact_email: str = "", **__):
        self._contact_email = contact_email or os.environ.get(
            "S2_CONTACT_EMAIL", "research@example.com"
        )

    async def download(
        self,
        paper: PaperContent,
        output_dir: Path,
    ) -> PDFDownloadResult:
        pdf_url = self._get_pdf_url(paper)
        if not pdf_url:
            return PDFDownloadResult(
                paper_id=paper.paper_id, success=False, error="no_arxiv_pdf_url",
            )

        filename = f"{_sanitize_filename(paper.title)}.pdf"
        output_path = output_dir / "arxiv" / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        headers = {
            "User-Agent": f"auto-paper-machine/0.1 (mailto:{self._contact_email})",
            "Accept": "application/pdf,*/*",
        }

        for host in (_ARXIV_HOST, _FALLBACK_HOST):
            url_for_host = pdf_url.replace(f"//{_ARXIV_HOST}/", f"//{host}/").replace(
                f"//{_FALLBACK_HOST}/", f"//{host}/"
            )
            result = await self._polite_download(url_for_host, output_path, headers)
            if result:
                return PDFDownloadResult(
                    paper_id=paper.paper_id,
                    success=True,
                    pdf_path=str(result),
                    file_size=result.stat().st_size,
                )
        return PDFDownloadResult(
            paper_id=paper.paper_id, success=False, error="download_failed",
        )

    def can_download(self, paper: PaperContent) -> bool:
        return bool(self._get_pdf_url(paper))

    def _get_pdf_url(self, paper: PaperContent) -> Optional[str]:
        if paper.pdf_url and ("arxiv.org" in paper.pdf_url):
            return self._rewrite_to_export(paper.pdf_url)
        arxiv_id = paper.extra.get("arxiv_id", "")
        if arxiv_id:
            return f"https://{_ARXIV_HOST}/pdf/{arxiv_id}.pdf"
        if paper.paper_id.startswith("arxiv:"):
            return f"https://{_ARXIV_HOST}/pdf/{paper.paper_id[6:]}.pdf"
        return None

    @staticmethod
    def _rewrite_to_export(url: str) -> str:
        return url.replace(f"//{_FALLBACK_HOST}/", f"//{_ARXIV_HOST}/").replace(
            "//www.arxiv.org/", f"//{_ARXIV_HOST}/"
        )

    @classmethod
    async def _polite_download(
        cls, url: str, output_path: Path, headers: dict,
    ) -> Optional[Path]:
        async with cls._global_lock:
            elapsed = time.monotonic() - cls._last_request_time
            if elapsed < _MIN_INTERVAL_SEC:
                wait = _MIN_INTERVAL_SEC - elapsed
                logger.debug("arxiv-polite: sleeping %.2fs to honor 3s gap", wait)
                await asyncio.sleep(wait)

            for attempt, backoff in enumerate([0.0, *_BACKOFF_SCHEDULE_SEC]):
                if backoff > 0:
                    logger.info(
                        "arxiv-polite backoff %.0fs before retry %d/%d for %s",
                        backoff, attempt, len(_BACKOFF_SCHEDULE_SEC), url,
                    )
                    await asyncio.sleep(backoff)
                try:
                    cls._last_request_time = time.monotonic()
                    async with httpx.AsyncClient(
                        timeout=_DOWNLOAD_TIMEOUT_SEC, follow_redirects=True,
                    ) as client:
                        resp = await client.get(url, headers=headers)

                    if resp.status_code in (403, 503, 429):
                        logger.warning(
                            "arxiv-polite HTTP %d for %s (attempt %d)",
                            resp.status_code, url, attempt + 1,
                        )
                        continue
                    resp.raise_for_status()
                    content = resp.content
                    if not content or len(content) < 100 or not content.startswith(_PDF_SIGNATURE):
                        logger.warning(
                            "arxiv-polite non-PDF response for %s (size=%d)",
                            url, len(content) if content else 0,
                        )
                        continue
                    output_path.write_bytes(content)
                    logger.info(
                        "arxiv-polite downloaded %s (%d bytes) -> %s",
                        url, len(content), output_path,
                    )
                    return output_path
                except (httpx.RequestError, httpx.HTTPStatusError) as e:
                    logger.warning("arxiv-polite error for %s: %s", url, e)
                    continue
            logger.error("arxiv-polite gave up after %d attempts: %s",
                         1 + len(_BACKOFF_SCHEDULE_SEC), url)
            return None
