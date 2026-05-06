import sqlite3
from typing import Dict, List, Optional


class PapersQuery:

    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def get_paper(self, paper_id: str) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT * FROM papers WHERE paper_id = ?", (paper_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_paper_by_doi(self, doi: str) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT * FROM papers WHERE doi = ?", (doi,)
        ).fetchone()
        return dict(row) if row else None

    def get_paper_by_arxiv(self, arxiv_id: str) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_paper_by_pmid(self, pmid: str) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT * FROM papers WHERE pmid = ?", (pmid,)
        ).fetchone()
        return dict(row) if row else None

    def get_paper_full(self, paper_id: str) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT * FROM v_papers_full WHERE paper_id = ?", (paper_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_paper_with_pdf(self, paper_id: str) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT * FROM v_papers_with_pdf WHERE paper_id = ?", (paper_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_papers(self, source: Optional[str] = None,
                    year: Optional[int] = None,
                    venue: Optional[str] = None,
                    domain_tag: Optional[str] = None,
                    limit: int = 100, offset: int = 0) -> List[Dict]:
        if domain_tag:
            return self._list_by_tag(domain_tag, year, limit, offset)
        clauses = []
        params = []
        if source:
            clauses.append("paper_id IN (SELECT paper_id FROM paper_sources WHERE platform = ?)")
            params.append(source)
        if year:
            clauses.append("year = ?")
            params.append(year)
        if venue:
            clauses.append("venue = ?")
            params.append(venue)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        rows = self.db.execute(
            f"SELECT * FROM papers{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def _list_by_tag(self, tag_code: str, year: Optional[int],
                     limit: int, offset: int) -> List[Dict]:
        params: list = [tag_code]
        extra = ""
        if year:
            extra = " AND p.year = ?"
            params.append(year)
        params.extend([limit, offset])
        rows = self.db.execute(f"""
            SELECT p.* FROM papers p
            JOIN paper_tags pt ON pt.paper_id = p.paper_id
            JOIN taxonomy_tags tt ON tt.id = pt.tag_id
            WHERE tt.tag_code = ?{extra}
            ORDER BY p.created_at DESC LIMIT ? OFFSET ?
        """, params).fetchall()
        return [dict(r) for r in rows]

    def search_papers(self, keyword: str, limit: int = 20) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM papers WHERE title LIKE ? LIMIT ?",
            (f"%{keyword}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_authors(self, paper_id: str) -> List[str]:
        rows = self.db.execute("""
            SELECT a.name FROM paper_authors pa
            JOIN authors a ON a.id = pa.author_id
            WHERE pa.paper_id = ? ORDER BY pa.author_order
        """, (paper_id,)).fetchall()
        return [r[0] for r in rows]

    def get_sources(self, paper_id: str) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM paper_sources WHERE paper_id = ?", (paper_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_tags(self, paper_id: str) -> List[Dict]:
        rows = self.db.execute("""
            SELECT tt.taxonomy_id, tt.tag_code, tt.tag_name,
                   pt.is_primary, pt.confidence, pt.tagged_by
            FROM paper_tags pt
            JOIN taxonomy_tags tt ON tt.id = pt.tag_id
            WHERE pt.paper_id = ?
        """, (paper_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_pdf_download(self, paper_id: str,
                         platform: Optional[str] = None) -> Optional[Dict]:
        if platform:
            row = self.db.execute(
                "SELECT * FROM pdf_downloads WHERE paper_id = ? AND platform = ?",
                (paper_id, platform),
            ).fetchone()
        else:
            row = self.db.execute(
                "SELECT * FROM pdf_downloads WHERE paper_id = ? AND success = 1 LIMIT 1",
                (paper_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_all_pdf_downloads(self, paper_id: str) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM pdf_downloads WHERE paper_id = ?", (paper_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_extraction(self, paper_id: str) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT * FROM pdf_extractions WHERE paper_id = ?", (paper_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_sections(self, paper_id: str) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM paper_sections WHERE paper_id = ? ORDER BY section_order",
            (paper_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_tables(self, paper_id: str) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM paper_tables WHERE paper_id = ? ORDER BY table_order",
            (paper_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_images(self, paper_id: str) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM paper_images WHERE paper_id = ? ORDER BY image_order",
            (paper_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_formulas(self, paper_id: str) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM paper_formulas WHERE paper_id = ? ORDER BY formula_order",
            (paper_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_artifacts(self, paper_id: str) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM paper_artifacts WHERE paper_id = ?", (paper_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_full_text(self, paper_id: str) -> str:
        row = self.db.execute(
            "SELECT full_text FROM pdf_extractions WHERE paper_id = ?",
            (paper_id,),
        ).fetchone()
        return row[0] if row and row[0] else ""

    def get_abstract(self, paper_id: str) -> str:
        row = self.db.execute(
            "SELECT abstract FROM papers WHERE paper_id = ?", (paper_id,)
        ).fetchone()
        return row[0] if row and row[0] else ""

    def count_papers(self, platform: Optional[str] = None) -> int:
        if platform:
            row = self.db.execute("""
                SELECT COUNT(*) FROM papers WHERE paper_id IN
                (SELECT paper_id FROM paper_sources WHERE platform = ?)
            """, (platform,)).fetchone()
        else:
            row = self.db.execute("SELECT COUNT(*) FROM papers").fetchone()
        return row[0] if row else 0

    def count_extractions(self, status: Optional[str] = None) -> int:
        if status:
            row = self.db.execute(
                "SELECT COUNT(*) FROM pdf_extractions WHERE status = ?",
                (status,),
            ).fetchone()
        else:
            row = self.db.execute(
                "SELECT COUNT(*) FROM pdf_extractions"
            ).fetchone()
        return row[0] if row else 0

    def count_pdfs(self, success: Optional[bool] = None) -> int:
        if success is not None:
            row = self.db.execute(
                "SELECT COUNT(DISTINCT paper_id) FROM pdf_downloads WHERE success = ?",
                (1 if success else 0,),
            ).fetchone()
        else:
            row = self.db.execute(
                "SELECT COUNT(DISTINCT paper_id) FROM pdf_downloads"
            ).fetchone()
        return row[0] if row else 0

    def list_taxonomies(self) -> List[Dict]:
        rows = self.db.execute("SELECT * FROM taxonomy ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def list_tags_for_taxonomy(self, taxonomy_id: str) -> List[Dict]:
        rows = self.db.execute(
            "SELECT * FROM taxonomy_tags WHERE taxonomy_id = ? ORDER BY tag_code",
            (taxonomy_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_tag_stats(self) -> List[Dict]:
        rows = self.db.execute("SELECT * FROM v_papers_by_tag").fetchall()
        return [dict(r) for r in rows]

    def get_crawl_jobs(self, status: Optional[str] = None,
                       limit: int = 50) -> List[Dict]:
        if status:
            rows = self.db.execute(
                "SELECT * FROM crawl_jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM crawl_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def papers_without_pdf(self, limit: int = 100) -> List[Dict]:
        rows = self.db.execute("""
            SELECT p.* FROM papers p
            WHERE NOT EXISTS (
                SELECT 1 FROM pdf_downloads pd
                WHERE pd.paper_id = p.paper_id AND pd.success = 1
            )
            ORDER BY p.created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def papers_without_extraction(self, limit: int = 100) -> List[Dict]:
        rows = self.db.execute("""
            SELECT p.* FROM papers p
            WHERE NOT EXISTS (
                SELECT 1 FROM pdf_extractions pe
                WHERE pe.paper_id = p.paper_id AND pe.status = 'success'
            )
            AND EXISTS (
                SELECT 1 FROM pdf_downloads pd
                WHERE pd.paper_id = p.paper_id AND pd.success = 1
            )
            ORDER BY p.created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def search_sections_fts(self, query: str, limit: int = 20) -> List[Dict]:
        rows = self.db.execute("""
            SELECT paper_id, section_title, section_text, page_number
            FROM paper_sections_fts WHERE paper_sections_fts MATCH ?
            LIMIT ?
        """, (query, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_random_with_full_text(self, num_papers: int = 5,
                                  min_full_text_length: int = 200,
                                  max_text_chars: int = 12000) -> List[Dict]:
        rows = self.db.execute(
            """
            SELECT p.paper_id, p.title, p.abstract, p.year, p.venue,
                   p.arxiv_id, pe.full_text,
                   (SELECT pdf_path FROM pdf_downloads
                    WHERE paper_id = p.paper_id AND success = 1 LIMIT 1) AS pdf_path
            FROM papers p
            JOIN pdf_extractions pe ON pe.paper_id = p.paper_id
            WHERE length(pe.full_text) >= ?
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (min_full_text_length, num_papers),
        ).fetchall()
        results = []
        for row in rows:
            full_text = row["full_text"] or ""
            if len(full_text) > max_text_chars:
                full_text = full_text[:max_text_chars]
            results.append({
                "paper_id": row["paper_id"],
                "title": row["title"] or "",
                "abstract": row["abstract"] or "",
                "year": row["year"] or 0,
                "venue": row["venue"] or "",
                "arxiv_id": row["arxiv_id"] or "",
                "pdf_url": "",
                "full_text": full_text,
            })
        return results

    def get_embedding_text(self, paper_id: str, max_chars: int = 8000) -> str:
        meta = self.get_paper(paper_id)
        if not meta:
            return ""
        parts = [meta.get("title", "")]
        if meta.get("abstract"):
            parts.append(meta["abstract"])
        text = self.get_full_text(paper_id)
        if text:
            parts.append(text)
        return "\n\n".join(parts)[:max_chars]
