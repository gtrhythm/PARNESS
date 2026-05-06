"""Run kg_cross_paper_discover across every paper in the KG.

Pulls the list of papers with units from Neo4j (no papers.db needed).
Resumability: every paper whose :Provenance has ``cross_paper_indexed_at``
is short-circuited unless ``--force`` is passed.

Usage:
    python scripts/discover_cross_paper.py
    python scripts/discover_cross_paper.py --limit 3 --concurrency 1
    python scripts/discover_cross_paper.py --force --papers 267027685,259298603
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


def _load_yaml(path: Path) -> Dict[str, Any]:
    import yaml
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _build_llm_client():
    from src.orchestrator.llm_config import UnifiedLLMConfig
    s = _load_yaml(REPO_ROOT / "config" / "llm_config.yaml")
    if not s.get("api_key"):
        raise SystemExit("config/llm_config.yaml missing api_key")
    return UnifiedLLMConfig(
        provider=s.get("provider", "minimax"),
        api_key=s["api_key"],
        model=s.get("model", "MiniMax-M2.7"),
        base_url=s.get("base_url", "https://api.minimaxi.com/v1"),
    ).prompt_client


def _build_neo4j_config(args) -> Dict[str, Any]:
    kg = _load_yaml(REPO_ROOT / "config" / "kg_config.yaml").get("neo4j") or {}
    cfg = {
        "uri":      args.neo4j_uri or kg.get("uri") or os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        "user":     args.neo4j_user or kg.get("user") or "neo4j",
        "password": args.neo4j_password or kg.get("password") or "",
    }
    embedding_dim = (
        kg.get("embedding_dim")
        or _load_yaml(REPO_ROOT / "config" / "kg_config.yaml").get("embedding", {}).get("dimension")
    )
    if embedding_dim:
        cfg["embedding_dim"] = int(embedding_dim)
    return cfg


def _list_paper_ids_from_kg(neo4j_cfg: Dict[str, Any], force: bool) -> List[str]:
    from src.knowledge_graph.store import KGStore
    store = KGStore(neo4j_cfg)
    try:
        with store._session() as s:
            if force:
                rows = s.run(
                    "MATCH (n:KGNode {source_type: 'paper_unit'}) "
                    "RETURN DISTINCT n.source_id AS pid ORDER BY pid"
                ).data()
            else:
                rows = s.run(
                    "MATCH (n:KGNode {source_type: 'paper_unit'}) "
                    "WITH DISTINCT n.source_id AS pid "
                    "OPTIONAL MATCH (p:Provenance {entity_type: 'paper', entity_id: pid}) "
                    "WITH pid, p.cross_paper_indexed_at AS stamped "
                    "WHERE stamped IS NULL "
                    "RETURN pid ORDER BY pid"
                ).data()
    finally:
        store.close()
    return [r["pid"] for r in rows]


async def _discover_one(
    paper_id: str,
    *,
    adapter_config: Dict[str, Any],
    sem: asyncio.Semaphore,
    log_prefix: str,
    top_k: int,
    min_confidence: float,
    max_evaluations: int,
) -> Dict[str, Any]:
    from src.orchestrator.adapters.kg_cross_paper_discover import (
        KGCrossPaperDiscoverModule,
    )
    async with sem:
        t0 = time.time()
        adapter = KGCrossPaperDiscoverModule(config=adapter_config)
        try:
            res = await adapter.execute({
                "paper_id": paper_id,
                "top_k_per_unit": top_k,
                "min_confidence": min_confidence,
                "max_evaluations": max_evaluations,
            })
            elapsed = time.time() - t0
            print(
                f"{log_prefix} paper_id={paper_id} "
                f"units={res.get('unit_count')} "
                f"cands={res.get('candidate_pair_count')} "
                f"evald={res.get('evaluated_pair_count')} "
                f"edges={res.get('cross_paper_edge_count')} "
                f"llm_calls={res.get('llm_calls')} "
                f"elapsed={elapsed:.1f}s",
                flush=True,
            )
            return {
                "paper_id": paper_id,
                "ok": True,
                "elapsed_s": round(elapsed, 2),
                **{k: res.get(k) for k in (
                    "unit_count", "candidate_pair_count",
                    "evaluated_pair_count", "cross_paper_edge_count",
                    "llm_calls", "errors", "skipped",
                )},
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
    neo4j_cfg = _build_neo4j_config(args)
    paper_ids = _list_paper_ids_from_kg(neo4j_cfg, args.force)

    if args.papers:
        wanted = set(args.papers.split(","))
        paper_ids = [p for p in paper_ids if p in wanted]
    if args.limit:
        paper_ids = paper_ids[: args.limit]

    print(f"about to cross-paper-discover {len(paper_ids)} paper(s) "
          f"(concurrency={args.concurrency}, force={args.force}, "
          f"top_k={args.top_k}, min_conf={args.min_confidence})",
          flush=True)

    if not paper_ids:
        print("nothing to do", flush=True)
        return {"total_papers": 0, "results": []}

    llm_client = _build_llm_client()
    adapter_config: Dict[str, Any] = {
        "neo4j": neo4j_cfg,
        "llm_client": llm_client,
    }

    sem = asyncio.Semaphore(max(1, args.concurrency))

    width = max(1, len(str(len(paper_ids))))
    tasks = [
        _discover_one(
            pid,
            adapter_config=adapter_config,
            sem=sem,
            log_prefix=f"[{i+1:>{width}}/{len(paper_ids)}]",
            top_k=args.top_k,
            min_confidence=args.min_confidence,
            max_evaluations=args.max_evaluations,
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
        "total_units": sum(r.get("unit_count", 0) for r in ok),
        "total_candidates": sum(r.get("candidate_pair_count", 0) for r in ok),
        "total_evaluated": sum(r.get("evaluated_pair_count", 0) for r in ok),
        "total_cross_edges": sum(r.get("cross_paper_edge_count", 0) for r in ok),
        "total_llm_calls": sum(r.get("llm_calls", 0) for r in ok),
        "total_elapsed_s": round(total_elapsed, 2),
        "results": results,
    }

    print(
        "\n=== summary ===\n"
        f"  papers ok / failed   : {summary['ok']} / {summary['failed']}\n"
        f"  candidate pairs      : {summary['total_candidates']}\n"
        f"  pairs evaluated      : {summary['total_evaluated']}\n"
        f"  cross-paper edges    : {summary['total_cross_edges']}\n"
        f"  total LLM calls      : {summary['total_llm_calls']}\n"
        f"  wall                 : {total_elapsed:.1f}s",
        flush=True,
    )
    out_dir = REPO_ROOT / "output" / "kg"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"discover_cross_paper_{int(time.time())}.json"
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"  report: {report_path}", flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0,
                        help="Process at most N papers (0 = all).")
    parser.add_argument("--papers", default="",
                        help="Comma-separated paper_ids — overrides --limit.")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--force", action="store_true",
                        help="Re-discover even for papers already stamped.")
    parser.add_argument("--top-k", type=int, default=8,
                        help="Top-K cross-paper candidates per unit.")
    parser.add_argument("--min-confidence", type=float, default=0.6)
    parser.add_argument("--max-evaluations", type=int, default=10_000,
                        help="Cap on candidate pairs per paper.")
    parser.add_argument("--neo4j-uri", default="")
    parser.add_argument("--neo4j-user", default="")
    parser.add_argument("--neo4j-password", default="")
    args = parser.parse_args()

    asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
