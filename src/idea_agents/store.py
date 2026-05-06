import json
import logging
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    AgentKnowledgeBase,
    CompressedInsight,
    IdeaSeed,
    IdeaReference,
    FullIdea,
)

logger = logging.getLogger(__name__)


@dataclass
class ContextBudget:
    max_tokens: int = 6000
    avg_chars_per_token: float = 3.5

    def estimate_tokens(self, text: str) -> int:
        return int(len(text) / self.avg_chars_per_token)

    def chunk_by_budget(
        self,
        items: List[Dict],
        formatter,
        max_tokens_per_chunk: int = None,
    ) -> List[List[Dict]]:
        budget = max_tokens_per_chunk or self.max_tokens
        chunks: List[List[Dict]] = []
        current: List[Dict] = []
        current_tokens = 0

        for item in items:
            text = formatter(item)
            tokens = self.estimate_tokens(text)
            if current and current_tokens + tokens > budget:
                chunks.append(current)
                current = [item]
                current_tokens = tokens
            else:
                current.append(item)
                current_tokens += tokens

        if current:
            chunks.append(current)

        return chunks


@dataclass
class IdeaGroup:
    group_id: str = ""
    ideas: List[Dict] = field(default_factory=list)
    synthesis: str = ""
    theme: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "theme": self.theme,
            "idea_count": len(self.ideas),
            "synthesis": self.synthesis,
        }


