"""Paper-search persistence adapter.

Writes search results from an S2 (or other) summary node + PDF download node to
a folder-based store. PDF and summary share the same `paper_id` stem so they
are trivially linkable. Optionally fetches the per-paper reference list from
the S2 graph API.

Folder layout::

    <output_dir>/
        pdfs/<safe_id>.pdf
        summaries/<safe_id>.json
        references/<safe_id>.json
        index_<tag>.jsonl

`safe_id` = `paper_id.replace(":", "_")` so colons never reach the filesystem.

This adapter does NOT touch papers.db; persistence is purely file-based.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from src.crawler.summary_agents._s2_common import s2_request_with_retry
from src.orchestrator.adapters.base import BaseModule

logger = logging.getLogger(__name__)

S2_API = "https://api.semanticscholar.org/graph/v1"
S2_REF_FIELDS = "title,year,authors,externalIds,venue"


def _safe_id(paper_id: str) -> str:
    return paper_id.replace(":", "_").replace("/", "_")


def _build_s2_headers(api_key: str, contact_email: str = "") -> dict:
    ua = "auto-paper-machine/0.1"
    if contact_email:
        ua = f"{ua} (mailto:{contact_email})"
    headers = {"User-Agent": ua, "Accept": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def _resolve_s2_lookup_id(paper: dict) -> Optional[str]:
    pid = paper.get("paper_id", "")
    if pid.startswith("s2:"):
        return pid[3:]
    extra = paper.get("extra") or {}
    s2_id = extra.get("s2_id") or ""
    if s2_id:
        return s2_id
    doi = paper.get("doi", "")
    if doi:
        return f"DOI:{doi}"
    arxiv_id = extra.get("arxiv_id", "")
    if arxiv_id:
        return f"ARXIV:{arxiv_id}"
    return None


def _extract_ref_record(item: dict) -> dict:
    cited = item.get("citedPaper") or {}
    ext = cited.get("externalIds") or {}
    return {
        "title": cited.get("title", "") or "",
        "year": cited.get("year"),
        "doi": ext.get("DOI", "") or "",
        "arxiv_id": ext.get("ArXiv", "") or "",
        "s2_id": cited.get("paperId", "") or "",
        "venue": cited.get("venue", "") or "",
        "authors": [a.get("name", "") for a in (cited.get("authors") or []) if a.get("name")],
    }


class PaperSearchPersistModule(BaseModule):
    module_name = "paper_search_persist"

    INPUT_SPEC = {
        "metadata": {"type": "list", "required": False, "default": []},
        "pdf_results": {"type": "list", "required": False, "default": []},
        "source": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "persisted_count": {"type": "int"},
        "pdf_count": {"type": "int"},
        "references_count": {"type": "int"},
        "index_path": {"type": "str"},
        "output_dir": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        metadata: List[dict] = inputs.get("metadata", []) or []
        pdf_results: List[dict] = inputs.get("pdf_results", []) or []
        source: str = inputs.get("source") or self.config.get("source", "s2")
        tag: str = self.config.get("tag", source)
        output_dir = Path(self.config.get("output_dir", "downloaded_papers/paper_search"))
        fetch_references: bool = bool(self.config.get("fetch_references", True))
        api_key: str = self.config.get("s2_api_key") or os.environ.get("S2_API_KEY", "")
        contact_email: str = self.config.get("s2_contact_email") or os.environ.get("S2_CONTACT_EMAIL", "")

        summaries_dir = output_dir / "summaries"
        references_dir = output_dir / "references"
        pdfs_dir = output_dir / "pdfs"
        for d in (summaries_dir, references_dir, pdfs_dir):
            d.mkdir(parents=True, exist_ok=True)

        pdf_map = {}
        for r in pdf_results:
            if isinstance(r, dict) and r.get("success") and r.get("pdf_path"):
                pdf_map[r.get("paper_id", "")] = r["pdf_path"]

        index_path = output_dir / f"index_{tag}.jsonl"
        persisted = 0
        pdf_count = 0
        refs_count = 0

        s2_headers = _build_s2_headers(api_key, contact_email)

        with index_path.open("w", encoding="utf-8") as idx_f:
            async with httpx.AsyncClient(timeout=60.0) as client:
                for paper in metadata:
                    if not isinstance(paper, dict):
                        continue
                    pid = paper.get("paper_id", "")
                    if not pid:
                        continue
                    safe = _safe_id(pid)

                    extra = paper.get("extra") or {}
                    raw_response = extra.get("_raw_response", {})

                    pdf_src = pdf_map.get(pid)
                    has_pdf = False
                    pdf_rel = None
                    if pdf_src:
                        src_path = Path(pdf_src)
                        if src_path.exists():
                            target = pdfs_dir / f"{safe}.pdf"
                            if src_path.resolve() != target.resolve():
                                try:
                                    shutil.copy2(src_path, target)
                                except Exception as e:
                                    logger.warning("PDF copy %s -> %s failed: %s",
                                                   src_path, target, e)
                            has_pdf = target.exists()
                            if has_pdf:
                                pdf_rel = f"pdfs/{safe}.pdf"
                                pdf_count += 1

                    refs: List[dict] = []
                    if fetch_references:
                        refs = await self._fetch_references(client, paper, s2_headers)
                    refs_path = references_dir / f"{safe}.json"
                    refs_path.write_text(json.dumps({
                        "paper_id": pid,
                        "source": source,
                        "count": len(refs),
                        "references": refs,
                    }, ensure_ascii=False, indent=2), encoding="utf-8")
                    if refs:
                        refs_count += 1

                    summary_path = summaries_dir / f"{safe}.json"
                    summary_doc = {
                        "paper_id": pid,
                        "title": paper.get("title", ""),
                        "abstract": paper.get("abstract", ""),
                        "authors": paper.get("authors", []),
                        "year": paper.get("year"),
                        "doi": paper.get("doi", ""),
                        "venue": paper.get("venue", ""),
                        "source": source,
                        "tag": tag,
                        "is_open_access": paper.get("is_open_access", False),
                        "keywords": paper.get("keywords", []),
                        "pdf_url": paper.get("pdf_url"),
                        "pdf_path": pdf_rel,
                        "references_path": f"references/{safe}.json",
                        "extra": {k: v for k, v in extra.items() if k != "_raw_response"},
                        "raw_response": raw_response,
                    }
                    summary_path.write_text(
                        json.dumps(summary_doc, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    persisted += 1

                    idx_f.write(json.dumps({
                        "paper_id": pid,
                        "title": paper.get("title", ""),
                        "year": paper.get("year"),
                        "doi": paper.get("doi", ""),
                        "source": source,
                        "tag": tag,
                        "summary_path": f"summaries/{safe}.json",
                        "references_path": f"references/{safe}.json",
                        "pdf_path": pdf_rel,
                        "has_pdf": has_pdf,
                        "has_refs": len(refs) > 0,
                        "ref_count": len(refs),
                    }, ensure_ascii=False) + "\n")

        logger.info(
            "PaperSearchPersist[%s]: persisted=%d pdf=%d refs=%d -> %s",
            tag, persisted, pdf_count, refs_count, output_dir,
        )

        return {
            "persisted_count": persisted,
            "pdf_count": pdf_count,
            "references_count": refs_count,
            "index_path": str(index_path),
            "output_dir": str(output_dir),
        }

    async def _fetch_references(
        self,
        client: httpx.AsyncClient,
        paper: dict,
        headers: dict,
    ) -> List[dict]:
        lookup_id = _resolve_s2_lookup_id(paper)
        if not lookup_id:
            return []
        url = f"{S2_API}/paper/{lookup_id}/references"
        params = {"limit": 100, "fields": S2_REF_FIELDS}
        data = await s2_request_with_retry(client, url, params, headers)
        if not data:
            return []
        items = data.get("data") or []
        return [_extract_ref_record(it) for it in items if isinstance(it, dict)]
