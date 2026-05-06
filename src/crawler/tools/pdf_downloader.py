import asyncio
import logging
import re
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_PDF_SIGNATURE = b"%PDF-"


class PDFDownloader:
    def __init__(
        self,
        max_concurrent: int = 5,
        timeout: float = 60.0,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ):
        self._sem = asyncio.Semaphore(max_concurrent)
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_delay = retry_delay

    async def download(
        self,
        url: str,
        output_path: Path,
        headers: Optional[dict] = None,
    ) -> Optional[Path]:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        default_headers = {
            "User-Agent": "Mozilla/5.0 (compatible; AcademicPaperCrawler/1.0)",
            "Accept": "application/pdf,*/*",
        }
        if headers:
            default_headers.update(headers)

        async with self._sem:
            for attempt in range(self._max_retries):
                try:
                    async with httpx.AsyncClient(
                        timeout=self._timeout,
                        follow_redirects=True,
                    ) as client:
                        resp = await client.get(url, headers=default_headers)
                        resp.raise_for_status()

                        content = resp.content
                        if not content or len(content) < 100:
                            raise ValueError("Response too small to be a PDF")

                        if not content.startswith(_PDF_SIGNATURE):
                            raise ValueError("Response is not a valid PDF")

                        output_path.write_bytes(content)
                        logger.info(
                            "Downloaded %s (%d bytes) -> %s",
                            url, len(content), output_path,
                        )
                        return output_path

                except Exception as e:
                    logger.warning(
                        "Download attempt %d/%d failed for %s: %s",
                        attempt + 1, self._max_retries, url, e,
                    )
                    if attempt < self._max_retries - 1:
                        await asyncio.sleep(self._retry_delay * (attempt + 1))

        logger.error("All download attempts failed for %s", url)
        return None

    @staticmethod
    def sanitize_filename(title: str, max_length: int = 120) -> str:
        name = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", title)
        name = re.sub(r"_+", "_", name).strip("_ ")
        return name[:max_length] if len(name) > max_length else name
