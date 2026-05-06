"""Snapshot the Neo4j KG into a single JSON-Lines file (no Neo4j stop
required, no APOC required). Captures every :KGNode + :Provenance plus
every :RELATED and :SOURCED_FROM edge, with all properties.

This is a *logical* backup — re-imports would need a small loader, but
it's enough to inspect or roll back if a later pass corrupts the graph.

Usage:
    python scripts/backup_kg.py
    python scripts/backup_kg.py --out output/kg/backup_pre_cross_paper.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _serialize_value(v):
    # neo4j datetimes / dates show up as DateTime objects; coerce them
    # to ISO strings so json.dumps survives them.
    if hasattr(v, "iso_format"):
        return v.iso_format()
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _entity_props(entity):
    """Pull properties off a neo4j Node or Relationship without relying
    on dict(entity) (which fails on Relationship in some driver
    versions)."""
    out = {}
    for k in entity.keys():
        out[k] = _serialize_value(entity[k])
    return out


def _node_props(rec):
    return _entity_props(rec["n"])


def _rel_props(rec):
    return _entity_props(rec["r"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--node-batch", type=int, default=2000)
    args = parser.parse_args()

    out_path = Path(args.out) if args.out else (
        REPO_ROOT / "output" / "kg" / f"backup_{int(time.time())}.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    from src.knowledge_graph.store import KGStore

    store = KGStore({
        "uri": args.neo4j_uri,
        "user": args.neo4j_user,
        "password": args.neo4j_password,
        "embedding_dim": 2560,
    })

    counts = {"KGNode": 0, "Provenance": 0, "RELATED": 0, "SOURCED_FROM": 0}

    with open(out_path, "w", encoding="utf-8") as fp:
        # ---- nodes ----
        with store._session() as s:
            for label in ("KGNode", "Provenance"):
                # Stream in pages so a 100k-node DB doesn't OOM.
                skip = 0
                while True:
                    rows = s.run(
                        f"MATCH (n:{label}) RETURN n SKIP $skip LIMIT $lim",
                        skip=skip, lim=args.node_batch,
                    ).data()
                    if not rows:
                        break
                    for rec in rows:
                        fp.write(json.dumps({
                            "type": "node",
                            "label": label,
                            "props": _node_props(rec),
                        }, ensure_ascii=False) + "\n")
                    counts[label] += len(rows)
                    skip += args.node_batch
                    print(f"  {label}: {counts[label]} written", flush=True)

        # ---- edges ----
        with store._session() as s:
            for rel_type in ("RELATED", "SOURCED_FROM"):
                skip = 0
                while True:
                    rows = s.run(
                        f"MATCH (a)-[r:{rel_type}]->(b) "
                        f"RETURN a.id AS src, b.id AS tgt, "
                        f"       properties(r) AS props "
                        f"SKIP $skip LIMIT $lim",
                        skip=skip, lim=args.node_batch,
                    ).data()
                    if not rows:
                        break
                    for rec in rows:
                        props = {
                            k: _serialize_value(v)
                            for k, v in (rec["props"] or {}).items()
                        }
                        fp.write(json.dumps({
                            "type": "edge",
                            "rel_type": rel_type,
                            "src": rec["src"],
                            "tgt": rec["tgt"],
                            "props": props,
                        }, ensure_ascii=False) + "\n")
                    counts[rel_type] += len(rows)
                    skip += args.node_batch
                    print(f"  :{rel_type}: {counts[rel_type]} written",
                          flush=True)

    store.close()

    print()
    print(f"backup → {out_path}")
    print(f"  KGNode             : {counts['KGNode']}")
    print(f"  Provenance         : {counts['Provenance']}")
    print(f"  :RELATED edges     : {counts['RELATED']}")
    print(f"  :SOURCED_FROM edges: {counts['SOURCED_FROM']}")
    print(f"  size: {out_path.stat().st_size / 1024 / 1024:.1f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
