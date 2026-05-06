PAPERS_DDL = """
-- ============================================================
-- papers.db — 跨学科论文统一存储
-- ============================================================

CREATE TABLE IF NOT EXISTS papers (
    paper_id        TEXT PRIMARY KEY,
    title           TEXT NOT NULL DEFAULT '',
    abstract        TEXT DEFAULT '',
    year            INTEGER DEFAULT 0,
    month           TEXT DEFAULT '',
    published_date  TEXT DEFAULT '',
    doi             TEXT DEFAULT '',
    pmid            TEXT DEFAULT '',
    arxiv_id        TEXT DEFAULT '',
    venue           TEXT DEFAULT '',
    venue_type      TEXT DEFAULT '',
    volume          TEXT DEFAULT '',
    issue           TEXT DEFAULT '',
    pages           TEXT DEFAULT '',
    publisher       TEXT DEFAULT '',
    comment         TEXT DEFAULT '',
    language        TEXT DEFAULT 'en',
    citation_count  INTEGER DEFAULT -1,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_doi
    ON papers(doi) WHERE doi IS NOT NULL AND doi != '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_pmid
    ON papers(pmid) WHERE pmid IS NOT NULL AND pmid != '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_arxiv
    ON papers(arxiv_id) WHERE arxiv_id IS NOT NULL AND arxiv_id != '';
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
CREATE INDEX IF NOT EXISTS idx_papers_venue
    ON papers(venue) WHERE venue IS NOT NULL AND venue != '';

-- ============================================================
-- authors
-- ============================================================
CREATE TABLE IF NOT EXISTS authors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    name_normalized TEXT NOT NULL UNIQUE,
    orcid           TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS paper_authors (
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    author_id       INTEGER NOT NULL REFERENCES authors(id),
    author_order    INTEGER NOT NULL,
    affiliation     TEXT DEFAULT '',
    PRIMARY KEY (paper_id, author_id, author_order)
);
CREATE INDEX IF NOT EXISTS idx_pa_paper ON paper_authors(paper_id);
CREATE INDEX IF NOT EXISTS idx_pa_author ON paper_authors(author_id);

-- ============================================================
-- paper_sources (multi-platform tracking)
-- ============================================================
CREATE TABLE IF NOT EXISTS paper_sources (
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    platform        TEXT NOT NULL,
    platform_id     TEXT NOT NULL DEFAULT '',
    url             TEXT DEFAULT '',
    pdf_url         TEXT DEFAULT '',
    pdf_path        TEXT DEFAULT '',
    is_open_access  INTEGER DEFAULT 0,
    oa_license      TEXT DEFAULT '',
    raw_metadata    TEXT DEFAULT '{}',
    fetched_at      TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (paper_id, platform)
);
CREATE INDEX IF NOT EXISTS idx_ps_platform ON paper_sources(platform);
CREATE INDEX IF NOT EXISTS idx_ps_oa ON paper_sources(is_open_access);

-- ============================================================
-- taxonomy (flexible classification)
-- ============================================================
CREATE TABLE IF NOT EXISTS taxonomy (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    is_system       INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS taxonomy_tags (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    taxonomy_id     TEXT NOT NULL REFERENCES taxonomy(id) ON DELETE CASCADE,
    tag_code        TEXT NOT NULL,
    tag_name        TEXT NOT NULL,
    parent_tag_id   INTEGER,
    description     TEXT DEFAULT '',
    FOREIGN KEY (parent_tag_id) REFERENCES taxonomy_tags(id),
    UNIQUE(taxonomy_id, tag_code)
);
CREATE INDEX IF NOT EXISTS idx_tt_taxonomy ON taxonomy_tags(taxonomy_id);
CREATE INDEX IF NOT EXISTS idx_tt_parent ON taxonomy_tags(parent_tag_id);

CREATE TABLE IF NOT EXISTS paper_tags (
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    tag_id          INTEGER NOT NULL REFERENCES taxonomy_tags(id) ON DELETE CASCADE,
    is_primary      INTEGER DEFAULT 0,
    confidence      REAL DEFAULT 1.0,
    tagged_by       TEXT DEFAULT 'source',
    PRIMARY KEY (paper_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_pt_tag ON paper_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_pt_primary
    ON paper_tags(is_primary) WHERE is_primary = 1;

-- ============================================================
-- pdf_downloads (PDFAgent writes)
-- ============================================================
CREATE TABLE IF NOT EXISTS pdf_downloads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    platform        TEXT NOT NULL,
    pdf_url         TEXT NOT NULL,
    pdf_path        TEXT DEFAULT '',
    file_size       INTEGER DEFAULT 0,
    file_hash       TEXT DEFAULT '',
    success         INTEGER NOT NULL DEFAULT 0,
    error           TEXT DEFAULT '',
    download_time_ms INTEGER DEFAULT 0,
    downloaded_at   TEXT DEFAULT (datetime('now')),
    UNIQUE(paper_id, platform)
);
CREATE INDEX IF NOT EXISTS idx_pd_success ON pdf_downloads(success);
CREATE INDEX IF NOT EXISTS idx_pd_platform ON pdf_downloads(platform);

-- ============================================================
-- pdf_extractions
-- ============================================================
CREATE TABLE IF NOT EXISTS pdf_extractions (
    paper_id        TEXT PRIMARY KEY REFERENCES papers(paper_id),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'extracting', 'success', 'failed')),
    engine          TEXT DEFAULT '',
    page_count      INTEGER DEFAULT 0,
    full_text       TEXT DEFAULT '',
    extraction_time_ms INTEGER DEFAULT 0,
    error           TEXT DEFAULT '',
    text_json_path      TEXT DEFAULT '',
    sections_json_path  TEXT DEFAULT '',
    tables_json_path    TEXT DEFAULT '',
    images_json_path    TEXT DEFAULT '',
    formulas_json_path  TEXT DEFAULT '',
    images_dir          TEXT DEFAULT '',
    figures_dir         TEXT DEFAULT '',
    markdown_path       TEXT DEFAULT '',
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pext_status ON pdf_extractions(status);

-- ============================================================
-- extraction sub-tables
-- ============================================================
CREATE TABLE IF NOT EXISTS paper_sections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id        TEXT NOT NULL REFERENCES pdf_extractions(paper_id) ON DELETE CASCADE,
    section_order   INTEGER NOT NULL,
    section_title   TEXT NOT NULL DEFAULT '',
    section_text    TEXT NOT NULL DEFAULT '',
    page_number     INTEGER,
    section_type    TEXT DEFAULT 'body'
);
CREATE INDEX IF NOT EXISTS idx_psec_paper ON paper_sections(paper_id, section_order);

CREATE TABLE IF NOT EXISTS paper_tables (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id        TEXT NOT NULL REFERENCES pdf_extractions(paper_id) ON DELETE CASCADE,
    table_order     INTEGER NOT NULL,
    content         TEXT NOT NULL DEFAULT '',
    page_number     INTEGER DEFAULT 0,
    caption         TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS paper_images (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id        TEXT NOT NULL REFERENCES pdf_extractions(paper_id) ON DELETE CASCADE,
    image_order     INTEGER NOT NULL,
    file_path       TEXT DEFAULT '',
    page_number     INTEGER DEFAULT 0,
    caption         TEXT DEFAULT '',
    bbox_x1 REAL, bbox_y1 REAL,
    bbox_x2 REAL, bbox_y2 REAL
);

CREATE TABLE IF NOT EXISTS paper_formulas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id        TEXT NOT NULL REFERENCES pdf_extractions(paper_id) ON DELETE CASCADE,
    formula_order   INTEGER NOT NULL,
    content         TEXT NOT NULL DEFAULT '',
    page_number     INTEGER DEFAULT 0,
    latex           TEXT NOT NULL DEFAULT ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS paper_sections_fts USING fts5(
    paper_id, section_title, section_text,
    content='paper_sections', content_rowid='id'
);

-- ============================================================
-- paper_artifacts (flexible file output tracking)
-- ============================================================
CREATE TABLE IF NOT EXISTS paper_artifacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    artifact_type   TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    file_size       INTEGER DEFAULT 0,
    file_hash       TEXT DEFAULT '',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(paper_id, artifact_type)
);
CREATE INDEX IF NOT EXISTS idx_art_type ON paper_artifacts(artifact_type);

-- ============================================================
-- crawl_jobs
-- ============================================================
CREATE TABLE IF NOT EXISTS crawl_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type        TEXT NOT NULL,
    platform        TEXT NOT NULL,
    domain          TEXT DEFAULT '',
    query           TEXT DEFAULT '',
    year_from       INTEGER DEFAULT 0,
    year_to         INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    papers_found    INTEGER DEFAULT 0,
    papers_new      INTEGER DEFAULT 0,
    pdfs_downloaded INTEGER DEFAULT 0,
    pdfs_failed     INTEGER DEFAULT 0,
    error           TEXT DEFAULT '',
    started_at      TEXT,
    completed_at    TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cj_status ON crawl_jobs(status);
CREATE INDEX IF NOT EXISTS idx_cj_platform ON crawl_jobs(platform);

-- ============================================================
-- views
-- ============================================================

CREATE VIEW IF NOT EXISTS v_papers_full AS
SELECT
    p.paper_id, p.title, p.abstract, p.year, p.doi, p.pmid,
    p.arxiv_id, p.venue, p.venue_type, p.citation_count,
    p.created_at, p.updated_at,
    (SELECT json_group_array(name) FROM (
        SELECT a.name FROM paper_authors pa
        JOIN authors a ON a.id = pa.author_id
        WHERE pa.paper_id = p.paper_id ORDER BY pa.author_order
    )) AS authors_json,
    (SELECT json_group_array(
        json_object('platform', platform, 'url', url,
                    'pdf_url', pdf_url, 'is_oa', is_open_access))
     FROM paper_sources ps WHERE ps.paper_id = p.paper_id
    ) AS sources_json,
    (SELECT json_group_array(
        json_object('taxonomy', tt.taxonomy_id, 'tag', tt.tag_code,
                    'name', tt.tag_name, 'is_primary', pt.is_primary))
     FROM paper_tags pt
     JOIN taxonomy_tags tt ON tt.id = pt.tag_id
     WHERE pt.paper_id = p.paper_id
    ) AS tags_json
FROM papers p;

CREATE VIEW IF NOT EXISTS v_papers_with_pdf AS
SELECT
    p.paper_id, p.title, p.year, p.doi, p.venue,
    (SELECT pdf_path FROM pdf_downloads
     WHERE paper_id = p.paper_id AND success = 1 LIMIT 1) AS pdf_path,
    (SELECT COUNT(*) FROM pdf_downloads
     WHERE paper_id = p.paper_id AND success = 1) AS pdf_downloaded,
    pe.status AS extraction_status,
    pe.engine AS extraction_engine,
    pe.page_count,
    pe.text_json_path, pe.sections_json_path, pe.tables_json_path,
    pe.images_dir, pe.markdown_path
FROM papers p
LEFT JOIN pdf_extractions pe ON pe.paper_id = p.paper_id;

CREATE VIEW IF NOT EXISTS v_papers_by_tag AS
SELECT
    t.id AS taxonomy_id, t.name AS taxonomy_name,
    tt.tag_code, tt.tag_name,
    COUNT(DISTINCT pt.paper_id) AS paper_count
FROM taxonomy t
JOIN taxonomy_tags tt ON tt.taxonomy_id = t.id
LEFT JOIN paper_tags pt ON pt.tag_id = tt.id
GROUP BY t.id, tt.id
ORDER BY t.name, paper_count DESC;

CREATE VIEW IF NOT EXISTS v_crawl_stats AS
SELECT
    platform, job_type, status,
    COUNT(*) AS job_count,
    SUM(papers_found) AS total_found,
    SUM(pdfs_downloaded) AS total_downloaded,
    SUM(pdfs_failed) AS total_failed
FROM crawl_jobs
GROUP BY platform, job_type, status;

CREATE VIEW IF NOT EXISTS v_paper_artifacts AS
SELECT
    p.paper_id, p.title,
    (SELECT pdf_path FROM pdf_downloads
     WHERE paper_id = p.paper_id AND success = 1 LIMIT 1) AS pdf_path,
    (SELECT json_group_array(
        json_object('type', artifact_type, 'path', file_path))
     FROM paper_artifacts WHERE paper_id = p.paper_id
    ) AS artifacts_json,
    pe.text_json_path, pe.sections_json_path, pe.tables_json_path,
    pe.images_json_path, pe.formulas_json_path,
    pe.images_dir, pe.figures_dir, pe.markdown_path
FROM papers p
LEFT JOIN pdf_extractions pe ON pe.paper_id = p.paper_id;
"""
