"""Quick KG summary for after a corpus indexing run.

Prints node / edge / provenance totals plus per-source-type breakdowns,
and a top-N papers list ranked by unit count. Read-only against Neo4j.

Usage:
    python scripts/kg_summary.py
    python scripts/kg_summary.py --top 20 --neo4j-uri bolt://localhost:7687
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="")
    parser.add_argument("--embedding-dim", type=int, default=2560)
    parser.add_argument("--top", type=int, default=10,
                        help="Show this many highest-unit-count papers.")
    parser.add_argument("--json", action="store_true",
                        help="Emit machine-readable JSON instead of text.")
    args = parser.parse_args()

    from src.knowledge_graph.store import KGStore

    store = KGStore({
        "uri": args.neo4j_uri,
        "user": args.neo4j_user,
        "password": args.neo4j_password,
        "embedding_dim": args.embedding_dim,
    })

    summary: dict = {}
    with store._session() as s:
        summary["totals"] = {
            "kgnode": s.run("MATCH (n:KGNode) RETURN count(n) AS c").single()["c"],
            "provenance": s.run("MATCH (p:Provenance) RETURN count(p) AS c").single()["c"],
            "related_edges": s.run(
                "MATCH ()-[r:RELATED]->() RETURN count(r) AS c"
            ).single()["c"],
            "sourced_from_edges": s.run(
                "MATCH ()-[r:SOURCED_FROM]->() RETURN count(r) AS c"
            ).single()["c"],
        }
        summary["nodes_by_source_type"] = {
            row["t"] or "(null)": row["c"]
            for row in s.run(
                "MATCH (n:KGNode) RETURN n.source_type AS t, count(*) AS c "
                "ORDER BY c DESC"
            )
        }
        summary["paper_unit_with_embedding"] = s.run(
            "MATCH (n:KGNode {source_type: 'paper_unit'}) "
            "WHERE n.embedding IS NOT NULL RETURN count(n) AS c"
        ).single()["c"]
        summary["edges_by_relation"] = {
            (row["rel"] or "(null)"): row["c"]
            for row in s.run(
                "MATCH ()-[r:RELATED]->() "
                "RETURN r.relation AS rel, count(*) AS c ORDER BY c DESC"
            )
        }
        summary["edges_by_discovered_by"] = {
            (row["d"] or "(null)"): row["c"]
            for row in s.run(
                "MATCH ()-[r:RELATED]->() "
                "RETURN r.discovered_by AS d, count(*) AS c ORDER BY c DESC"
            )
        }
        summary["paper_provenances_with_text_hash"] = s.run(
            "MATCH (p:Provenance {entity_type: 'paper'}) "
            "WHERE p.paper_text_hash IS NOT NULL RETURN count(p) AS c"
        ).single()["c"]
        summary["top_papers_by_unit_count"] = [
            {
                "paper_id": row["pid"],
                "unit_count": row["c"],
            }
            for row in s.run(
                "MATCH (n:KGNode {source_type: 'paper_unit'}) "
                "RETURN n.source_id AS pid, count(*) AS c "
                "ORDER BY c DESC LIMIT $top",
                top=args.top,
            )
        ]
        summary["distinct_papers_with_units"] = s.run(
            "MATCH (n:KGNode {source_type: 'paper_unit'}) "
            "RETURN count(DISTINCT n.source_id) AS c"
        ).single()["c"]
    store.close()

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    t = summary["totals"]
    print("=== TOTALS ===")
    print(f"  KGNode             : {t['kgnode']}")
    print(f"  Provenance         : {t['provenance']}")
    print(f"  RELATED edges      : {t['related_edges']}")
    print(f"  SOURCED_FROM edges : {t['sourced_from_edges']}")
    print()
    print("=== KGNode by source_type ===")
    for name, c in summary["nodes_by_source_type"].items():
        print(f"  {name:25s} {c}")
    print()
    pu = summary["nodes_by_source_type"].get("paper_unit", 0)
    print(f"paper_unit with embedding : {summary['paper_unit_with_embedding']} / {pu}")
    print(f"distinct papers w/ units  : {summary['distinct_papers_with_units']}")
    print(f"paper Provenances stamped : {summary['paper_provenances_with_text_hash']}")
    print()
    print("=== :RELATED by relation ===")
    for name, c in summary["edges_by_relation"].items():
        print(f"  {name:25s} {c}")
    print()
    print("=== :RELATED by discovered_by ===")
    for name, c in summary["edges_by_discovered_by"].items():
        print(f"  {name:25s} {c}")
    print()
    print(f"=== top {args.top} papers by unit count ===")
    for row in summary["top_papers_by_unit_count"]:
        print(f"  {row['paper_id']:30s} {row['unit_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
