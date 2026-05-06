import json
import struct
from typing import Any, Dict, List, Optional

from src.db.base import BaseDatabase


def _split_fixed_extra(data: Dict, fixed_keys: set) -> tuple:
    fixed = {}
    extra = {}
    for k, v in data.items():
        if k in fixed_keys:
            fixed[k] = v
        else:
            extra[k] = v
    extra_json = json.dumps(extra, ensure_ascii=False) if extra else "{}"
    return fixed, extra_json


class KnowledgeStoreWriter:
    def __init__(self, db: BaseDatabase):
        self.db = db

    def _delete_children(self, table: str, column: str, parent_id: Any):
        self.db.execute(f"DELETE FROM {table} WHERE {column} = ?", (parent_id,))

    def _bulk_insert(self, table: str, columns: List[str], rows: List[tuple]):
        if not rows:
            return
        placeholders = ", ".join(["?"] * len(columns))
        cols = ", ".join(columns)
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        self.db.executemany(sql, rows)

    _INSIGHT_FIXED = {
        "paper_id", "title", "year", "core_insight", "problem_solved",
        "key_trick", "novelty_signal", "created_at",
        "limitations", "limitations_json",
        "open_questions", "open_questions_json",
        "reusable_components", "reusable_components_json",
        "assumed_but_not_proven", "assumed_but_not_proven_json",
    }

    def upsert_insight(self, insight_data: Dict, limitations: Optional[List[str]] = None,
                       open_questions: Optional[List[str]] = None,
                       components: Optional[List[str]] = None,
                       assumptions: Optional[List[str]] = None):
        pid = insight_data["paper_id"]
        fixed, extra_json = _split_fixed_extra(insight_data, self._INSIGHT_FIXED)
        self.db.execute(
            "INSERT OR REPLACE INTO insights (paper_id, title, year, core_insight, problem_solved, key_trick, novelty_signal, extra_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, fixed.get("title", ""), fixed.get("year", 0),
             fixed.get("core_insight", ""), fixed.get("problem_solved", ""),
             fixed.get("key_trick", ""), fixed.get("novelty_signal", ""),
             extra_json, fixed.get("created_at")))
        for table, items in [
            ("insight_limitations", limitations or []),
            ("insight_open_questions", open_questions or []),
            ("insight_reusable_components", components or []),
            ("insight_assumptions", assumptions or []),
        ]:
            self._delete_children(table, "paper_id", pid)
            col = {"insight_limitations": "limitation", "insight_open_questions": "question",
                   "insight_reusable_components": "component", "insight_assumptions": "assumption"}[table]
            rows = [(pid, item, i) for i, item in enumerate(items)]
            self._bulk_insert(table, ["paper_id", col, "position"], rows)

    def bulk_upsert_insights(self, insights_list: List[Dict]):
        for insight_data in insights_list:
            self.upsert_insight(
                insight_data,
                limitations=insight_data.get("limitations_json", []),
                open_questions=insight_data.get("open_questions_json", []),
                components=insight_data.get("reusable_components_json", []),
                assumptions=insight_data.get("assumed_but_not_proven_json", []),
            )

    _SEED_FIXED = {
        "seed", "seed_type", "rationale", "created_at",
        "source_papers", "source_papers_json",
        "related_insights", "related_insights_json",
    }

    def upsert_seed(self, seed_data: Dict, source_papers: Optional[List[str]] = None,
                    related_insights: Optional[List[str]] = None):
        fixed, extra_json = _split_fixed_extra(seed_data, self._SEED_FIXED)
        cursor = self.db.execute(
            "INSERT OR REPLACE INTO seeds (seed, seed_type, rationale, extra_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (fixed.get("seed", ""), fixed.get("seed_type", ""),
             fixed.get("rationale", ""), extra_json, fixed.get("created_at")))
        seed_id = cursor.lastrowid
        self._delete_children("seed_source_papers", "seed_id", seed_id)
        self._delete_children("seed_related_insights", "seed_id", seed_id)
        if source_papers:
            rows = [(seed_id, pid, i) for i, pid in enumerate(source_papers)]
            self._bulk_insert("seed_source_papers", ["seed_id", "paper_id", "position"], rows)
        if related_insights:
            rows = [(seed_id, ins, i) for i, ins in enumerate(related_insights)]
            self._bulk_insert("seed_related_insights", ["seed_id", "insight", "position"], rows)
        return seed_id

    def upsert_seed_cluster(self, cluster_data: Dict, insights: Optional[List[str]] = None,
                            limitations: Optional[List[str]] = None,
                            gaps: Optional[List[Dict]] = None):
        cursor = self.db.execute(
            "INSERT OR REPLACE INTO seed_clusters (theme, created_at) VALUES (?, ?)",
            (cluster_data.get("theme", ""), cluster_data.get("created_at")))
        cluster_id = cursor.lastrowid
        for table in ["seed_cluster_insights", "seed_cluster_limitations",
                       "seed_cluster_gaps", "cluster_gap_source_papers", "cluster_gap_related_insights"]:
            if table == "seed_cluster_insights":
                self._delete_children(table, "cluster_id", cluster_id)
            elif table == "seed_cluster_limitations":
                self._delete_children(table, "cluster_id", cluster_id)
            elif table == "seed_cluster_gaps":
                self._delete_children(table, "cluster_id", cluster_id)
        if insights:
            rows = [(cluster_id, pid, i) for i, pid in enumerate(insights)]
            self._bulk_insert("seed_cluster_insights", ["cluster_id", "paper_id", "position"], rows)
        if limitations:
            rows = [(cluster_id, lim, i) for i, lim in enumerate(limitations)]
            self._bulk_insert("seed_cluster_limitations", ["cluster_id", "limitation", "position"], rows)
        if gaps:
            for pos, gap in enumerate(gaps):
                cursor2 = self.db.execute(
                    "INSERT INTO seed_cluster_gaps (cluster_id, seed, seed_type, rationale, novelty_signal, position) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (cluster_id, gap.get("seed", ""), gap.get("seed_type", ""),
                     gap.get("rationale", ""), gap.get("novelty_signal", ""), pos))
                gap_id = cursor2.lastrowid
                for spos, sp in enumerate(gap.get("source_papers", [])):
                    self.db.execute(
                        "INSERT INTO cluster_gap_source_papers (gap_id, paper_id, position) VALUES (?, ?, ?)",
                        (gap_id, sp, spos))
                for ipos, ins in enumerate(gap.get("related_insights", [])):
                    self.db.execute(
                        "INSERT INTO cluster_gap_related_insights (gap_id, insight, position) VALUES (?, ?, ?)",
                        (gap_id, ins, ipos))
        return cluster_id

    def upsert_cross_domain_pair(self, pair_data: Dict, seeds: Optional[List[Dict]] = None):
        cursor = self.db.execute(
            "INSERT OR REPLACE INTO cross_domain_pairs "
            "(insight_a_id, insight_b_id, surface_similarity, structural_analogy, transfer_direction, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (pair_data.get("insight_a_id", ""), pair_data.get("insight_b_id", ""),
             pair_data.get("surface_similarity", 0.0), pair_data.get("structural_analogy", ""),
             pair_data.get("transfer_direction", ""), pair_data.get("created_at")))
        pair_id = cursor.lastrowid
        self._delete_children("cross_domain_pair_seeds", "pair_id", pair_id)
        if seeds:
            for seed in seeds:
                cursor2 = self.db.execute(
                    "INSERT INTO cross_domain_pair_seeds (pair_id, seed, seed_type, rationale, novelty_signal) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (pair_id, seed.get("seed", ""), seed.get("seed_type", ""),
                     seed.get("rationale", ""), seed.get("novelty_signal", "")))
                seed_row_id = cursor2.lastrowid
                for spos, sp in enumerate(seed.get("source_papers", [])):
                    self.db.execute(
                        "INSERT INTO cd_pair_seed_source_papers (seed_row_id, paper_id, position) VALUES (?, ?, ?)",
                        (seed_row_id, sp, spos))
                for ipos, ins in enumerate(seed.get("related_insights", [])):
                    self.db.execute(
                        "INSERT INTO cd_pair_seed_related_insights (seed_row_id, insight, position) VALUES (?, ?, ?)",
                        (seed_row_id, ins, ipos))
        return pair_id

    def upsert_replication_problem(self, data: Dict, missing_details: Optional[List[str]] = None):
        pid = data["paper_id"]
        self.db.execute(
            "INSERT OR REPLACE INTO replication_problems "
            "(paper_id, paper_title, claimed_result, reproduction_issue, suggested_experiment, potential_improvement) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (pid, data.get("paper_title", ""), data.get("claimed_result", ""),
             data.get("reproduction_issue", ""), data.get("suggested_experiment", ""),
             data.get("potential_improvement", "")))
        self._delete_children("replication_missing_details", "paper_id", pid)
        if missing_details:
            rows = [(pid, d, i) for i, d in enumerate(missing_details)]
            self._bulk_insert("replication_missing_details", ["paper_id", "detail", "position"], rows)

    def upsert_transfer_idea(self, data: Dict, source_papers: Optional[List[str]] = None):
        mn = data["method_name"]
        self.db.execute(
            "INSERT OR REPLACE INTO transfer_ideas "
            "(method_name, source_domain, target_domain, method_description, transfer_rationale, "
            "adaptation_needed, feasibility_score) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (mn, data.get("source_domain", ""), data.get("target_domain", ""),
             data.get("method_description", ""), data.get("transfer_rationale", ""),
             data.get("adaptation_needed", ""), data.get("feasibility_score", 0.0)))
        self._delete_children("transfer_idea_source_papers", "method_name", mn)
        if source_papers:
            rows = [(mn, pid, i) for i, pid in enumerate(source_papers)]
            self._bulk_insert("transfer_idea_source_papers", ["method_name", "paper_id", "position"], rows)

    def upsert_critique(self, data: Dict):
        self.db.execute(
            "INSERT OR REPLACE INTO critiques "
            "(paper_id, claim, flaw, severity, suggested_improvement, evidence) VALUES (?, ?, ?, ?, ?, ?)",
            (data.get("paper_id", ""), data.get("claim", ""), data.get("flaw", ""),
             data.get("severity", ""), data.get("suggested_improvement", ""), data.get("evidence", "")))

    def upsert_theory_improvement(self, data: Dict):
        self.db.execute(
            "INSERT OR REPLACE INTO theory_improvements "
            "(paper_id, original_assumption, theoretical_issue, proposed_correction, mathematical_sketch, impact_assessment) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (data.get("paper_id", ""), data.get("original_assumption", ""),
             data.get("theoretical_issue", ""), data.get("proposed_correction", ""),
             data.get("mathematical_sketch", ""), data.get("impact_assessment", "")))

    def upsert_trend(self, data: Dict, supporting_papers: Optional[List[str]] = None,
                     related_gaps: Optional[List[str]] = None):
        tn = data["trend_name"]
        self.db.execute(
            "INSERT OR REPLACE INTO trends (trend_name, description, growth_rate) VALUES (?, ?, ?)",
            (tn, data.get("description", ""), data.get("growth_rate", "")))
        self._delete_children("trend_supporting_papers", "trend_name", tn)
        self._delete_children("trend_related_gaps", "trend_name", tn)
        if supporting_papers:
            rows = [(tn, pid, i) for i, pid in enumerate(supporting_papers)]
            self._bulk_insert("trend_supporting_papers", ["trend_name", "paper_id", "position"], rows)
        if related_gaps:
            rows = [(tn, gap, i) for i, gap in enumerate(related_gaps)]
            self._bulk_insert("trend_related_gaps", ["trend_name", "gap", "position"], rows)

    def upsert_meta_gap(self, data: Dict, evidence_papers: Optional[List[str]] = None):
        gd = data["gap_description"]
        self.db.execute(
            "INSERT OR REPLACE INTO meta_gaps (gap_description, domain, opportunity_score) VALUES (?, ?, ?)",
            (gd, data.get("domain", ""), data.get("opportunity_score", 0.0)))
        self._delete_children("meta_gap_evidence_papers", "gap_description", gd)
        if evidence_papers:
            rows = [(gd, pid, i) for i, pid in enumerate(evidence_papers)]
            self._bulk_insert("meta_gap_evidence_papers", ["gap_description", "paper_id", "position"], rows)

    def upsert_follow_up_idea(self, data: Dict):
        self.db.execute(
            "INSERT OR REPLACE INTO follow_up_ideas "
            "(original_paper_id, original_paper_title, future_work_claim, extension_idea, feasibility, "
            "novelty_assessment, required_resources) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (data.get("original_paper_id", ""), data.get("original_paper_title", ""),
             data.get("future_work_claim", ""), data.get("extension_idea", ""),
             data.get("feasibility", ""), data.get("novelty_assessment", ""),
             data.get("required_resources", "")))

    def upsert_failure_case(self, data: Dict):
        self.db.execute(
            "INSERT OR REPLACE INTO failure_cases "
            "(paper_id, paper_title, method_description, failure_scenario, why_it_fails, counter_example, suggested_fix) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (data.get("paper_id", ""), data.get("paper_title", ""),
             data.get("method_description", ""), data.get("failure_scenario", ""),
             data.get("why_it_fails", ""), data.get("counter_example", ""),
             data.get("suggested_fix", "")))

    def upsert_limitation_extension(self, data: Dict):
        self.db.execute(
            "INSERT OR REPLACE INTO limitation_extensions "
            "(paper_id, paper_title, stated_limitation, extension_direction, proposed_approach, "
            "expected_contribution, difficulty) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (data.get("paper_id", ""), data.get("paper_title", ""),
             data.get("stated_limitation", ""), data.get("extension_direction", ""),
             data.get("proposed_approach", ""), data.get("expected_contribution", ""),
             data.get("difficulty", "")))

    def upsert_hypothesis(self, data: Dict, source_papers: Optional[List[str]] = None):
        hid = data["hypothesis_id"]
        self.db.execute(
            "INSERT OR REPLACE INTO hypotheses "
            "(hypothesis_id, statement, rationale, testability, predicted_outcome, required_experiment, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (hid, data.get("statement", ""), data.get("rationale", ""),
             data.get("testability", ""), data.get("predicted_outcome", ""),
             data.get("required_experiment", ""), data.get("confidence", 0.0)))
        self._delete_children("hypothesis_source_papers", "hypothesis_id", hid)
        if source_papers:
            rows = [(hid, pid, i) for i, pid in enumerate(source_papers)]
            self._bulk_insert("hypothesis_source_papers", ["hypothesis_id", "paper_id", "position"], rows)

    def upsert_evidence_item(self, data: Dict):
        self.db.execute(
            "INSERT OR REPLACE INTO evidence_items "
            "(hypothesis_id, paper_id, paper_title, stance, evidence_description, strength, relevance) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (data.get("hypothesis_id", ""), data.get("paper_id", ""),
             data.get("paper_title", ""), data.get("stance", ""),
             data.get("evidence_description", ""), data.get("strength", ""),
             data.get("relevance", 0.0)))

    _IDEA_FIXED = {
        "id", "title", "description", "category", "methodology",
        "expected_results", "required_resources", "risk_analysis",
        "seed_type", "rationale",
        "novelty_score", "feasibility_score", "impact_score",
        "overall_score", "direction_alignment_score",
        "is_archived", "created_at",
        "source_papers", "source_papers_json",
        "strengths", "strengths_json",
        "weaknesses", "weaknesses_json",
    }

    def upsert_idea(self, data: Dict, source_papers: Optional[List[str]] = None,
                    strengths: Optional[List[str]] = None, weaknesses: Optional[List[str]] = None):
        idea_id = data["id"]
        fixed, extra_json = _split_fixed_extra(data, self._IDEA_FIXED)
        self.db.execute(
            "INSERT OR REPLACE INTO ideas "
            "(id, title, description, category, methodology, expected_results, required_resources, "
            "risk_analysis, seed_type, rationale, novelty_score, feasibility_score, impact_score, "
            "overall_score, direction_alignment_score, is_archived, extra_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (idea_id, fixed.get("title", ""), fixed.get("description", ""),
             fixed.get("category", ""), fixed.get("methodology", ""),
             fixed.get("expected_results", ""), fixed.get("required_resources", ""),
             fixed.get("risk_analysis", ""), fixed.get("seed_type", ""),
             fixed.get("rationale", ""), fixed.get("novelty_score", 0.0),
             fixed.get("feasibility_score", 0.0), fixed.get("impact_score", 0.0),
             fixed.get("overall_score", 0.0), fixed.get("direction_alignment_score", 0.0),
             fixed.get("is_archived", 0), extra_json, fixed.get("created_at")))
        self._delete_children("idea_source_papers", "idea_id", idea_id)
        self._delete_children("idea_strengths", "idea_id", idea_id)
        self._delete_children("idea_weaknesses", "idea_id", idea_id)
        if source_papers:
            rows = [(idea_id, pid, i) for i, pid in enumerate(source_papers)]
            self._bulk_insert("idea_source_papers", ["idea_id", "paper_id", "position"], rows)
        if strengths:
            rows = [(idea_id, s, i) for i, s in enumerate(strengths)]
            self._bulk_insert("idea_strengths", ["idea_id", "strength", "position"], rows)
        if weaknesses:
            rows = [(idea_id, w, i) for i, w in enumerate(weaknesses)]
            self._bulk_insert("idea_weaknesses", ["idea_id", "weakness", "position"], rows)

    def bulk_upsert_ideas(self, ideas_list: List[Dict]):
        for idea_data in ideas_list:
            self.upsert_idea(
                idea_data,
                source_papers=idea_data.get("source_papers_json", []),
                strengths=idea_data.get("strengths_json", []),
                weaknesses=idea_data.get("weaknesses_json", []),
            )

    _EXPLORATION_FIXED = {
        "idea_id", "idea_title", "related_work", "novelty_validation",
        "direction_alignment",
        "search_queries", "search_queries_json",
        "found_papers", "found_papers_json",
        "found_insights", "found_insights_json",
        "refined_idea", "refined_idea_json",
        "references_needed", "references_needed_json",
        "innovation_gaps", "innovation_gaps_json",
    }

    def upsert_exploration(self, data: Dict, search_queries: Optional[List[str]] = None,
                           found_papers: Optional[List[Dict]] = None,
                           found_insights: Optional[List[str]] = None,
                           refined_ideas: Optional[List[Dict]] = None,
                           references_needed: Optional[List[str]] = None,
                           innovation_gaps: Optional[List[str]] = None):
        idea_id = data["idea_id"]
        fixed, extra_json = _split_fixed_extra(data, self._EXPLORATION_FIXED)
        self.db.execute(
            "INSERT OR REPLACE INTO explorations "
            "(idea_id, idea_title, related_work, novelty_validation, direction_alignment, extra_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (idea_id, fixed.get("idea_title", ""), fixed.get("related_work", ""),
             fixed.get("novelty_validation", ""), fixed.get("direction_alignment", 0.0),
             extra_json))
        for table in ["exploration_search_queries", "exploration_found_papers",
                       "exploration_found_insights", "exploration_references_needed",
                       "exploration_innovation_gaps"]:
            self._delete_children(table, "idea_id", idea_id)
        self._delete_children("exploration_refined_ideas", "idea_id", idea_id)
        if search_queries:
            rows = [(idea_id, q, i) for i, q in enumerate(search_queries)]
            self._bulk_insert("exploration_search_queries", ["idea_id", "query", "position"], rows)
        if found_papers:
            rows = [(idea_id, p.get("title", ""), p.get("year", 0),
                     p.get("abstract", ""), i) for i, p in enumerate(found_papers)]
            self._bulk_insert("exploration_found_papers",
                              ["idea_id", "title", "year", "abstract", "position"], rows)
        if found_insights:
            rows = [(idea_id, t, i) for i, t in enumerate(found_insights)]
            self._bulk_insert("exploration_found_insights", ["idea_id", "title", "position"], rows)
        if refined_ideas:
            for ri in refined_ideas:
                cursor = self.db.execute(
                    "INSERT INTO exploration_refined_ideas "
                    "(idea_id, title, description, category, methodology, expected_results, "
                    "required_resources, risk_analysis, seed_type, rationale, novelty_score, "
                    "feasibility_score, impact_score, overall_score, direction_alignment_score) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (idea_id, ri.get("title", ""), ri.get("description", ""),
                     ri.get("category", ""), ri.get("methodology", ""),
                     ri.get("expected_results", ""), ri.get("required_resources", ""),
                     ri.get("risk_analysis", ""), ri.get("seed_type", ""),
                     ri.get("rationale", ""), ri.get("novelty_score", 0.0),
                     ri.get("feasibility_score", 0.0), ri.get("impact_score", 0.0),
                     ri.get("overall_score", 0.0), ri.get("direction_alignment_score", 0.0)))
                refined_id = cursor.lastrowid
                for spos, sp in enumerate(ri.get("source_papers", [])):
                    self.db.execute(
                        "INSERT INTO exploration_refined_source_papers (refined_id, paper_id, position) "
                        "VALUES (?, ?, ?)", (refined_id, sp, spos))
                for str_pos, st in enumerate(ri.get("strengths", [])):
                    self.db.execute(
                        "INSERT INTO exploration_refined_strengths (refined_id, strength, position) "
                        "VALUES (?, ?, ?)", (refined_id, st, str_pos))
                for wpos, w in enumerate(ri.get("weaknesses", [])):
                    self.db.execute(
                        "INSERT INTO exploration_refined_weaknesses (refined_id, weakness, position) "
                        "VALUES (?, ?, ?)", (refined_id, w, wpos))
        if references_needed:
            rows = [(idea_id, r, i) for i, r in enumerate(references_needed)]
            self._bulk_insert("exploration_references_needed",
                              ["idea_id", "reference_topic", "position"], rows)
        if innovation_gaps:
            rows = [(idea_id, g, i) for i, g in enumerate(innovation_gaps)]
            self._bulk_insert("exploration_innovation_gaps", ["idea_id", "gap", "position"], rows)

    def upsert_reference(self, data: Dict):
        self.db.execute(
            "INSERT OR REPLACE INTO idea_references "
            "(source_idea_id, target_type, target_id, reference_kind, context, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (data.get("source_idea_id", ""), data.get("target_type", ""),
             data.get("target_id", ""), data.get("reference_kind", ""),
             data.get("context", ""), data.get("confidence", 1.0)))

    def insert_run_log(self, data: Dict):
        self.db.execute(
            "INSERT INTO run_log "
            "(pipeline, direction, new_insights, new_seeds, new_ideas, new_references, "
            "total_insights, total_seeds, total_ideas, papers_crawled, "
            "new_replication_problems, new_transfer_ideas, new_critiques, new_theory_improvements, "
            "new_trends, new_meta_gaps, new_follow_ups, new_failures, new_limitations, "
            "new_hypotheses, new_evidence, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (data.get("pipeline", ""), data.get("direction", ""),
             data.get("new_insights", 0), data.get("new_seeds", 0),
             data.get("new_ideas", 0), data.get("new_references", 0),
             data.get("total_insights", 0), data.get("total_seeds", 0),
             data.get("total_ideas", 0), data.get("papers_crawled", 0),
             data.get("new_replication_problems", 0), data.get("new_transfer_ideas", 0),
             data.get("new_critiques", 0), data.get("new_theory_improvements", 0),
             data.get("new_trends", 0), data.get("new_meta_gaps", 0),
             data.get("new_follow_ups", 0), data.get("new_failures", 0),
             data.get("new_limitations", 0), data.get("new_hypotheses", 0),
             data.get("new_evidence", 0), data.get("created_at")))

    def upsert_metadata(self, key: str, value: str):
        self.db.execute(
            "INSERT OR REPLACE INTO store_metadata (key, value) VALUES (?, ?)",
            (key, value))

    def insert_raw_idea(self, idea: str, source: str, source_type: str = "",
                        extra: Optional[Dict] = None):
        extra_json = json.dumps(extra, ensure_ascii=False) if extra else "{}"
        cursor = self.db.execute(
            "INSERT INTO raw_ideas (idea, source, source_type, extra_json) VALUES (?, ?, ?, ?)",
            (idea, source, source_type, extra_json))
        return cursor.lastrowid

    def bulk_insert_raw_ideas(self, items: List[Dict]):
        for item in items:
            self.insert_raw_idea(
                idea=item.get("idea", ""),
                source=item.get("source", ""),
                source_type=item.get("source_type", ""),
                extra=item.get("extra"),
            )

    def upsert_vector(self, data: Dict):
        vector_blob = data.get("vector_blob")
        if isinstance(vector_blob, list):
            vector_blob = struct.pack(f"{len(vector_blob)}f", *vector_blob)
        self.db.execute(
            "INSERT OR REPLACE INTO vectors (id, collection, reference_id, vector_blob, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (data["id"], data["collection"], data["reference_id"],
             vector_blob, data.get("created_at")))

    def bulk_upsert_vectors(self, vectors_list: List[Dict]):
        for v in vectors_list:
            self.upsert_vector(v)

    _SCHEDULER_IDEA_FIXED = {
        "idea_id", "title", "description", "category", "methodology",
        "expected_results", "required_resources", "risk_analysis",
        "seed_type", "rationale",
        "source_papers", "source_papers_json",
        "tags", "tags_json",
        "paper_count", "insight_count", "seed_count",
    }

    def submit_ideas(self, ideas: List[Dict], batch_id: str = ""):
        from datetime import datetime
        now = datetime.now().isoformat()
        count = 0
        for idea_data in ideas:
            idea_id = idea_data.get("idea_id", "")
            if not idea_id:
                continue
            fixed, extra_json = _split_fixed_extra(idea_data, self._SCHEDULER_IDEA_FIXED)
            self.db.execute(
                "INSERT OR IGNORE INTO scheduler_ideas "
                "(idea_id, title, description, category, methodology, expected_results, "
                "required_resources, risk_analysis, seed_type, rationale, status, best_score, "
                "extra_json, created_at, updated_at, batch_id, paper_count, insight_count, seed_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', 0.0, ?, ?, ?, ?, ?, ?, ?)",
                (idea_id, fixed.get("title", ""), fixed.get("description", ""),
                 fixed.get("category", ""), fixed.get("methodology", ""),
                 fixed.get("expected_results", ""), fixed.get("required_resources", ""),
                 fixed.get("risk_analysis", ""), fixed.get("seed_type", ""),
                 fixed.get("rationale", ""), extra_json, now, now, batch_id,
                 fixed.get("paper_count", 0), fixed.get("insight_count", 0),
                 fixed.get("seed_count", 0)))
            self.db.execute(
                "INSERT OR IGNORE INTO scheduler_evaluation_queue (idea_id) VALUES (?)",
                (idea_id,))
            self._delete_children("scheduler_idea_source_papers", "idea_id", idea_id)
            self._delete_children("scheduler_idea_tags", "idea_id", idea_id)
            source_papers = idea_data.get("source_papers_json", [])
            if source_papers:
                rows = [(idea_id, pid, i) for i, pid in enumerate(source_papers)]
                self._bulk_insert("scheduler_idea_source_papers",
                                  ["idea_id", "paper_id", "position"], rows)
            tags = idea_data.get("tags_json", [])
            if tags:
                rows = [(idea_id, tag) for tag in tags]
                self._bulk_insert("scheduler_idea_tags", ["idea_id", "tag"], rows)
            count += 1
        self.db.execute(
            "INSERT INTO scheduler_history (action, timestamp, batch_id, count) VALUES (?, ?, ?, ?)",
            ("submit", now, batch_id, count))

    def record_evaluations(self, idea_id: str, evaluations: List[Dict]):
        from datetime import datetime
        now = datetime.now().isoformat()
        for eval_data in evaluations:
            cursor = self.db.execute(
                "INSERT INTO scheduler_evaluations "
                "(idea_id, evaluator, novelty_score, feasibility_score, impact_score, overall_score, "
                "recommendation, timestamp, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (idea_id, eval_data.get("evaluator", ""),
                 eval_data.get("novelty_score", 0.0), eval_data.get("feasibility_score", 0.0),
                 eval_data.get("impact_score", 0.0), eval_data.get("overall_score", 0.0),
                 eval_data.get("recommendation", ""), eval_data.get("timestamp", now),
                 eval_data.get("notes", "")))
            eval_id = cursor.lastrowid
            strengths = eval_data.get("strengths_json", [])
            if strengths:
                rows = [(eval_id, s, i) for i, s in enumerate(strengths)]
                self._bulk_insert("scheduler_evaluation_strengths",
                                  ["evaluation_id", "strength", "position"], rows)
            weaknesses = eval_data.get("weaknesses_json", [])
            if weaknesses:
                rows = [(eval_id, w, i) for i, w in enumerate(weaknesses)]
                self._bulk_insert("scheduler_evaluation_weaknesses",
                                  ["evaluation_id", "weakness", "position"], rows)
        best = max((e.get("overall_score", 0.0) for e in evaluations), default=0.0)
        if best >= 7.0:
            status = "accepted"
        elif best >= 5.0:
            status = "evaluated"
        else:
            status = "rejected"
        self.db.execute(
            "UPDATE scheduler_ideas SET status = ?, best_score = ?, updated_at = ? WHERE idea_id = ?",
            (status, best, now, idea_id))
        self.db.execute("DELETE FROM scheduler_evaluation_queue WHERE idea_id = ?", (idea_id,))
        self.db.execute(
            "INSERT INTO scheduler_history (action, timestamp, evaluator, count) VALUES (?, ?, ?, ?)",
            ("evaluate", now, evaluations[0].get("evaluator", "") if evaluations else "",
             len(evaluations)))

    def save_knowledge_base(self, kb_dict: Dict):
        for insight in kb_dict.get("insights", []):
            self.upsert_insight(
                insight,
                limitations=insight.get("limitations_json", []),
                open_questions=insight.get("open_questions_json", []),
                components=insight.get("reusable_components_json", []),
                assumptions=insight.get("assumed_but_not_proven_json", []),
            )
        for seed_type_key in ("analyst_seeds", "connector_seeds", "contrarian_seeds"):
            for seed in kb_dict.get(seed_type_key, []):
                seed["seed_type"] = seed_type_key.replace("_seeds", "")
                self.upsert_seed(
                    seed,
                    source_papers=seed.get("source_papers_json", []),
                    related_insights=seed.get("related_insights_json", []),
                )
        for cluster in kb_dict.get("clusters", []):
            self.upsert_seed_cluster(
                cluster,
                insights=cluster.get("insight_indices_json", []),
                limitations=cluster.get("common_limitations_json", []),
                gaps=cluster.get("gaps_json", []),
            )
        for pair in kb_dict.get("cross_domain_pairs", []):
            self.upsert_cross_domain_pair(pair, seeds=pair.get("idea_seed_json") and [pair["idea_seed_json"]] or None)
        for item in kb_dict.get("replication_problems", []):
            self.upsert_replication_problem(
                item, missing_details=item.get("missing_details_json", []))
        for item in kb_dict.get("transfer_ideas", []):
            self.upsert_transfer_idea(
                item, source_papers=item.get("source_papers_json", []))
        for item in kb_dict.get("critiques", []):
            self.upsert_critique(item)
        for item in kb_dict.get("theory_improvements", []):
            self.upsert_theory_improvement(item)
        for item in kb_dict.get("trends", []):
            self.upsert_trend(
                item,
                supporting_papers=item.get("supporting_papers_json", []),
                related_gaps=item.get("related_gaps_json", []),
            )
        for item in kb_dict.get("meta_gaps", []):
            self.upsert_meta_gap(
                item, evidence_papers=item.get("evidence_papers_json", []))
        for item in kb_dict.get("follow_up_ideas", []):
            self.upsert_follow_up_idea(item)
        for item in kb_dict.get("failure_cases", []):
            self.upsert_failure_case(item)
        for item in kb_dict.get("limitation_extensions", []):
            self.upsert_limitation_extension(item)
        for item in kb_dict.get("hypotheses", []):
            self.upsert_hypothesis(
                item, source_papers=item.get("source_papers_json", []))
        for item in kb_dict.get("evidence_items", []):
            self.upsert_evidence_item(item)
