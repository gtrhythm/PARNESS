import asyncio
import json
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from .models import IdeaRecord, IdeaStatus, EvaluationReport

logger = logging.getLogger(__name__)


class IdeaScheduler:
    def __init__(self, store_dir: str = "output/idea_scheduler"):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.ideas_path = self.store_dir / "ideas.json"
        self.queue_path = self.store_dir / "evaluation_queue.json"
        self.history_path = self.store_dir / "history.json"
        self.stats_path = self.store_dir / "stats.json"
        self._lock = asyncio.Lock()

    async def submit_ideas(
        self,
        ideas: List[Dict],
        batch_id: str = "",
        paper_count: int = 0,
        insight_count: int = 0,
        seed_count: int = 0,
    ) -> List[IdeaRecord]:
        async with self._lock:
            existing = self._load_ideas()
            existing_titles = {r.title.lower().strip() for r in existing}

            now = datetime.utcnow().isoformat()
            new_records = []
            for idea_data in ideas:
                title = idea_data.get("title", "")
                if not title or title.lower().strip() in existing_titles:
                    continue

                record = IdeaRecord(
                    idea_id=hashlib.sha256(title.lower().strip().encode()).hexdigest()[:16],
                    title=title,
                    description=idea_data.get("description", ""),
                    category=idea_data.get("category", ""),
                    methodology=idea_data.get("methodology", ""),
                    expected_results=idea_data.get("expected_results", ""),
                    required_resources=idea_data.get("required_resources", ""),
                    risk_analysis=idea_data.get("risk_analysis", ""),
                    source_papers=idea_data.get("source_papers", []),
                    seed_type=idea_data.get("seed_type", ""),
                    rationale=idea_data.get("rationale", ""),
                    status=IdeaStatus.GENERATED,
                    created_at=now,
                    updated_at=now,
                    batch_id=batch_id,
                    paper_count=paper_count,
                    insight_count=insight_count,
                    seed_count=seed_count,
                    tags=idea_data.get("tags", []),
                )
                new_records.append(record)
                existing_titles.add(title.lower().strip())

            existing.extend(new_records)
            self._save_ideas(existing)

            self._enqueue([r.idea_id for r in new_records])

            self._append_history({
                "action": "submit",
                "batch_id": batch_id,
                "count": len(new_records),
                "timestamp": now,
            })

            logger.info("Scheduler: submitted %d new ideas (total: %d)", len(new_records), len(existing))
            return new_records

    async def get_evaluation_queue(self) -> List[IdeaRecord]:
        async with self._lock:
            ideas = self._load_ideas()
            queue_ids = self._load_queue()
            queued = [i for i in ideas if i.idea_id in queue_ids and i.status == IdeaStatus.GENERATED]
            return queued

    async def mark_evaluating(self, idea_ids: List[str]):
        async with self._lock:
            ideas = self._load_ideas()
            now = datetime.utcnow().isoformat()
            for idea in ideas:
                if idea.idea_id in idea_ids:
                    idea.status = IdeaStatus.EVALUATING
                    idea.updated_at = now
            self._save_ideas(ideas)

    async def record_evaluations(
        self,
        evaluations: Dict[str, Dict],
        evaluator: str = "critic_agent",
    ):
        async with self._lock:
            ideas = self._load_ideas()
            now = datetime.utcnow().isoformat()
            queue_ids = set(self._load_queue())

            for idea in ideas:
                if idea.idea_id not in evaluations:
                    continue

                ev_data = evaluations[idea.idea_id]
                report = EvaluationReport(
                    evaluator=evaluator,
                    novelty_score=ev_data.get("novelty_score", 0.0),
                    feasibility_score=ev_data.get("feasibility_score", 0.0),
                    impact_score=ev_data.get("impact_score", 0.0),
                    overall_score=ev_data.get("overall_score", 0.0),
                    strengths=ev_data.get("strengths", []),
                    weaknesses=ev_data.get("weaknesses", []),
                    recommendation=ev_data.get("recommendation", ""),
                    timestamp=now,
                    notes=ev_data.get("notes", ""),
                )
                idea.evaluations.append(report)
                idea.best_score = max(idea.best_score, report.overall_score)
                idea.updated_at = now

                if report.overall_score >= 7.0:
                    idea.status = IdeaStatus.ACCEPTED
                elif report.overall_score >= 5.0:
                    idea.status = IdeaStatus.EVALUATED
                else:
                    idea.status = IdeaStatus.REJECTED

                queue_ids.discard(idea.idea_id)

            self._save_ideas(ideas)
            self._save_queue(list(queue_ids))

            self._append_history({
                "action": "evaluate",
                "evaluator": evaluator,
                "count": len(evaluations),
                "timestamp": now,
            })

            logger.info("Scheduler: recorded %d evaluations", len(evaluations))

    async def get_ideas_by_status(self, status: IdeaStatus) -> List[IdeaRecord]:
        async with self._lock:
            ideas = self._load_ideas()
            return [i for i in ideas if i.status == status]

    async def get_top_ideas(self, top_k: int = 20) -> List[IdeaRecord]:
        async with self._lock:
            ideas = self._load_ideas()
            scored = [i for i in ideas if i.best_score > 0]
            scored.sort(key=lambda x: x.best_score, reverse=True)
            return scored[:top_k]

    async def get_all_ideas(self) -> List[IdeaRecord]:
        async with self._lock:
            return self._load_ideas()

    async def get_statistics(self) -> Dict[str, Any]:
        async with self._lock:
            ideas = self._load_ideas()

            status_counts = {}
            for status in IdeaStatus:
                status_counts[status.value] = 0
            for idea in ideas:
                status_counts[idea.status.value] += 1

            scored = [i.best_score for i in ideas if i.best_score > 0]
            avg_score = sum(scored) / len(scored) if scored else 0.0

            return {
                "total_ideas": len(ideas),
                "status_distribution": status_counts,
                "average_score": round(avg_score, 2),
                "max_score": max(scored) if scored else 0.0,
                "evaluated_count": len(scored),
                "accepted_count": status_counts.get("accepted", 0),
                "rejected_count": status_counts.get("rejected", 0),
            }

    def _load_ideas(self) -> List[IdeaRecord]:
        if self.ideas_path.exists():
            try:
                data = json.loads(self.ideas_path.read_text(encoding="utf-8"))
                return [IdeaRecord.from_dict(d) for d in data]
            except Exception:
                pass
        return []

    def _save_ideas(self, ideas: List[IdeaRecord]):
        self.ideas_path.write_text(
            json.dumps([i.to_dict() for i in ideas], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_queue(self) -> List[str]:
        if self.queue_path.exists():
            try:
                return json.loads(self.queue_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save_queue(self, ids: List[str]):
        self.queue_path.write_text(
            json.dumps(ids, indent=2), encoding="utf-8"
        )

    def _enqueue(self, idea_ids: List[str]):
        existing = self._load_queue()
        existing.extend(idea_ids)
        self._save_queue(existing)

    def _append_history(self, entry: Dict):
        history = []
        if self.history_path.exists():
            try:
                history = json.loads(self.history_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        history.append(entry)
        self.history_path.write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
        )
