import json
import sqlite3
from typing import Dict, List, Optional


class PapersWriter:

    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def upsert_paper(self, paper: Dict):
        doi = paper.get("doi", "")
        if doi:
            existing = self.db.execute(
                "SELECT paper_id FROM papers WHERE doi = ? AND paper_id != ?",
                (doi, paper.get("paper_id", "")),
            ).fetchone()
            if existing:
                return
        self.db.execute("""
            INSERT INTO papers (paper_id, title, abstract, year, month,
                published_date, doi, pmid, arxiv_id, venue, venue_type,
                volume, issue, pages, publisher, comment, language,
                citation_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(paper_id) DO UPDATE SET
                title = COALESCE(NULLIF(excluded.title, ''), papers.title),
                abstract = COALESCE(NULLIF(excluded.abstract, ''), papers.abstract),
                year = CASE WHEN excluded.year > 0 THEN excluded.year ELSE papers.year END,
                doi = COALESCE(NULLIF(excluded.doi, ''), papers.doi),
                pmid = COALESCE(NULLIF(excluded.pmid, ''), papers.pmid),
                arxiv_id = COALESCE(NULLIF(excluded.arxiv_id, ''), papers.arxiv_id),
                venue = COALESCE(NULLIF(excluded.venue, ''), papers.venue),
                venue_type = COALESCE(NULLIF(excluded.venue_type, ''), papers.venue_type),
                comment = COALESCE(NULLIF(excluded.comment, ''), papers.comment),
                citation_count = CASE WHEN excluded.citation_count >= 0
                    THEN excluded.citation_count ELSE papers.citation_count END,
                updated_at = datetime('now')
        """, (
            paper.get("paper_id", ""),
            paper.get("title", ""),
            paper.get("abstract", ""),
            paper.get("year", 0),
            paper.get("month", ""),
            paper.get("published_date", ""),
            paper.get("doi", ""),
            paper.get("pmid", ""),
            paper.get("arxiv_id", ""),
            paper.get("venue", ""),
            paper.get("venue_type", ""),
            paper.get("volume", ""),
            paper.get("issue", ""),
            paper.get("pages", ""),
            paper.get("publisher", ""),
            paper.get("comment", ""),
            paper.get("language", "en"),
            paper.get("citation_count", -1),
        ))

    def _get_or_create_author(self, name: str) -> int:
        normalized = name.strip().lower()
        row = self.db.execute(
            "SELECT id FROM authors WHERE name_normalized = ?", (normalized,)
        ).fetchone()
        if row:
            return row[0]
        cur = self.db.execute(
            "INSERT INTO authors (name, name_normalized, orcid) VALUES (?, ?, ?)",
            (name, normalized, ""),
        )
        return cur.lastrowid

    def upsert_paper_authors(self, paper_id: str, authors: List[str]):
        self.db.execute(
            "DELETE FROM paper_authors WHERE paper_id = ?", (paper_id,)
        )
        for order, name in enumerate(authors):
            aid = self._get_or_create_author(name)
            self.db.execute(
                "INSERT INTO paper_authors (paper_id, author_id, author_order, affiliation) "
                "VALUES (?, ?, ?, '')",
                (paper_id, aid, order),
            )

    def upsert_paper_source(self, paper_id: str, source: Dict):
        self.db.execute("""
            INSERT INTO paper_sources (paper_id, platform, platform_id, url,
                pdf_url, pdf_path, is_open_access, oa_license, raw_metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id, platform) DO UPDATE SET
                url = COALESCE(NULLIF(excluded.url, ''), paper_sources.url),
                pdf_url = COALESCE(NULLIF(excluded.pdf_url, ''), paper_sources.pdf_url),
                pdf_path = COALESCE(NULLIF(excluded.pdf_path, ''), paper_sources.pdf_path),
                is_open_access = CASE WHEN excluded.is_open_access > 0
                    THEN excluded.is_open_access ELSE paper_sources.is_open_access END,
                raw_metadata = excluded.raw_metadata,
                fetched_at = datetime('now')
        """, (
            paper_id,
            source.get("platform", ""),
            source.get("platform_id", ""),
            source.get("url", ""),
            source.get("pdf_url", ""),
            source.get("pdf_path", ""),
            source.get("is_open_access", 0),
            source.get("oa_license", ""),
            json.dumps(source.get("raw_metadata", {}), ensure_ascii=False),
        ))

    def upsert_taxonomy(self, taxonomy_id: str, name: str,
                        description: str = "", is_system: int = 0):
        self.db.execute("""
            INSERT INTO taxonomy (id, name, description, is_system)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET name = excluded.name
        """, (taxonomy_id, name, description, is_system))

    def _get_or_create_tag(self, taxonomy_id: str, tag_code: str,
                           tag_name: str, parent_tag_id: Optional[int] = None) -> int:
        row = self.db.execute(
            "SELECT id FROM taxonomy_tags WHERE taxonomy_id = ? AND tag_code = ?",
            (taxonomy_id, tag_code),
        ).fetchone()
        if row:
            return row[0]
        cur = self.db.execute(
            "INSERT INTO taxonomy_tags (taxonomy_id, tag_code, tag_name, parent_tag_id, description) "
            "VALUES (?, ?, ?, ?, '')",
            (taxonomy_id, tag_code, tag_name, parent_tag_id),
        )
        return cur.lastrowid

    def upsert_paper_tag(self, paper_id: str, taxonomy_id: str,
                         tag_code: str, tag_name: str,
                         is_primary: int = 0, tagged_by: str = "source",
                         confidence: float = 1.0):
        tag_id = self._get_or_create_tag(taxonomy_id, tag_code, tag_name)
        self.db.execute(
            "INSERT INTO paper_tags (paper_id, tag_id, is_primary, confidence, tagged_by) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(paper_id, tag_id) DO UPDATE SET "
            "is_primary = CASE WHEN excluded.is_primary > 0 THEN excluded.is_primary "
            "ELSE paper_tags.is_primary END, "
            "confidence = excluded.confidence",
            (paper_id, tag_id, is_primary, confidence, tagged_by),
        )

    def upsert_paper_tags_batch(self, paper_id: str, taxonomy_id: str,
                                tags: List[Dict], tagged_by: str = "source"):
        for tag in tags:
            self.upsert_paper_tag(
                paper_id=paper_id,
                taxonomy_id=taxonomy_id,
                tag_code=tag.get("code", ""),
                tag_name=tag.get("name", tag.get("code", "")),
                is_primary=tag.get("is_primary", 0),
                tagged_by=tagged_by,
            )

    def upsert_pdf_download(self, paper_id: str, download: Dict):
        self.db.execute("""
            INSERT INTO pdf_downloads (paper_id, platform, pdf_url, pdf_path,
                file_size, file_hash, success, error, download_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id, platform) DO UPDATE SET
                pdf_url = excluded.pdf_url,
                pdf_path = excluded.pdf_path,
                file_size = excluded.file_size,
                file_hash = excluded.file_hash,
                success = excluded.success,
                error = excluded.error,
                download_time_ms = excluded.download_time_ms,
                downloaded_at = datetime('now')
        """, (
            paper_id,
            download.get("platform", ""),
            download.get("pdf_url", ""),
            download.get("pdf_path", ""),
            download.get("file_size", 0),
            download.get("file_hash", ""),
            download.get("success", 0),
            download.get("error", ""),
            download.get("download_time_ms", 0),
        ))

    def upsert_pdf_extraction(self, paper_id: str, extraction: Dict):
        self.db.execute("""
            INSERT INTO pdf_extractions (paper_id, status, engine, page_count,
                full_text, extraction_time_ms, error,
                text_json_path, sections_json_path, tables_json_path,
                images_json_path, formulas_json_path,
                images_dir, figures_dir, markdown_path, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(paper_id) DO UPDATE SET
                status = excluded.status,
                engine = COALESCE(NULLIF(excluded.engine, ''), pdf_extractions.engine),
                page_count = CASE WHEN excluded.page_count > 0
                    THEN excluded.page_count ELSE pdf_extractions.page_count END,
                full_text = COALESCE(NULLIF(excluded.full_text, ''), pdf_extractions.full_text),
                extraction_time_ms = CASE WHEN excluded.extraction_time_ms > 0
                    THEN excluded.extraction_time_ms ELSE pdf_extractions.extraction_time_ms END,
                error = excluded.error,
                text_json_path = COALESCE(NULLIF(excluded.text_json_path, ''), pdf_extractions.text_json_path),
                sections_json_path = COALESCE(NULLIF(excluded.sections_json_path, ''), pdf_extractions.sections_json_path),
                tables_json_path = COALESCE(NULLIF(excluded.tables_json_path, ''), pdf_extractions.tables_json_path),
                images_json_path = COALESCE(NULLIF(excluded.images_json_path, ''), pdf_extractions.images_json_path),
                formulas_json_path = COALESCE(NULLIF(excluded.formulas_json_path, ''), pdf_extractions.formulas_json_path),
                images_dir = COALESCE(NULLIF(excluded.images_dir, ''), pdf_extractions.images_dir),
                figures_dir = COALESCE(NULLIF(excluded.figures_dir, ''), pdf_extractions.figures_dir),
                markdown_path = COALESCE(NULLIF(excluded.markdown_path, ''), pdf_extractions.markdown_path),
                updated_at = datetime('now')
        """, (
            paper_id,
            extraction.get("status", "pending"),
            extraction.get("engine", ""),
            extraction.get("page_count", 0),
            extraction.get("full_text", ""),
            extraction.get("extraction_time_ms", 0),
            extraction.get("error", ""),
            extraction.get("text_json_path", ""),
            extraction.get("sections_json_path", ""),
            extraction.get("tables_json_path", ""),
            extraction.get("images_json_path", ""),
            extraction.get("formulas_json_path", ""),
            extraction.get("images_dir", ""),
            extraction.get("figures_dir", ""),
            extraction.get("markdown_path", ""),
        ))

    def bulk_insert_sections(self, paper_id: str, sections: List[Dict]):
        self.db.execute("DELETE FROM paper_sections WHERE paper_id = ?", (paper_id,))
        if not sections:
            return
        self.db.executemany(
            "INSERT INTO paper_sections "
            "(paper_id, section_order, section_title, section_text, page_number, section_type) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (paper_id, i,
                 s.get("title", ""), s.get("text", ""),
                 s.get("page"), s.get("section_type", "body"))
                for i, s in enumerate(sections)
            ],
        )

    def bulk_insert_tables(self, paper_id: str, tables: List[Dict]):
        self.db.execute("DELETE FROM paper_tables WHERE paper_id = ?", (paper_id,))
        if not tables:
            return
        self.db.executemany(
            "INSERT INTO paper_tables (paper_id, table_order, content, page_number, caption) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (paper_id, i, t.get("content", ""), t.get("page", 0), t.get("caption", ""))
                for i, t in enumerate(tables)
            ],
        )

    def bulk_insert_images(self, paper_id: str, images: List[Dict]):
        self.db.execute("DELETE FROM paper_images WHERE paper_id = ?", (paper_id,))
        if not images:
            return
        rows = []
        for i, img in enumerate(images):
            bbox = img.get("bbox", {})
            if isinstance(bbox, list) and len(bbox) >= 4:
                bx1, by1, bx2, by2 = bbox[0], bbox[1], bbox[2], bbox[3]
            elif isinstance(bbox, dict):
                bx1 = bbox.get("x1")
                by1 = bbox.get("y1")
                bx2 = bbox.get("x2")
                by2 = bbox.get("y2")
            else:
                bx1 = by1 = bx2 = by2 = None
            rows.append((
                paper_id, i, img.get("path", ""), img.get("page", 0),
                img.get("caption", ""), bx1, by1, bx2, by2,
            ))
        self.db.executemany(
            "INSERT INTO paper_images "
            "(paper_id, image_order, file_path, page_number, caption, "
            "bbox_x1, bbox_y1, bbox_x2, bbox_y2) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows,
        )

    def bulk_insert_formulas(self, paper_id: str, formulas: List[Dict]):
        self.db.execute("DELETE FROM paper_formulas WHERE paper_id = ?", (paper_id,))
        if not formulas:
            return
        self.db.executemany(
            "INSERT INTO paper_formulas (paper_id, formula_order, content, page_number, latex) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (paper_id, i, f.get("content", ""), f.get("page", 0), f.get("latex", ""))
                for i, f in enumerate(formulas)
            ],
        )

    def save_extraction_full(self, paper_id: str, extraction: Dict,
                             sections: List[Dict], tables: List[Dict],
                             images: List[Dict], formulas: List[Dict]):
        self.upsert_pdf_extraction(paper_id, extraction)
        self.bulk_insert_sections(paper_id, sections)
        self.bulk_insert_tables(paper_id, tables)
        self.bulk_insert_images(paper_id, images)
        self.bulk_insert_formulas(paper_id, formulas)

    def upsert_artifact(self, paper_id: str, artifact_type: str,
                        file_path: str, file_size: int = 0,
                        file_hash: str = "", metadata: Dict = None):
        self.db.execute("""
            INSERT INTO paper_artifacts (paper_id, artifact_type, file_path,
                file_size, file_hash, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id, artifact_type) DO UPDATE SET
                file_path = excluded.file_path,
                file_size = excluded.file_size,
                file_hash = excluded.file_hash,
                metadata = excluded.metadata
        """, (
            paper_id, artifact_type, file_path, file_size, file_hash,
            json.dumps(metadata or {}, ensure_ascii=False),
        ))

    def upsert_crawl_job(self, job: Dict) -> int:
        if job.get("id"):
            self.db.execute("""
                UPDATE crawl_jobs SET status=?, papers_found=?, papers_new=?,
                    pdfs_downloaded=?, pdfs_failed=?, error=?,
                    completed_at=COALESCE(?, completed_at)
                WHERE id=?
            """, (
                job.get("status", "pending"),
                job.get("papers_found", 0),
                job.get("papers_new", 0),
                job.get("pdfs_downloaded", 0),
                job.get("pdfs_failed", 0),
                job.get("error", ""),
                job.get("completed_at"),
                job["id"],
            ))
            return job["id"]
        cur = self.db.execute("""
            INSERT INTO crawl_jobs (job_type, platform, domain, query,
                year_from, year_to, status, papers_found, papers_new,
                pdfs_downloaded, pdfs_failed, error, started_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job.get("job_type", ""),
            job.get("platform", ""),
            job.get("domain", ""),
            job.get("query", ""),
            job.get("year_from", 0),
            job.get("year_to", 0),
            job.get("status", "pending"),
            job.get("papers_found", 0),
            job.get("papers_new", 0),
            job.get("pdfs_downloaded", 0),
            job.get("pdfs_failed", 0),
            job.get("error", ""),
            job.get("started_at"),
        ))
        return cur.lastrowid

    def save_paper_from_summary(self, paper: Dict, platform: str):
        with self.db:
            self.upsert_paper(paper)
            authors = paper.get("authors", [])
            if authors:
                self.upsert_paper_authors(paper["paper_id"], authors)
            source_info = {
                "platform": platform,
                "platform_id": paper.get("platform_id", paper.get("paper_id", "")),
                "url": paper.get("url", paper.get("abs_url", "")),
                "pdf_url": paper.get("pdf_url", ""),
                "pdf_path": paper.get("pdf_path", ""),
                "is_open_access": 1 if paper.get("is_open_access") else 0,
                "oa_license": paper.get("oa_license", ""),
                "raw_metadata": paper.get("raw_metadata", {}),
            }
            self.upsert_paper_source(paper["paper_id"], source_info)
            categories = paper.get("categories", [])
            if categories:
                for cat in categories:
                    is_primary = 1 if cat == paper.get("primary_category", "") else 0
                    self.upsert_paper_tag(
                        paper_id=paper["paper_id"],
                        taxonomy_id="arxiv_cat" if "." in str(cat) else "keyword",
                        tag_code=str(cat),
                        tag_name=str(cat),
                        is_primary=is_primary,
                    )
            keywords = paper.get("keywords", [])
            if keywords:
                for kw in keywords:
                    self.upsert_paper_tag(
                        paper_id=paper["paper_id"],
                        taxonomy_id="keyword",
                        tag_code=str(kw),
                        tag_name=str(kw),
                    )

    def save_pdf_result(self, paper_id: str, platform: str,
                        pdf_result: Dict, extraction: Optional[Dict] = None,
                        sections: Optional[List[Dict]] = None,
                        tables: Optional[List[Dict]] = None,
                        images: Optional[List[Dict]] = None,
                        formulas: Optional[List[Dict]] = None):
        with self.db:
            self.upsert_pdf_download(paper_id, {
                "platform": platform,
                "pdf_url": pdf_result.get("pdf_url", ""),
                "pdf_path": pdf_result.get("pdf_path", ""),
                "file_size": pdf_result.get("file_size", 0),
                "file_hash": pdf_result.get("file_hash", ""),
                "success": 1 if pdf_result.get("success") else 0,
                "error": pdf_result.get("error", ""),
                "download_time_ms": pdf_result.get("download_time_ms", 0),
            })
            if extraction:
                self.save_extraction_full(
                    paper_id, extraction,
                    sections or [], tables or [],
                    images or [], formulas or [],
                )
