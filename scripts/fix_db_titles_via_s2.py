"""Repair DB rows whose persisted title doesn't match the parsed PDF.

For each paper_id whose ``papers.title`` is empty OR whose normalized
fuzzy similarity against the markdown's first H1 is below a threshold,
hit Semantic Scholar (with API key) directly using the H1 as the query
and overwrite the row in-place.

Usage::

    S2_API_KEY=... python3 scripts/fix_db_titles_via_s2.py \\
        --db output/papers.db \\
        --parsed-root output/pdf_kit_parsed_past \\
        [--threshold 0.7] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

NORM_RE = re.compile(r"[^a-z0-9]+")
SECTION_HEADS = {
    "ABSTRACT", "INTRODUCTION", "REFERENCES", "CONCLUSION",
    "ACKNOWLEDGEMENTS", "ACKNOWLEDGMENTS", "ETHICS STATEMENT",
    "REPRODUCIBILITY STATEMENT",
}


def norm(s: str) -> str:
    return NORM_RE.sub(" ", (s or "").lower()).strip()


def md_first_heading(md_path: Path) -> str:
    if not md_path.is_file():
        return ""
    for line in md_path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s.startswith("#"):
            continue
        t = s.lstrip("# ").strip()
        if not t or t.upper() in SECTION_HEADS:
            continue
        return t
    return ""


def add_spaces_to_runon(s: str) -> str:
    """Crude space restoration for ALL-CAPS run-on tokens.

    Helps S2's BM25 to tokenize. We only do this if the heading looks
    run-on (a single 12+ char token of letters/digits).
    """
    s = s.strip()
    if not s:
        return s
    tokens = s.split()
    if len(tokens) > 1 and any(len(t) <= 12 for t in tokens):
        return s
    out = []
    for tok in tokens or [s]:
        if len(tok) >= 12 and tok.isalpha():
            spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", tok)
            if spaced == tok:
                spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", tok)
            out.append(spaced)
        else:
            out.append(tok)
    return " ".join(out)


def load_problems(db_path: str, threshold: float, parsed_root: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT paper_id, title, year FROM papers ORDER BY paper_id"
    ).fetchall()
    conn.close()
    problems = []
    for r in rows:
        pid = r["paper_id"]
        md = parsed_root / pid / f"{pid}.md"
        h1 = md_first_heading(md)
        if not h1:
            continue
        db_title = (r["title"] or "").strip()
        if not db_title:
            problems.append((pid, "", h1, 0.0))
            continue
        sim = difflib.SequenceMatcher(None, norm(db_title), norm(h1)).ratio()
        if sim < threshold:
            problems.append((pid, db_title, h1, sim))
    return problems


_S2_AGENT = None


async def s2_lookup(query: str):
    global _S2_AGENT
    from src.crawler.summary_agents.s2_summary import S2SummaryAgent
    from src.crawler.models import SearchIntent

    if _S2_AGENT is None:
        api_key = os.getenv("S2_API_KEY", "")
        if not api_key:
            raise RuntimeError("S2_API_KEY env var is not set")
        _S2_AGENT = S2SummaryAgent(api_key=api_key)
    res = await _S2_AGENT.fetch(SearchIntent(keywords=[query], max_papers=1))
    return res[0] if res else None


_LLM_CLIENT = None


async def llm_clean_title(folder: Path) -> str:
    """Run the same headings_only LLM consensus as the pipeline does, but
    standalone, so we get a properly word-segmented title for run-on
    PDF text.
    """
    global _LLM_CLIENT
    from src.orchestrator.adapters.title_extractor import (
        TitleExtractorModule,
    )
    pid = folder.name
    md = folder / f"{pid}.md"
    if not md.is_file():
        return ""
    markdown = md.read_text(encoding="utf-8", errors="replace")
    paper = {"paper_id": pid, "markdown": markdown}

    if _LLM_CLIENT is None:
        import yaml as _yaml
        from src.orchestrator.llm_config import UnifiedLLMConfig
        cfg_path = os.environ.get("LLM_CONFIG", "config/llm_config.yaml")
        with open(cfg_path) as f:
            raw = _yaml.safe_load(f)
        llm = UnifiedLLMConfig(
            provider=raw["provider"], api_key=raw["api_key"],
            model=raw["model"], base_url=raw.get("base_url"),
        )
        _LLM_CLIENT_CFG = llm.adapter_config()
        m = TitleExtractorModule({
            **_LLM_CLIENT_CFG,
            "headings_only": True,
            "consensus_n": 3,
            "max_retries": 6,
        })
        _LLM_CLIENT = m._get_llm_client()

    extractor = TitleExtractorModule({
        "llm_client": _LLM_CLIENT,
        "headings_only": True,
        "consensus_n": 3,
        "max_retries": 6,
    })
    out = await extractor.run_agent({"papers": [paper]})
    titles = out.get("titles", [])
    if titles and titles[0].get("status") == "success":
        return titles[0].get("title") or ""
    return ""


def update_paper_row(db_path: str, parse_pid: str, paper_content,
                     dry_run: bool = False) -> dict:
    """Mirror what summary_persist does for ONE paper, but as direct
    UPDATE keyed by parse_pid.
    """
    pc = paper_content
    title = pc.title or ""
    abstract = getattr(pc, "abstract", "") or ""
    year = getattr(pc, "year", 0) or 0
    venue = getattr(pc, "venue", "") or ""
    doi = getattr(pc, "doi", "") or ""
    arxiv_id = getattr(pc, "arxiv_id", "") or ""
    pmid = getattr(pc, "pmid", "") or ""
    citation_count = getattr(pc, "citation_count", -1)
    if citation_count is None:
        citation_count = -1

    if dry_run:
        return {
            "paper_id": parse_pid, "title": title, "year": year,
            "venue": venue, "doi": doi, "dry_run": True,
        }

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "UPDATE papers SET title=?, abstract=?, year=?, venue=?, "
            "doi=?, arxiv_id=?, pmid=?, citation_count=?, updated_at=? "
            "WHERE paper_id=?",
            (title, abstract, year, venue, doi, arxiv_id, pmid,
             citation_count,
             datetime.now(timezone.utc).isoformat(timespec="seconds"),
             parse_pid),
        )
        # keep paper_sources row in sync (single source: s2)
        conn.execute(
            "INSERT OR REPLACE INTO paper_sources "
            "(paper_id, platform, platform_id, raw_metadata, fetched_at) "
            "VALUES (?, 's2', ?, ?, datetime('now'))",
            (parse_pid,
             getattr(pc, "paper_id", "") or "",
             json.dumps(pc.to_dict() if hasattr(pc, "to_dict") else {},
                        ensure_ascii=False)),
        )

        # rewrite authors
        authors = getattr(pc, "authors", []) or []
        if authors:
            conn.execute(
                "DELETE FROM paper_authors WHERE paper_id=?", (parse_pid,)
            )
            for order, name in enumerate(authors):
                if not name:
                    continue
                normname = norm(name)
                conn.execute(
                    "INSERT OR IGNORE INTO authors (name, name_normalized) "
                    "VALUES (?, ?)", (name, normname),
                )
                aid = conn.execute(
                    "SELECT id FROM authors WHERE name_normalized=?",
                    (normname,),
                ).fetchone()[0]
                conn.execute(
                    "INSERT OR REPLACE INTO paper_authors "
                    "(paper_id, author_id, author_order) VALUES (?, ?, ?)",
                    (parse_pid, aid, order),
                )

        conn.commit()
    finally:
        conn.close()

    return {
        "paper_id": parse_pid, "title": title, "year": year,
        "venue": venue, "doi": doi, "rows_updated": cur.rowcount,
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="output/papers.db")
    ap.add_argument("--parsed-root", default="output/pdf_kit_parsed_past")
    ap.add_argument("--threshold", type=float, default=0.7,
                    help="similarity threshold under which a row is rebuilt")
    ap.add_argument("--accept", type=float, default=0.5,
                    help="similarity threshold between S2-returned title "
                         "and MD H1 to accept the lookup")
    ap.add_argument("--dry-run", action="store_true", default=True)
    args = ap.parse_args()

    parsed_root = Path(args.parsed_root)
    if not parsed_root.is_dir():
        logger.error("parsed_root not a dir: %s", parsed_root); return 2

    if not os.getenv("S2_API_KEY"):
        logger.error("S2_API_KEY env var is required"); return 2

    problems = load_problems(args.db, args.threshold, parsed_root)
    logger.info("Found %d papers needing repair (threshold=%.2f)",
                len(problems), args.threshold)

    async def attempt_lookup(pid, query, ref_text, label):
        """Single S2 query + accept/reject. Returns (pc, accept_sim) or (None, reason)."""
        try:
            pc = await s2_lookup(query)
        except Exception as e:
            return None, f"s2_error[{label}]: {e}"
        if pc is None:
            return None, f"no_results[{label}]"
        s2_title = pc.title or ""
        accept_sim = difflib.SequenceMatcher(
            None, norm(s2_title), norm(ref_text)
        ).ratio()
        if accept_sim < args.accept:
            return None, f"low_sim[{label}]={accept_sim:.2f} S2='{s2_title[:60]}'"
        return pc, accept_sim

    fixed = 0
    rejected = []  # (pid, reason)
    for pid, db_title, h1, sim in problems:
        folder = parsed_root / pid
        query1 = add_spaces_to_runon(h1)
        logger.info("[%s] sim=%.2f H1='%s' → S2#1 query='%s'",
                    pid, sim, h1[:60], query1[:80])
        pc, info = await attempt_lookup(pid, query1, h1, "h1")
        await asyncio.sleep(1.1)

        if pc is None:
            # Fallback: clean title via LLM (headings_only consensus), retry S2
            logger.info("[%s] H1 lookup failed (%s); trying LLM-clean title",
                        pid, info)
            try:
                clean = await llm_clean_title(folder)
            except Exception as e:
                logger.warning("[%s] LLM error: %s", pid, e)
                rejected.append((pid, f"llm_error: {e}"))
                continue
            if not clean:
                rejected.append((pid, f"no_llm_title; first={info}"))
                continue
            logger.info("[%s] LLM title='%s' → S2#2", pid, clean)
            pc, info2 = await attempt_lookup(pid, clean, clean, "llm")
            await asyncio.sleep(1.1)
            if pc is None:
                rejected.append((pid, f"{info} | {info2}"))
                continue
            accept_sim = info2
        else:
            accept_sim = info

        out = update_paper_row(args.db, pid, pc, dry_run=args.dry_run)
        fixed += 1
        logger.info("[%s] ✓ updated → '%s' (DOI=%s, year=%s, sim=%.2f)",
                    pid, out["title"][:70], out["doi"], out["year"],
                    accept_sim)

    logger.info("\n=== summary ===")
    logger.info("repaired:  %d", fixed)
    logger.info("rejected:  %d", len(rejected))
    for pid, reason in rejected:
        logger.info("  - %s : %s", pid, reason)
    if args.dry_run:
        logger.info("(dry-run; no DB writes performed)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
