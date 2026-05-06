#!/usr/bin/env python3
import argparse
import glob
import hashlib
import json
import os
import sqlite3
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.base import BaseDatabase
from src.db.schemas.knowledge_store_schema import KNOWLEDGE_STORE_DDL
from src.db.writers.knowledge_store_writer import KnowledgeStoreWriter

DEFAULT_DB_PATH = "output/knowledge_store/knowledge_store.db"
DEFAULT_JSON_PATH = "output/knowledge_store"


def phase1_init_schema(db: BaseDatabase):
    print("[Phase 1] Initializing schema...")
    db.executescript(KNOWLEDGE_STORE_DDL)
    db.commit()
    tables = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    views = db.execute(
        "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name").fetchall()
    triggers = db.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name").fetchall()
    print(f"  Created {len(tables)} tables, {len(views)} views, {len(triggers)} triggers")


def _ensure_idea_id(idea_data: dict) -> str:
    if idea_data.get("id"):
        return idea_data["id"]
    title = idea_data.get("title", "")
    return hashlib.sha256(title.lower().strip().encode()).hexdigest()[:16]


def _ensure_scheduler_idea_id(idea_data: dict) -> str:
    if idea_data.get("idea_id"):
        return idea_data["idea_id"]
    title = idea_data.get("title", "")
    return hashlib.sha256(title.lower().strip().encode()).hexdigest()[:16]


def _float_list_to_blob(vec):
    if vec is None:
        return None
    if isinstance(vec, (bytes, bytearray)):
        return vec
    if isinstance(vec, list):
        return struct.pack(f"{len(vec)}f", *vec)
    return None


def _migrate_knowledge_base(writer: KnowledgeStoreWriter, json_path: str):
    kb_path = os.path.join(json_path, "knowledge_base.json")
    if not os.path.exists(kb_path):
        print("  knowledge_base.json not found, skipping")
        return
    print(f"  Migrating knowledge_base.json...")
    with open(kb_path, "r") as f:
        kb = json.load(f)

    insights = kb.get("insights", [])
    print(f"    insights: {len(insights)}")
    for insight in insights:
        limitations = insight.get("limitations_json", insight.get("limitations", []))
        open_questions = insight.get("open_questions_json", insight.get("open_questions", []))
        components = insight.get("reusable_components_json", insight.get("reusable_components", []))
        assumptions = insight.get("assumed_but_not_proven_json", insight.get("assumed_but_not_proven", []))
        writer.upsert_insight(insight, limitations, open_questions, components, assumptions)

    for seed_type_key in ("analyst_seeds", "connector_seeds", "contrarian_seeds"):
        seeds = kb.get(seed_type_key, [])
        stype = seed_type_key.replace("_seeds", "")
        print(f"    {seed_type_key}: {len(seeds)}")
        for seed in seeds:
            seed["seed_type"] = stype
            writer.upsert_seed(
                seed,
                source_papers=seed.get("source_papers_json", seed.get("source_papers", [])),
                related_insights=seed.get("related_insights_json", seed.get("related_insights", [])),
            )

    clusters = kb.get("clusters", [])
    print(f"    clusters: {len(clusters)}")
    for cluster in clusters:
        writer.upsert_seed_cluster(
            cluster,
            insights=cluster.get("insight_indices_json", cluster.get("insight_indices", [])),
            limitations=cluster.get("common_limitations_json", cluster.get("common_limitations", [])),
            gaps=cluster.get("gaps_json", cluster.get("gaps", [])),
        )

    pairs = kb.get("cross_domain_pairs", [])
    print(f"    cross_domain_pairs: {len(pairs)}")
    for pair in pairs:
        seeds_list = None
        idea_seed = pair.get("idea_seed_json", pair.get("idea_seed"))
        if idea_seed:
            if isinstance(idea_seed, dict):
                seeds_list = [idea_seed]
            elif isinstance(idea_seed, list):
                seeds_list = idea_seed
        writer.upsert_cross_domain_pair(pair, seeds=seeds_list)

    for key in ("replication_problems", "transfer_ideas", "critiques",
                "theory_improvements", "follow_up_ideas", "failure_cases",
                "limitation_extensions", "evidence_items"):
        items = kb.get(key, [])
        print(f"    {key}: {len(items)}")
        for item in items:
            if key == "replication_problems":
                writer.upsert_replication_problem(
                    item, missing_details=item.get("missing_details_json", item.get("missing_details", [])))
            elif key == "transfer_ideas":
                writer.upsert_transfer_idea(
                    item, source_papers=item.get("source_papers_json", item.get("source_papers", [])))
            elif key == "critiques":
                writer.upsert_critique(item)
            elif key == "theory_improvements":
                writer.upsert_theory_improvement(item)
            elif key == "follow_up_ideas":
                writer.upsert_follow_up_idea(item)
            elif key == "failure_cases":
                writer.upsert_failure_case(item)
            elif key == "limitation_extensions":
                writer.upsert_limitation_extension(item)
            elif key == "evidence_items":
                writer.upsert_evidence_item(item)

    for key in ("trends", "meta_gaps", "hypotheses"):
        items = kb.get(key, [])
        print(f"    {key}: {len(items)}")
        for item in items:
            if key == "trends":
                writer.upsert_trend(
                    item,
                    supporting_papers=item.get("supporting_papers_json", item.get("supporting_papers", [])),
                    related_gaps=item.get("related_gaps_json", item.get("related_gaps", [])),
                )
            elif key == "meta_gaps":
                writer.upsert_meta_gap(
                    item, evidence_papers=item.get("evidence_papers_json", item.get("evidence_papers", [])))
            elif key == "hypotheses":
                writer.upsert_hypothesis(
                    item, source_papers=item.get("source_papers_json", item.get("source_papers", [])))


