"""Run paper_intra_index_incremental over every paper in output/papers.db.

Why this exists
---------------
The corpus has ~92 papers and ~70 k paragraph fragments in
``paper_sections``. Earlier per-section indexing burned far too much
LLM. The whole-paper strategy in ``paper_intra_index`` collapses each
paper to one (or rarely a handful of) LLM calls. This script drives
that adapter across the whole corpus with:

* paper-level resumability — uses ``paper_intra_index_incremental`` so
  papers whose text-hash hasn't changed are short-circuited end-to-end
  with no LLM cost. Re-running after a partial failure is free.
* bounded concurrency — defaults to ``--concurrency 4`` so we don't
  blast the MiniMax API.
* per-paper logging + a final JSON report at
  ``output/kg/index_all_papers_<timestamp>.json``.

LLM configuration is loaded from ``config/llm_config.yaml`` (the
project's MiniMax-M2.7 key). Embeddings use whatever
``src.knowledge_graph.embedder.get_embedder()`` resolves — Ollama by
default. The Neo4j connection comes from ``config/kg_config.yaml`` or
the ``--neo4j-uri`` flag.

Usage
-----
    python scripts/index_all_papers.py --concurrency 4

    # Smoke run on 3 papers:
    python scripts/index_all_papers.py --limit 3 --concurrency 1

    # Force re-index even if the hash matches:
    python scripts/index_all_papers.py --force
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _load_llm_settings() -> Dict[str, Any]:
    import yaml
    p = REPO_ROOT / "config" / "llm_config.yaml"
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text()) or {}


def _load_kg_settings() -> Dict[str, Any]:
    import yaml
    p = REPO_ROOT / "config" / "kg_config.yaml"
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text()) or {}


def _build_llm_client():
    from src.orchestrator.llm_config import UnifiedLLMConfig
    s = _load_llm_settings()
    if not s.get("api_key"):
        raise SystemExit("config/llm_config.yaml missing api_key")
    cfg = UnifiedLLMConfig(
        provider=s.get("provider", "minimax"),
        api_key=s["api_key"],
        model=s.get("model", "MiniMax-M2.7"),
        base_url=s.get("base_url", "https://api.minimaxi.com/v1"),
    )
    return cfg.prompt_client


def _build_neo4j_config(args) -> Dict[str, Any]:
    kg = _load_kg_settings().get("neo4j") or {}
    cfg = {
        "uri":      args.neo4j_uri or kg.get("uri") or os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        "user":     args.neo4j_user or kg.get("user") or os.environ.get("NEO4J_USER", "neo4j"),
        "password": args.neo4j_password or kg.get("password") or os.environ.get("NEO4J_PASSWORD", ""),
    }
    embedding_dim = kg.get("embedding_dim") or _load_kg_settings().get("embedding", {}).get("dimension")
    if embedding_dim:
        cfg["embedding_dim"] = int(embedding_dim)
    return cfg


def _list_paper_ids(db_path: str) -> List[str]:
    from src.knowledge_graph._external_db import open_readonly
    with open_readonly(db_path) as conn:
        return [
            row["paper_id"]
            for row in conn.execute(
                "SELECT paper_id FROM papers ORDER BY paper_id"
            ).fetchall()
        ]


async def _index_one_paper(
    paper_id: str,
    *,
    db_path: str,
    adapter_config: Dict[str, Any],
    sem: asyncio.Semaphore,
    force: bool,
    log_prefix: str,
) -> Dict[str, Any]:
    from src.orchestrator.adapters.paper_intra_index_incremental import (
        PaperIntraIndexIncrementalModule,
    )
    async with sem:
        t0 = time.time()
        adapter = PaperIntraIndexIncrementalModule(config=adapter_config)
        try:
            res = await adapter.execute({
                "paper_id": paper_id,
                "db_path": db_path,
                "force": force,
            })
            elapsed = time.time() - t0
            reindex = res.get("reindex_result") or {}
            print(
                f"{log_prefix} paper_id={paper_id} "
                f"drift={res.get('drift')} skipped={res.get('skipped')} "
                f"chunks={reindex.get('chunk_count', 0)} "
                f"units={reindex.get('round1_unit_count', 0)} "
                f"r1_edges={reindex.get('round1_edge_count', 0)} "
                f"r2_edges={reindex.get('round2_edge_count', 0)} "
                f"elapsed={elapsed:.1f}s",
                flush=True,
            )
            return {
                "paper_id": paper_id,
                "ok": True,
                "elapsed_s": round(elapsed, 2),
                "drift": res.get("drift", False),
                "skipped": res.get("skipped", False),
                "chunks": reindex.get("chunk_count", 0),
                "units": reindex.get("round1_unit_count", 0),
                "r1_edges": reindex.get("round1_edge_count", 0),
                "r2_edges": reindex.get("round2_edge_count", 0),
                "same_source_edges": reindex.get("same_source_edge_count", 0),
                "errors": reindex.get("errors") or [],
            }
        except Exception as exc:
            elapsed = time.time() - t0
            print(
                f"{log_prefix} paper_id={paper_id} FAILED elapsed={elapsed:.1f}s: {exc!r}",
                flush=True,
            )
            return {
                "paper_id": paper_id,
                "ok": False,
                "elapsed_s": round(elapsed, 2),
                "error": repr(exc),
            }


async def _run(args) -> Dict[str, Any]:
    db_path = args.db_path
    paper_ids = _list_paper_ids(db_path)
    if args.limit:
        paper_ids = paper_ids[: args.limit]
    if args.papers:
        wanted = set(args.papers.split(","))
        paper_ids = [p for p in paper_ids if p in wanted]

    print(f"about to index {len(paper_ids)} paper(s) "
          f"(concurrency={args.concurrency}, force={args.force})",
          flush=True)

    llm_client = _build_llm_client()
    neo4j_cfg = _build_neo4j_config(args)

    adapter_config: Dict[str, Any] = {
        "neo4j": neo4j_cfg,
        "llm_client": llm_client,
        "min_confidence": args.min_confidence,
        "max_context_tokens": args.max_context_tokens,
    }

    sem = asyncio.Semaphore(max(1, args.concurrency))

    width = max(1, len(str(len(paper_ids))))
    tasks = [
        _index_one_paper(
            pid, db_path=db_path, adapter_config=adapter_config,
            sem=sem, force=args.force,
            log_prefix=f"[{i+1:>{width}}/{len(paper_ids)}]",
        )
        for i, pid in enumerate(paper_ids)
    ]

    t0 = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=False)
    total_elapsed = time.time() - t0

    ok = [r for r in results if r.get("ok")]
    failed = [r for r in results if not r.get("ok")]

    summary = {
        "total_papers": len(paper_ids),
        "ok": len(ok),
        "failed": len(failed),
        "skipped_no_drift": sum(1 for r in ok if r.get("skipped")),
        "drift_indexed": sum(1 for r in ok if r.get("drift")),
        "total_units": sum(r.get("units", 0) for r in ok),
        "total_r1_edges": sum(r.get("r1_edges", 0) for r in ok),
        "total_r2_edges": sum(r.get("r2_edges", 0) for r in ok),
        "total_same_source_edges": sum(r.get("same_source_edges", 0) for r in ok),
        "total_chunks": sum(r.get("chunks", 0) for r in ok),
        "total_elapsed_s": round(total_elapsed, 2),
        "results": results,
    }

    print(
        "\n=== summary ===\n"
        f"  papers: ok={summary['ok']} failed={summary['failed']} "
        f"(skip-no-drift={summary['skipped_no_drift']}, "
        f"reindexed={summary['drift_indexed']})\n"
        f"  units : {summary['total_units']}\n"
        f"  edges : r1={summary['total_r1_edges']} r2={summary['total_r2_edges']} "
        f"same_source={summary['total_same_source_edges']}\n"
        f"  total elapsed: {total_elapsed:.1f}s",
        flush=True,
    )

    out_dir = REPO_ROOT / "output" / "kg"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"index_all_papers_{int(time.time())}.json"
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"  report: {report_path}", flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default="output/papers.db")
    parser.add_argument("--limit", type=int, default=0,
                        help="Index at most N papers (0 = all).")
    parser.add_argument("--papers", default="",
                        help="Comma-separated paper_ids — overrides --limit.")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--force", action="store_true",
                        help="Re-index even if paper_text_hash matches.")
    parser.add_argument("--min-confidence", type=float, default=0.5)
    parser.add_argument("--max-context-tokens", type=int, default=200_000)
    parser.add_argument("--neo4j-uri", default="")
    parser.add_argument("--neo4j-user", default="")
    parser.add_argument("--neo4j-password", default="")
    args = parser.parse_args()

    asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
