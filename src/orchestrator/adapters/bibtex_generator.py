import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .base import BaseModule
from src.experiment_agents.persistence import PersistenceHelper

logger = logging.getLogger(__name__)


class BibtexGeneratorModule(BaseModule):
    module_name = "bibtex_generator"

    INPUT_SPEC = {
        "confirmed_references": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "bib_path": {"type": "str"},
        "citation_keys": {"type": "dict"},
        "persistence_info": {"type": "dict"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        confirmed_references = inputs.get("confirmed_references", [])

        deduped = self._deduplicate(confirmed_references)

        db_path = self.config.get("db_path", "output/papers.db")
        deduped = self._enrich_from_db(deduped, db_path)

        citation_keys = {}
        bib_entries = []
        for ref in deduped:
            key, entry = self._generate_bibtex_entry(ref)
            citation_keys[ref.get("paper_id", "")] = key
            bib_entries.append(entry)

        bib_content = "\n\n".join(bib_entries) + "\n" if bib_entries else ""

        output_dir = Path("output/references")
        output_dir.mkdir(parents=True, exist_ok=True)
        bib_path = output_dir / "references.bib"
        PersistenceHelper.write_text(bib_path, bib_content)

        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir, {"references": "references.bib"}
        )

        logger.info(
            "[BibtexGenerator] Generated %d entries -> %s",
            len(bib_entries), bib_path,
        )

        return {
            "bib_path": str(bib_path),
            "citation_keys": citation_keys,
            "persistence_info": persistence_info,
        }

    @staticmethod
    def _deduplicate(refs: List[Dict]) -> List[Dict]:
        seen = set()
        unique = []
        for r in refs:
            pid = r.get("paper_id", "")
            if pid and pid not in seen:
                seen.add(pid)
                unique.append(r)
            elif not pid:
                unique.append(r)
        return unique

    def _enrich_from_db(self, refs: List[Dict], db_path: str) -> List[Dict]:
        if not Path(db_path).exists():
            return refs

        pids = [r.get("paper_id", "") for r in refs if r.get("paper_id")]
        if not pids:
            return refs

        try:
            from src.db.base import BaseDatabase

            db = BaseDatabase(db_path)
            try:
                enriched = {}
                for pid in pids:
                    row = db.fetchone(
                        "SELECT paper_id, title, abstract, year, venue, doi "
                        "FROM papers WHERE paper_id = ?",
                        (pid,),
                    )
                    if row:
                        enriched[pid] = dict(row)
                for r in refs:
                    pid = r.get("paper_id", "")
                    if pid in enriched:
                        db_row = enriched[pid]
                        for field in ("title", "abstract", "year", "venue", "doi"):
                            if not r.get(field) and db_row.get(field):
                                r[field] = db_row[field]
                return refs
            finally:
                db.close()
        except Exception as e:
            logger.warning("[BibtexGenerator] DB enrich failed: %s", e)
            return refs

    @staticmethod
    def _generate_bibtex_entry(ref: Dict) -> Tuple[str, str]:
        title = ref.get("title", "untitled")
        year = ref.get("year", "0000")
        authors = ref.get("authors", "unknown")

        if authors and authors != "unknown":
            first_author = (
                authors.split(",")[0]
                .split(" and ")[0]
                .strip()
                .split()[-1]
                .lower()
            )
        else:
            first_author = "unknown"

        first_word = (
            title.split()[0].lower().strip(".,;:") if title.split() else "untitled"
        )
        key = f"{first_author}{year}{first_word}"

        venue = ref.get("venue", "")
        entry_type = "inproceedings" if venue else "article"

        lines = [f"@{entry_type}{{{key},"]
        lines.append(f"  title = {{{title}}},")
        lines.append(f"  author = {{{authors}}},")
        lines.append(f"  year = {{{year}}},")
        if venue:
            lines.append(f"  booktitle = {{{venue}}},")
        if ref.get("doi"):
            lines.append(f"  doi = {{{ref['doi']}}},")
        lines.append("}")

        return key, "\n".join(lines)