def _migrate_accumulated_ideas(writer: KnowledgeStoreWriter, json_path: str, is_archived: bool = False):
    if is_archived:
        pattern = os.path.join(json_path, "archive", "ideas_*.json")
        files = glob.glob(pattern)
        label = "archived"
    else:
        path = os.path.join(json_path, "accumulated_ideas.json")
        files = [path] if os.path.exists(path) else []
        label = "accumulated"

    total = 0
    for filepath in files:
        print(f"  Migrating {os.path.basename(filepath)}...")
        with open(filepath, "r") as f:
            ideas = json.load(f)
        for idea in ideas:
            idea["id"] = _ensure_idea_id(idea)
            idea["is_archived"] = int(is_archived)
            sp = idea.get("source_papers_json", idea.get("source_papers", []))
            st = idea.get("strengths_json", idea.get("strengths", []))
            wk = idea.get("weaknesses_json", idea.get("weaknesses", []))
            writer.upsert_idea(idea, source_papers=sp, strengths=st, weaknesses=wk)
            total += 1
    print(f"    {label} ideas migrated: {total}")


def _migrate_explorations(writer: KnowledgeStoreWriter, json_path: str):
    path = os.path.join(json_path, "explorations.json")
    if not os.path.exists(path):
        print("  explorations.json not found, skipping")
        return
    print(f"  Migrating explorations.json...")
    with open(path, "r") as f:
        explorations = json.load(f)
    print(f"    explorations: {len(explorations)}")
    for exp in explorations:
        writer.upsert_exploration(
            exp,
            search_queries=exp.get("search_queries_json", exp.get("search_queries", [])),
            found_papers=exp.get("found_papers_json", exp.get("found_papers", [])),
            found_insights=exp.get("found_insights_json", exp.get("found_insights", [])),
            refined_ideas=exp.get("refined_idea_json", exp.get("refined_idea"))
            and [exp.get("refined_idea_json", exp.get("refined_idea"))] or None,
            references_needed=exp.get("references_needed_json", exp.get("references_needed", [])),
            innovation_gaps=exp.get("innovation_gaps_json", exp.get("innovation_gaps", [])),
        )


def _migrate_references(writer: KnowledgeStoreWriter, json_path: str):
    path = os.path.join(json_path, "references.json")
    if not os.path.exists(path):
        print("  references.json not found, skipping")
        return
    print(f"  Migrating references.json...")
    with open(path, "r") as f:
        refs = json.load(f)
    print(f"    references: {len(refs)}")
    for ref in refs:
        writer.upsert_reference(ref)