class TieredKnowledgeStore:
    HOT_MAX_INSIGHTS = 200
    HOT_MAX_IDEAS = 200
    ARCHIVE_DIR_NAME = "archive"

    def __init__(self, store_dir: str = "output/knowledge_store"):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir = self.store_dir / self.ARCHIVE_DIR_NAME
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.kb_path = self.store_dir / "knowledge_base.json"
        self.ideas_path = self.store_dir / "accumulated_ideas.json"
        self.meta_path = self.store_dir / "meta.json"
        self.run_log_path = self.store_dir / "run_log.json"
        self.explorations_path = self.store_dir / "explorations.json"
        self.budget = ContextBudget()

    def load_kb(self) -> AgentKnowledgeBase:
        if self.kb_path.exists():
            try:
                data = json.loads(self.kb_path.read_text(encoding="utf-8"))
                return AgentKnowledgeBase.from_dict(data)
            except Exception as e:
                logger.warning("Failed to load KB: %s", e)
        return AgentKnowledgeBase()

    def save_kb(self, kb: AgentKnowledgeBase):
        self.kb_path.write_text(
            json.dumps(kb.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_all_ideas(self) -> List[Dict]:
        ideas = []
        if self.ideas_path.exists():
            try:
                ideas = json.loads(self.ideas_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        for arch in sorted(self.archive_dir.glob("ideas_*.json")):
            try:
                archived = json.loads(arch.read_text(encoding="utf-8"))
                ideas.extend(archived)
            except Exception:
                pass

        return ideas

    def load_hot_ideas(self) -> List[Dict]:
        if self.ideas_path.exists():
            try:
                all_ideas = json.loads(self.ideas_path.read_text(encoding="utf-8"))
                return all_ideas[-self.HOT_MAX_IDEAS:]
            except Exception:
                pass
        return []

    def load_hot_insights(self) -> List[Dict]:
        kb = self.load_kb()
        insights = kb.insights
        if len(insights) > self.HOT_MAX_INSIGHTS:
            insights = insights[-self.HOT_MAX_INSIGHTS:]
        return [i.to_dict() for i in insights]

    def save_ideas_with_archive(self, ideas: List[Dict]):
        if len(ideas) <= self.HOT_MAX_IDEAS:
            self.ideas_path.write_text(
                json.dumps(ideas, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return

        hot = ideas[-self.HOT_MAX_IDEAS:]
        cold = ideas[:-self.HOT_MAX_IDEAS]

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        count = len(cold)
        archive_file = self.archive_dir / f"ideas_{ts}_{count}.json"
        archive_file.write_text(
            json.dumps(cold, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Archived %d old ideas → %s", count, archive_file.name)

        self.ideas_path.write_text(
            json.dumps(hot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        meta = self._load_meta()
        meta["total_archived_ideas"] = meta.get("total_archived_ideas", 0) + count
        self._save_meta(meta)

    def merge_insights(
        self,
        existing: List[CompressedInsight],
        new: List[CompressedInsight],
    ) -> List[CompressedInsight]:
        existing_ids = {i.paper_id for i in existing}
        added = [i for i in new if i.paper_id not in existing_ids]
        merged = existing + added
        logger.info("Merge insights: %d + %d → %d", len(existing), len(new), len(merged))
        return merged

    def merge_seeds(
        self,
        existing: List[IdeaSeed],
        new: List[IdeaSeed],
    ) -> List[IdeaSeed]:
        existing_texts = {s.seed.lower().strip() for s in existing}
        added = [s for s in new if s.seed.lower().strip() not in existing_texts]
        return existing + added

    def retrieve_by_keywords(
        self,
        query: str,
        ideas: List[Dict],
        top_k: int = 20,
    ) -> List[Dict]:
        query_words = set(query.lower().split())
        scored = []
        for idea in ideas:
            text = f"{idea.get('title', '')} {idea.get('description', '')} {idea.get('methodology', '')}".lower()
            idea_words = set(text.split())
            overlap = len(query_words & idea_words)
            if overlap > 0:
                scored.append((overlap, idea))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [idea for _, idea in scored[:top_k]]

    def retrieve_by_category(
        self,
        category: str,
        ideas: List[Dict],
        top_k: int = 20,
    ) -> List[Dict]:
        cat_lower = category.lower().strip()
        matched = [i for i in ideas if i.get("category", "").lower() == cat_lower]
        if len(matched) >= top_k:
            return matched[:top_k]
        remaining = top_k - len(matched)
        others = [i for i in ideas if i.get("category", "").lower() != cat_lower]
        return matched + others[:remaining]

    def chunk_ideas(
        self,
        ideas: List[Dict],
        max_tokens_per_chunk: int = 5000,
    ) -> List[List[Dict]]:
        def formatter(idea: Dict) -> str:
            return f"- {idea.get('title', '')}: {idea.get('description', '')[:300]}"

        return self.budget.chunk_by_budget(ideas, formatter, max_tokens_per_chunk)

    def stats(self) -> Dict:
        kb = self.load_kb()
        hot_ideas = self.load_hot_ideas()
        meta = self._load_meta()
        archived = meta.get("total_archived_ideas", 0)

        return {
            "insight_count": len(kb.insights),
            "seed_count": len(kb.all_seeds()),
            "hot_idea_count": len(hot_ideas),
            "archived_idea_count": archived,
            "total_idea_count": len(hot_ideas) + archived,
            "paper_ids": [i.paper_id for i in kb.insights],
            "exploration_count": len(self.load_explorations()),
        }

    def _load_meta(self) -> Dict:
        if self.meta_path.exists():
            try:
                return json.loads(self.meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_meta(self, meta: Dict):
        self.meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save_references(self, refs: List[IdeaReference]):
        """Save reference graph."""
        refs_path = self.store_dir / "references.json"
        existing = []
        if refs_path.exists():
            try:
                existing = json.loads(refs_path.read_text(encoding="utf-8"))
            except: pass
        existing.extend([r.to_dict() for r in refs])
        refs_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_references(self) -> List[IdeaReference]:
        """Load all references."""
        refs_path = self.store_dir / "references.json"
        if not refs_path.exists():
            return []
        try:
            data = json.loads(refs_path.read_text(encoding="utf-8"))
            return [IdeaReference.from_dict(d) for d in data]
        except:
            return []

    def get_idea_lineage(self, idea_id: str) -> Dict:
        """Get full lineage graph for an idea (upstream sources + downstream derivations)."""
        refs = self.load_references()
        upstream = [r for r in refs if r.source_idea_id == idea_id]
        downstream = [r for r in refs if r.target_type == "idea" and r.target_id == idea_id]
        return {"idea_id": idea_id, "upstream": [r.to_dict() for r in upstream], "downstream": [r.to_dict() for r in downstream]}

    def build_rich_idea(self, idea: Dict, refs: List[IdeaReference] = None) -> Dict:
        """Convert a plain idea dict to RichIdea with references attached."""
        if refs is None:
            refs = self.load_references()
        idea_id = hashlib.sha256(idea.get("title", "").lower().strip().encode()).hexdigest()[:16]
        idea_refs = [r for r in refs if r.source_idea_id == idea_id]
        derived = [r.source_idea_id for r in refs if r.target_type == "idea" and r.target_id == idea_id]
        rich = {**idea, "idea_id": idea_id, "references": [r.to_dict() for r in idea_refs], "derived_idea_ids": derived}
        exploration_data = self.load_explorations(idea_id)
        if exploration_data:
            rich["exploration"] = exploration_data[0]
        return rich

    def save_explorations(self, explorations: List[Dict]):
        existing = self.load_explorations()
        merged = self.merge_explorations(existing, explorations)
        self.explorations_path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_explorations(self, idea_id: str = None) -> List[Dict]:
        if not self.explorations_path.exists():
            return []
        try:
            data = json.loads(self.explorations_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if idea_id is not None:
            return [e for e in data if e.get("idea_id") == idea_id]
        return data

    def merge_explorations(self, existing: List[Dict], new: List[Dict]) -> List[Dict]:
        existing_ids = {e.get("idea_id") for e in existing}
        added = [e for e in new if e.get("idea_id") not in existing_ids]
        return existing + added

    def append_run_log(self, entry: Dict):
        logs = []
        if self.run_log_path.exists():
            try:
                logs = json.loads(self.run_log_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        logs.append(entry)
        self.run_log_path.write_text(
            json.dumps(logs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
