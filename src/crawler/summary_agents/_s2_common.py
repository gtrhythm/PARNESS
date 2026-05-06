"""Shared helpers for S2-backed summary agents.

Several venue-specific summary agents (cvf, acl, ieee, frontiers, ssrn, acs)
proxy through Semantic Scholar's `/paper/search` and parse the same record
shape as `s2_summary.py`. This module centralizes the bits that must stay
consistent across them — most importantly the choice of PDF URL.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

S2_FIELDS = (
    "paperId,externalIds,title,abstract,year,venue,fieldsOfStudy,"
    "citationCount,openAccessPdf,isOpenAccess"
)


async def s2_request_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: dict,
    headers: dict,
    max_attempts: int = 5,
    backoff_min: float = 1.0,
    backoff_max: float = 5.0,
) -> Optional[dict]:
    for attempt in range(max_attempts):
        try:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429,) or resp.status_code >= 500:
                delay = random.uniform(backoff_min, backoff_max)
                logger.info(
                    "S2 %s -> HTTP %d (attempt %d/%d), retrying in %.2fs",
                    url, resp.status_code, attempt + 1, max_attempts, delay,
                )
                await asyncio.sleep(delay)
                continue
            logger.warning("S2 %s -> HTTP %d (non-retriable): %s",
                           url, resp.status_code, resp.text[:200])
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            delay = random.uniform(backoff_min, backoff_max)
            logger.info(
                "S2 %s network error (attempt %d/%d): %s; retrying in %.2fs",
                url, attempt + 1, max_attempts, e, delay,
            )
            await asyncio.sleep(delay)
    logger.warning("S2 %s gave up after %d attempts", url, max_attempts)
    return None


def pick_s2_pdf_url(item: dict) -> Optional[str]:
    """Pick the most reliably-downloadable PDF URL from an S2 record.

    arxiv.org direct links are preferred over `openAccessPdf.url` because
    publisher-hosted OA links are frequently 403'd by Cloudflare/anti-scrape
    while arxiv is always reachable. Empirical baseline: arxiv 100%,
    publisher OA links ~25% (see scripts/test_s2_oa_download.py).
    """
    external_ids = item.get("externalIds") or {}
    arxiv_id = external_ids.get("ArXiv") or ""
    if arxiv_id:
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    oa = item.get("openAccessPdf")
    if isinstance(oa, dict):
        url = oa.get("url")
        if url:
            return url
    return None
