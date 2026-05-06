"""Backfill :Provenance nodes for papers whose units exist but whose
parent Provenance was wiped by the global orphan-sweep race in
``KGStore.delete_source``. Reads paper_text from papers.db (read-only),
computes the canonical paper_text_hash, and MERGEs the Provenance with
all the SOURCED_FROM edges from existing paper_unit nodes.

Idempotent: re-running on already-stamped papers is a no-op.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="")
    parser.add_argument("--db-path", default="output/papers.db")
    args = parser.parse_args()

    from src.knowledge_graph.store import KGStore
    from src.knowledge_graph._external_db import open_readonly
    from src.orchestrator.adapters.paper_intra_index import _paper_text_hash

    store = KGStore({
        "uri": args.neo4j_uri,
        "user": args.neo4j_user,
        "password": args.neo4j_password,
        "embedding_dim": 2560,
    })

    with store._session() as s:
        units_pids = {
            r["sid"]
            for r in s.run(
                "MATCH (n:KGNode {source_type:'paper_unit'}) "
                "RETURN DISTINCT n.source_id AS sid"
            )
        }
        prov_pids = {
            r["eid"]
            for r in s.run(
                "MATCH (p:Provenance {entity_type:'paper'}) "
                "RETURN p.entity_id AS eid"
            )
        }

    missing = sorted(units_pids - prov_pids)
    print(f"papers with units      : {len(units_pids)}")
    print(f"paper Provenances      : {len(prov_pids)}")
    print(f"backfill targets       : {len(missing)}")

    if not missing:
        store.close()
        return 0

    backfilled = 0
    for paper_id in missing:
        try:
            with open_readonly(args.db_path) as conn:
                row = conn.execute(
                    "SELECT title FROM papers WHERE paper_id = ?",
                    (paper_id,),
                ).fetchone()
                title = (row["title"] if row else paper_id) or paper_id

                section_rows = conn.execute(
                    "SELECT id, paper_id, section_order, section_text "
                    "FROM paper_sections WHERE paper_id = ?",
                    (paper_id,),
                ).fetchall()
                sections = [dict(r) for r in section_rows]

            paper_hash = _paper_text_hash(sections)
        except Exception as exc:
            print(f"  {paper_id}: read failed: {exc!r}")
            continue

        with store._session() as s:
            s.run(
                """
                MERGE (p:Provenance {id: $pid})
                ON CREATE SET p.entity_type = 'paper',
                              p.entity_id = $paper_id,
                              p.entity_title = $title,
                              p.created_at = datetime()
                SET p.paper_text_hash = $h, p.updated_at = datetime()
                WITH p
                MATCH (u:KGNode {source_type: 'paper_unit', source_id: $paper_id})
                WHERE NOT (u)-[:SOURCED_FROM]->(p)
                CREATE (u)-[r:SOURCED_FROM {
                    provenance_type: 'paper',
                    provenance_id: $pid,
                    provenance_path: 'paper_unit',
                    evidence_text: '',
                    confidence: 1.0,
                    created_at: datetime()
                }]->(p)
                RETURN count(r) AS edges_added
                """,
                pid=f"paper_{paper_id}",
                paper_id=paper_id,
                title=str(title)[:200],
                h=paper_hash,
            )
        backfilled += 1
        if backfilled % 10 == 0:
            print(f"  backfilled {backfilled} / {len(missing)}")

    print(f"backfilled {backfilled} provenance nodes")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
