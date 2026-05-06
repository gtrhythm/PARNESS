ARTIFACTS_DDL = """
-- ============================================================
-- artifacts.db — Unified flexible artifact store
--
-- Replaces the previous evaluations / paper_writing / experiment_paper
-- databases. Designed for fast-evolving agent outputs where rigid
-- per-domain tables led to ~15% schema coverage and frequent DDL churn.
--
-- Tables (4):
--   sessions        : pipeline run context
--   artifacts       : every agent-produced "thing"  (type-tagged, JSON payload)
--   artifact_metrics: numeric metrics for sortable / comparable queries
--   artifact_links  : artifact-to-artifact DAG (evaluates / supersedes / cites / ...)
-- ============================================================

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

-- ============================================================
-- sessions
-- ============================================================
CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,
    pipeline_name   TEXT DEFAULT '',
    idea_id         TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    payload_json    TEXT DEFAULT '{}',
    started_at      TEXT DEFAULT (datetime('now')),
    finished_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_idea ON sessions(idea_id);
CREATE INDEX IF NOT EXISTS idx_sessions_pipeline ON sessions(pipeline_name);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);

-- ============================================================
-- artifacts (the heart of the design)
--
-- One row per "thing produced by some agent". The artifact_type column
-- is an open-ended enum -- new types can be added without DDL changes.
-- Examples:
--   experiment / experiment_attempt
--   paper_draft / paper_section / paper_reference / bibtex
--   image / chart / tex / pdf
--   eval_export / eval_report / metric_snapshot
--   code_repo / extracted_link / related_paper / download_report
--
-- payload_json holds anything agent-specific (caption, prompt, config,
-- raw experiment results blob, ...). Stable / queryable fields stay as
-- columns; everything else lives in JSON.
-- ============================================================
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id     TEXT PRIMARY KEY,
    artifact_type   TEXT NOT NULL,
    idea_id         TEXT DEFAULT '',
    session_id      TEXT
                    REFERENCES sessions(session_id) ON DELETE CASCADE,
    parent_id       TEXT
                    REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'created',
    role            TEXT DEFAULT '',
    file_path       TEXT DEFAULT '',
    file_size_bytes INTEGER DEFAULT 0,
    payload_json    TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(artifact_type);
CREATE INDEX IF NOT EXISTS idx_artifacts_idea ON artifacts(idea_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_session ON artifacts(session_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_parent ON artifacts(parent_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_status ON artifacts(status);
CREATE INDEX IF NOT EXISTS idx_artifacts_type_status
    ON artifacts(artifact_type, status);

-- ============================================================
-- artifact_metrics
--
-- Separate table (not JSON) so we can ORDER BY metric_value, do
-- baseline comparisons, build leaderboards, etc.
-- is_primary marks the headline metric for display / ranking.
-- ============================================================
CREATE TABLE IF NOT EXISTS artifact_metrics (
    artifact_id     TEXT NOT NULL
                    REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    metric_name     TEXT NOT NULL,
    metric_value    REAL NOT NULL,
    is_primary      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (artifact_id, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_metrics_name ON artifact_metrics(metric_name, metric_value);
CREATE INDEX IF NOT EXISTS idx_metrics_primary
    ON artifact_metrics(is_primary) WHERE is_primary = 1;

-- ============================================================
-- artifact_links
--
-- Directed edges between artifacts. link_kind examples:
--   evaluates / supersedes / generated_from / cites / contains
-- ============================================================
CREATE TABLE IF NOT EXISTS artifact_links (
    from_id         TEXT NOT NULL
                    REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    to_id           TEXT NOT NULL
                    REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    link_kind       TEXT NOT NULL,
    payload_json    TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (from_id, to_id, link_kind)
);

CREATE INDEX IF NOT EXISTS idx_links_to ON artifact_links(to_id, link_kind);
CREATE INDEX IF NOT EXISTS idx_links_kind ON artifact_links(link_kind);

-- ============================================================
-- views: convenience JSON projections
-- ============================================================

CREATE VIEW IF NOT EXISTS v_artifacts_full AS
SELECT
    a.artifact_id,
    a.artifact_type,
    a.idea_id,
    a.session_id,
    a.parent_id,
    a.status,
    a.role,
    a.file_path,
    a.file_size_bytes,
    a.payload_json,
    a.created_at,
    a.updated_at,
    (
        SELECT json_group_object(metric_name, metric_value)
        FROM artifact_metrics
        WHERE artifact_id = a.artifact_id
    ) AS metrics_json,
    (
        SELECT metric_name FROM artifact_metrics
        WHERE artifact_id = a.artifact_id AND is_primary = 1
        LIMIT 1
    ) AS primary_metric_name,
    (
        SELECT metric_value FROM artifact_metrics
        WHERE artifact_id = a.artifact_id AND is_primary = 1
        LIMIT 1
    ) AS primary_metric_value
FROM artifacts a;

CREATE VIEW IF NOT EXISTS v_session_summary AS
SELECT
    s.session_id,
    s.pipeline_name,
    s.idea_id,
    s.status,
    s.started_at,
    s.finished_at,
    COUNT(a.artifact_id) AS artifact_count,
    COUNT(DISTINCT a.artifact_type) AS artifact_type_count
FROM sessions s
LEFT JOIN artifacts a ON a.session_id = s.session_id
GROUP BY s.session_id;
"""