def _migrate_run_log(writer: KnowledgeStoreWriter, json_path: str):
    path = os.path.join(json_path, "run_log.json")
    if not os.path.exists(path):
        print("  run_log.json not found, skipping")
        return
    print(f"  Migrating run_log.json...")
    with open(path, "r") as f:
        logs = json.load(f)
    print(f"    run_log entries: {len(logs)}")
    for log_entry in logs:
        writer.insert_run_log(log_entry)


def _migrate_meta(writer: KnowledgeStoreWriter, json_path: str):
    path = os.path.join(json_path, "meta.json")
    if not os.path.exists(path):
        print("  meta.json not found, skipping")
        return
    print(f"  Migrating meta.json...")
    with open(path, "r") as f:
        meta = json.load(f)
    for key, value in meta.items():
        writer.upsert_metadata(key, json.dumps(value) if not isinstance(value, str) else value)


def _migrate_vectors(writer: KnowledgeStoreWriter, json_path: str):
    path = os.path.join(json_path, "vector_store_backup.json")
    if not os.path.exists(path):
        print("  vector_store_backup.json not found, skipping")
        return
    print(f"  Migrating vector_store_backup.json...")
    with open(path, "r") as f:
        data = json.load(f)
    count = 0
    for collection, records in data.items():
        for record in records:
            vec_id = record.get("id", "")
            vector = record.get("vector", [])
            payload = record.get("payload", record.get("payload_json", {}))
            if not vec_id:
                continue
            ref_id = ""
            if collection == "ideas":
                ref_id = payload.get("id", "")
            elif collection == "insights":
                ref_id = payload.get("paper_id", "")
            elif collection == "seeds":
                ref_id = str(payload.get("id", ""))
            elif collection == "explorations":
                ref_id = payload.get("idea_id", "")
            writer.db.execute(
                "INSERT OR REPLACE INTO vectors (id, collection, reference_id, vector_blob, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (vec_id, collection, ref_id, _float_list_to_blob(vector),
                 record.get("created_at")))
            count += 1
    print(f"    vectors: {count}")


def phase2_migrate_data(db: BaseDatabase, json_path: str):
    print("[Phase 2] Migrating data...")
    writer = KnowledgeStoreWriter(db)

    _migrate_knowledge_base(writer, json_path)
    db.commit()

    _migrate_accumulated_ideas(writer, json_path, is_archived=False)
    db.commit()

    _migrate_accumulated_ideas(writer, json_path, is_archived=True)
    db.commit()

    _migrate_explorations(writer, json_path)
    db.commit()

    _migrate_references(writer, json_path)
    db.commit()

    _migrate_run_log(writer, json_path)
    db.commit()

    _migrate_meta(writer, json_path)
    db.commit()

    _migrate_vectors(writer, json_path)
    db.commit()


