import json
import sqlite3
from typing import Any, Dict, List, Optional


def _merge_extra(row_dict: Dict) -> Dict:
    extra_raw = row_dict.pop("extra_json", None)
    if extra_raw:
        try:
            extra = json.loads(extra_raw)
            for k, v in extra.items():
                if k not in row_dict:
                    row_dict[k] = v
        except (json.JSONDecodeError, TypeError):
            pass
    return row_dict


class InsightQuery:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def get_by_id(self, paper_id: str) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT * FROM v_insights_full WHERE paper_id = ?", (paper_id,)).fetchone()
        return _merge_extra(dict(row)) if row else None

    def list_all(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM v_insights_full ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)).fetchall()
        return [_merge_extra(dict(r)) for r in rows]

    def filter_by_year(self, year: int) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM v_insights_full WHERE year = ? ORDER BY paper_id",
            (year,)).fetchall()
        return [_merge_extra(dict(r)) for r in rows]

    def search_by_keyword(self, keyword: str, limit: int = 20) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM v_insights_full WHERE core_insight LIKE ? OR title LIKE ? LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", limit)).fetchall()
        return [_merge_extra(dict(r)) for r in rows]

    def get_with_related(self, paper_id: str) -> Optional[Dict]:
        insight = self.get_by_id(paper_id)
        if not insight:
            return None
        seeds = self.db.execute(
            "SELECT s.* FROM seeds s "
            "JOIN seed_source_papers ssp ON ssp.seed_id = s.id "
            "WHERE ssp.paper_id = ?", (paper_id,)).fetchall()
        insight["related_seeds"] = [_merge_extra(dict(s)) for s in seeds]
        return insight


class IdeaQuery:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def get_by_id(self, idea_id: str) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT * FROM v_ideas_full WHERE id = ?", (idea_id,)).fetchone()
        return _merge_extra(dict(row)) if row else None

    def get_by_title(self, title: str) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT * FROM v_ideas_full WHERE LOWER(TRIM(title)) = LOWER(TRIM(?))",
            (title,)).fetchone()
        return _merge_extra(dict(row)) if row else None

    def list_all(self, is_archived: bool = False, limit: int = 100,
                 offset: int = 0) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM v_ideas_full WHERE is_archived = ? ORDER BY overall_score DESC LIMIT ? OFFSET ?",
            (int(is_archived), limit, offset)).fetchall()
        return [_merge_extra(dict(r)) for r in rows]

    def filter_by_category(self, category: str) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM v_ideas_full WHERE category = ? ORDER BY overall_score DESC",
            (category,)).fetchall()
        return [_merge_extra(dict(r)) for r in rows]

    def filter_by_seed_type(self, seed_type: str) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM v_ideas_full WHERE seed_type = ? ORDER BY overall_score DESC",
            (seed_type,)).fetchall()
        return [_merge_extra(dict(r)) for r in rows]

    def search_by_keyword(self, keyword: str, limit: int = 20) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM v_ideas_full WHERE title LIKE ? OR description LIKE ? OR methodology LIKE ? LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", limit)).fetchall()
        return [_merge_extra(dict(r)) for r in rows]

    def get_top_by_score(self, n: int = 20) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM v_ideas_full WHERE is_archived = 0 ORDER BY overall_score DESC LIMIT ?",
            (n,)).fetchall()
        return [_merge_extra(dict(r)) for r in rows]

    def get_with_source_papers(self, idea_id: str) -> Optional[Dict]:
        return self.get_by_id(idea_id)

    def get_with_exploration(self, idea_id: str) -> Optional[Dict]:
        idea = self.get_by_id(idea_id)
        if not idea:
            return None
        exploration = self.db.execute(
            "SELECT * FROM v_explorations_full WHERE idea_id = ?", (idea_id,)).fetchone()
        if exploration:
            idea["exploration"] = _merge_extra(dict(exploration))
        return idea


class SeedQuery:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def get_by_id(self, seed_id: int) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT * FROM v_seeds_full WHERE id = ?", (seed_id,)).fetchone()
        return _merge_extra(dict(row)) if row else None

    def list_by_type(self, seed_type: str) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM v_seeds_full WHERE seed_type = ? ORDER BY id",
            (seed_type,)).fetchall()
        return [_merge_extra(dict(r)) for r in rows]

    def get_with_source_papers(self, seed_id: int) -> Optional[Dict]:
        return self.get_by_id(seed_id)


class RawIdeaQuery:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def get_by_id(self, raw_idea_id: int) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT * FROM raw_ideas WHERE id = ?", (raw_idea_id,)).fetchone()
        return _merge_extra(dict(row)) if row else None

    def list_all(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM raw_ideas ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)).fetchall()
        return [_merge_extra(dict(r)) for r in rows]

    def filter_by_source_type(self, source_type: str) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM raw_ideas WHERE source_type = ? ORDER BY created_at DESC",
            (source_type,)).fetchall()
        return [_merge_extra(dict(r)) for r in rows]

    def search_by_keyword(self, keyword: str, limit: int = 20) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM raw_ideas WHERE idea LIKE ? OR source LIKE ? LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", limit)).fetchall()
        return [_merge_extra(dict(r)) for r in rows]

    def count(self) -> int:
        row = self.db.execute("SELECT COUNT(*) FROM raw_ideas").fetchone()
        return row[0] if row else 0


class SchedulerIdeaQuery:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def get_by_id(self, idea_id: str) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT * FROM v_scheduler_ideas_full WHERE idea_id = ?", (idea_id,)).fetchone()
        return _merge_extra(dict(row)) if row else None

    def list_by_status(self, status: str) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM v_scheduler_ideas_full WHERE status = ? ORDER BY best_score DESC",
            (status,)).fetchall()
        return [_merge_extra(dict(r)) for r in rows]

    def list_queued(self) -> List[str]:
        rows = self.db.execute(
            "SELECT idea_id FROM scheduler_evaluation_queue ORDER BY rowid").fetchall()
        return [r[0] for r in rows]

    def get_with_evaluations(self, idea_id: str) -> Optional[Dict]:
        idea = self.get_by_id(idea_id)
        if not idea:
            return None
        rows = self.db.execute(
            "SELECT * FROM v_scheduler_evaluations_full WHERE idea_id = ? ORDER BY timestamp",
            (idea_id,)).fetchall()
        idea["evaluations"] = [_merge_extra(dict(r)) for r in rows]
        return idea

    def get_best_ideas(self, n: int = 20) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM v_scheduler_ideas_full ORDER BY best_score DESC LIMIT ?",
            (n,)).fetchall()
        return [_merge_extra(dict(r)) for r in rows]