def verify_migration(db: BaseDatabase, json_path: str):
    print("[Verify] Checking migration integrity...")

    expected = {}
    kb_path = os.path.join(json_path, "knowledge_base.json")
    if os.path.exists(kb_path):
        with open(kb_path, "r") as f:
            kb = json.load(f)
        expected["insights"] = len(kb.get("insights", []))
        for seed_key in ("analyst_seeds", "connector_seeds", "contrarian_seeds"):
            key = seed_key.replace("_seeds", "")
            expected[f"seeds_{key}"] = len(kb.get(seed_key, []))
        expected["seed_clusters"] = len(kb.get("clusters", []))
        for k in ("replication_problems", "transfer_ideas", "critiques",
                  "theory_improvements", "follow_up_ideas", "failure_cases",
                  "limitation_extensions", "hypotheses", "evidence_items",
                  "trends", "meta_gaps"):
            expected[k] = len(kb.get(k, []))

    ideas_path = os.path.join(json_path, "accumulated_ideas.json")
    if os.path.exists(ideas_path):
        with open(ideas_path, "r") as f:
            expected["ideas_active"] = len(json.load(f))

    archive_files = glob.glob(os.path.join(json_path, "archive", "ideas_*.json"))
    archived = 0
    for af in archive_files:
        with open(af, "r") as f:
            archived += len(json.load(f))
    if archived:
        expected["ideas_archived"] = archived

    exp_path = os.path.join(json_path, "explorations.json")
    if os.path.exists(exp_path):
        with open(exp_path, "r") as f:
            expected["explorations"] = len(json.load(f))

    refs_path = os.path.join(json_path, "references.json")
    if os.path.exists(refs_path):
        with open(refs_path, "r") as f:
            expected["idea_references"] = len(json.load(f))

    checks = []
    table_map = {
        "insights": "insights",
        "seed_clusters": "seed_clusters",
        "replication_problems": "replication_problems",
        "transfer_ideas": "transfer_ideas",
        "critiques": "critiques",
        "theory_improvements": "theory_improvements",
        "follow_up_ideas": "follow_up_ideas",
        "failure_cases": "failure_cases",
        "limitation_extensions": "limitation_extensions",
        "hypotheses": "hypotheses",
        "evidence_items": "evidence_items",
        "trends": "trends",
        "meta_gaps": "meta_gaps",
        "explorations": "explorations",
        "idea_references": "idea_references",
    }
    for key, table in table_map.items():
        if key in expected:
            actual = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            match = actual == expected[key]
            status = "OK" if match else "MISMATCH"
            checks.append((key, expected[key], actual, status))
            if not match:
                print(f"  {status}: {key} expected={expected[key]} actual={actual}")
            else:
                print(f"  {status}: {key} = {actual}")

    if "ideas_active" in expected or "ideas_archived" in expected:
        active = db.execute("SELECT COUNT(*) FROM ideas WHERE is_archived = 0").fetchone()[0]
        archived_db = db.execute("SELECT COUNT(*) FROM ideas WHERE is_archived = 1").fetchone()[0]
        if "ideas_active" in expected:
            match = active == expected["ideas_active"]
            status = "OK" if match else "MISMATCH"
            checks.append(("ideas_active", expected["ideas_active"], active, status))
            print(f"  {status}: ideas_active expected={expected['ideas_active']} actual={active}")
        if "ideas_archived" in expected:
            match = archived_db == expected["ideas_archived"]
            status = "OK" if match else "MISMATCH"
            checks.append(("ideas_archived", expected["ideas_archived"], archived_db, status))
            print(f"  {status}: ideas_archived expected={expected['ideas_archived']} actual={archived_db}")

    fk_result = db.execute("PRAGMA foreign_key_check").fetchall()
    if fk_result:
        print(f"  FK VIOLATIONS: {len(fk_result)}")
        for v in fk_result[:10]:
            print(f"    {v}")
    else:
        print("  FK check: OK")

    mismatches = [c for c in checks if c[3] == "MISMATCH"]
    if mismatches:
        print(f"\n[Verify] FAILED: {len(mismatches)} mismatches found")
        return False
    print(f"\n[Verify] PASSED: {len(checks)} checks OK")
    return True


def main():
    parser = argparse.ArgumentParser(description="Migrate knowledge_store JSON to SQLite")
    parser.add_argument("--phase", type=int, choices=[1, 2], help="Phase to run (1=init, 2=migrate)")
    parser.add_argument("--verify-only", action="store_true", help="Only run verification")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help="SQLite database path")
    parser.add_argument("--json-path", default=DEFAULT_JSON_PATH, help="JSON source directory")
    args = parser.parse_args()

    if args.verify_only:
        db = BaseDatabase(args.db_path)
        verify_migration(db, args.json_path)
        db.close()
        return

    if args.phase is None:
        db = BaseDatabase(args.db_path)
        phase1_init_schema(db)
        phase2_migrate_data(db, args.json_path)
        verify_migration(db, args.json_path)
        db.close()
    elif args.phase == 1:
        db = BaseDatabase(args.db_path)
        phase1_init_schema(db)
        db.close()
    elif args.phase == 2:
        db = BaseDatabase(args.db_path)
        phase2_migrate_data(db, args.json_path)
        verify_migration(db, args.json_path)
        db.close()


if __name__ == "__main__":
    main()
