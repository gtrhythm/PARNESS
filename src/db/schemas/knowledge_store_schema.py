KNOWLEDGE_STORE_DDL = """
-- ============================================================
-- knowledge_store.db DDL
-- 25 main tables + 37 sub-tables = 62 tables
-- ============================================================

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA cache_size = -64000;
PRAGMA temp_store = MEMORY;

-- ============================================================
-- MAIN TABLE 1: insights
-- ============================================================
CREATE TABLE IF NOT EXISTS insights (
    paper_id        TEXT PRIMARY KEY,
    title           TEXT NOT NULL DEFAULT '',
    year            INTEGER NOT NULL DEFAULT 0,
    core_insight    TEXT DEFAULT '',
    problem_solved  TEXT DEFAULT '',
    key_trick       TEXT DEFAULT '',
    novelty_signal  TEXT DEFAULT '',
    extra_json      TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_insights_year ON insights(year);

-- Sub-tables for insights
CREATE TABLE IF NOT EXISTS insight_limitations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id    TEXT NOT NULL REFERENCES insights(paper_id) ON DELETE CASCADE,
    limitation  TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_il_paper ON insight_limitations(paper_id);

CREATE TABLE IF NOT EXISTS insight_open_questions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id    TEXT NOT NULL REFERENCES insights(paper_id) ON DELETE CASCADE,
    question    TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS insight_reusable_components (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id    TEXT NOT NULL REFERENCES insights(paper_id) ON DELETE CASCADE,
    component   TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS insight_assumptions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id    TEXT NOT NULL REFERENCES insights(paper_id) ON DELETE CASCADE,
    assumption  TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- MAIN TABLE 2: seeds
-- ============================================================
CREATE TABLE IF NOT EXISTS seeds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    seed            TEXT NOT NULL,
    seed_type       TEXT NOT NULL,
    rationale       TEXT DEFAULT '',
    extra_json      TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE (seed, seed_type)
);
CREATE INDEX IF NOT EXISTS idx_seeds_type ON seeds(seed_type);

CREATE TABLE IF NOT EXISTS seed_source_papers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    seed_id     INTEGER NOT NULL REFERENCES seeds(id) ON DELETE CASCADE,
    paper_id    TEXT NOT NULL REFERENCES insights(paper_id),
    position    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ssp_seed ON seed_source_papers(seed_id);
CREATE INDEX IF NOT EXISTS idx_ssp_paper ON seed_source_papers(paper_id);

CREATE TABLE IF NOT EXISTS seed_related_insights (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    seed_id     INTEGER NOT NULL REFERENCES seeds(id) ON DELETE CASCADE,
    insight     TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- MAIN TABLE 3: seed_clusters
-- ============================================================
CREATE TABLE IF NOT EXISTS seed_clusters (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    theme   TEXT NOT NULL DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_seed_clusters_theme ON seed_clusters(theme);

CREATE TABLE IF NOT EXISTS seed_cluster_insights (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id  INTEGER NOT NULL REFERENCES seed_clusters(id) ON DELETE CASCADE,
    paper_id    TEXT NOT NULL REFERENCES insights(paper_id),
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS seed_cluster_limitations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id  INTEGER NOT NULL REFERENCES seed_clusters(id) ON DELETE CASCADE,
    limitation  TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS seed_cluster_gaps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id      INTEGER NOT NULL REFERENCES seed_clusters(id) ON DELETE CASCADE,
    seed            TEXT NOT NULL,
    seed_type       TEXT DEFAULT '',
    rationale       TEXT DEFAULT '',
    novelty_signal  TEXT DEFAULT '',
    position        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cluster_gap_source_papers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    gap_id      INTEGER NOT NULL REFERENCES seed_cluster_gaps(id) ON DELETE CASCADE,
    paper_id    TEXT NOT NULL REFERENCES insights(paper_id),
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cluster_gap_related_insights (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    gap_id      INTEGER NOT NULL REFERENCES seed_cluster_gaps(id) ON DELETE CASCADE,
    insight     TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- MAIN TABLE 4: cross_domain_pairs
-- ============================================================
CREATE TABLE IF NOT EXISTS cross_domain_pairs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    insight_a_id        TEXT NOT NULL REFERENCES insights(paper_id),
    insight_b_id        TEXT NOT NULL REFERENCES insights(paper_id),
    surface_similarity  REAL DEFAULT 0.0,
    structural_analogy  TEXT DEFAULT '',
    transfer_direction  TEXT DEFAULT '',
    created_at          TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cdp_dedup ON cross_domain_pairs(insight_a_id, insight_b_id);

CREATE TABLE IF NOT EXISTS cross_domain_pair_seeds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pair_id         INTEGER NOT NULL REFERENCES cross_domain_pairs(id) ON DELETE CASCADE,
    seed            TEXT NOT NULL,
    seed_type       TEXT DEFAULT '',
    rationale       TEXT DEFAULT '',
    novelty_signal  TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS cd_pair_seed_source_papers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    seed_row_id INTEGER NOT NULL REFERENCES cross_domain_pair_seeds(id) ON DELETE CASCADE,
    paper_id    TEXT NOT NULL REFERENCES insights(paper_id),
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cd_pair_seed_related_insights (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    seed_row_id INTEGER NOT NULL REFERENCES cross_domain_pair_seeds(id) ON DELETE CASCADE,
    insight     TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- MAIN TABLE 5: replication_problems
-- ============================================================
CREATE TABLE IF NOT EXISTS replication_problems (
    paper_id                TEXT PRIMARY KEY,
    paper_title             TEXT DEFAULT '',
    claimed_result          TEXT DEFAULT '',
    reproduction_issue      TEXT DEFAULT '',
    suggested_experiment    TEXT DEFAULT '',
    potential_improvement   TEXT DEFAULT '',
    FOREIGN KEY (paper_id) REFERENCES insights(paper_id)
);

CREATE TABLE IF NOT EXISTS replication_missing_details (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id    TEXT NOT NULL REFERENCES replication_problems(paper_id) ON DELETE CASCADE,
    detail      TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- MAIN TABLE 6: transfer_ideas
-- ============================================================
CREATE TABLE IF NOT EXISTS transfer_ideas (
    method_name         TEXT PRIMARY KEY,
    source_domain       TEXT DEFAULT '',
    target_domain       TEXT DEFAULT '',
    method_description  TEXT DEFAULT '',
    transfer_rationale  TEXT DEFAULT '',
    adaptation_needed   TEXT DEFAULT '',
    feasibility_score   REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS transfer_idea_source_papers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    method_name     TEXT NOT NULL REFERENCES transfer_ideas(method_name) ON DELETE CASCADE,
    paper_id        TEXT NOT NULL,
    position        INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- MAIN TABLE 7: critiques
-- ============================================================
CREATE TABLE IF NOT EXISTS critiques (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id                TEXT DEFAULT '',
    claim                   TEXT DEFAULT '',
    flaw                    TEXT NOT NULL,
    severity                TEXT DEFAULT '',
    suggested_improvement   TEXT DEFAULT '',
    evidence                TEXT DEFAULT '',
    FOREIGN KEY (paper_id) REFERENCES insights(paper_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_critiques_dedup ON critiques(paper_id, SUBSTR(flaw, 1, 200));

-- ============================================================
-- MAIN TABLE 8: theory_improvements
-- ============================================================
CREATE TABLE IF NOT EXISTS theory_improvements (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id                TEXT DEFAULT '',
    original_assumption     TEXT DEFAULT '',
    theoretical_issue       TEXT NOT NULL,
    proposed_correction     TEXT DEFAULT '',
    mathematical_sketch     TEXT DEFAULT '',
    impact_assessment       TEXT DEFAULT '',
    FOREIGN KEY (paper_id) REFERENCES insights(paper_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_theory_improvements_dedup ON theory_improvements(paper_id, SUBSTR(theoretical_issue, 1, 200));

-- ============================================================
-- MAIN TABLE 9: trends
-- ============================================================
CREATE TABLE IF NOT EXISTS trends (
    trend_name      TEXT PRIMARY KEY,
    description     TEXT DEFAULT '',
    growth_rate     TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS trend_supporting_papers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trend_name  TEXT NOT NULL REFERENCES trends(trend_name) ON DELETE CASCADE,
    paper_id    TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS trend_related_gaps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trend_name  TEXT NOT NULL REFERENCES trends(trend_name) ON DELETE CASCADE,
    gap         TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- MAIN TABLE 10: meta_gaps
-- ============================================================
CREATE TABLE IF NOT EXISTS meta_gaps (
    gap_description     TEXT PRIMARY KEY,
    domain              TEXT DEFAULT '',
    opportunity_score   REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS meta_gap_evidence_papers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    gap_description TEXT NOT NULL REFERENCES meta_gaps(gap_description) ON DELETE CASCADE,
    paper_id        TEXT NOT NULL,
    position        INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- MAIN TABLE 11: follow_up_ideas
-- ============================================================
CREATE TABLE IF NOT EXISTS follow_up_ideas (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    original_paper_id       TEXT DEFAULT '',
    original_paper_title    TEXT DEFAULT '',
    future_work_claim       TEXT DEFAULT '',
    extension_idea          TEXT NOT NULL,
    feasibility             TEXT DEFAULT '',
    novelty_assessment      TEXT DEFAULT '',
    required_resources      TEXT DEFAULT '',
    FOREIGN KEY (original_paper_id) REFERENCES insights(paper_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_follow_up_ideas_dedup ON follow_up_ideas(original_paper_id, SUBSTR(extension_idea, 1, 200));

-- ============================================================
-- MAIN TABLE 12: failure_cases
-- ============================================================
CREATE TABLE IF NOT EXISTS failure_cases (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id                TEXT DEFAULT '',
    paper_title             TEXT DEFAULT '',
    method_description      TEXT DEFAULT '',
    failure_scenario        TEXT NOT NULL,
    why_it_fails            TEXT DEFAULT '',
    counter_example         TEXT DEFAULT '',
    suggested_fix           TEXT DEFAULT '',
    FOREIGN KEY (paper_id) REFERENCES insights(paper_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_failure_cases_dedup ON failure_cases(paper_id, SUBSTR(failure_scenario, 1, 200));

-- ============================================================
-- MAIN TABLE 13: limitation_extensions
-- ============================================================
CREATE TABLE IF NOT EXISTS limitation_extensions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id                TEXT DEFAULT '',
    paper_title             TEXT DEFAULT '',
    stated_limitation       TEXT NOT NULL,
    extension_direction     TEXT DEFAULT '',
    proposed_approach       TEXT DEFAULT '',
    expected_contribution   TEXT DEFAULT '',
    difficulty              TEXT DEFAULT '',
    FOREIGN KEY (paper_id) REFERENCES insights(paper_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_limitation_extensions_dedup ON limitation_extensions(paper_id, SUBSTR(stated_limitation, 1, 200));

-- ============================================================
-- MAIN TABLE 14: hypotheses
-- ============================================================
CREATE TABLE IF NOT EXISTS hypotheses (
    hypothesis_id       TEXT PRIMARY KEY,
    statement           TEXT DEFAULT '',
    rationale           TEXT DEFAULT '',
    testability         TEXT DEFAULT '',
    predicted_outcome   TEXT DEFAULT '',
    required_experiment TEXT DEFAULT '',
    confidence          REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS hypothesis_source_papers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    hypothesis_id   TEXT NOT NULL REFERENCES hypotheses(hypothesis_id) ON DELETE CASCADE,
    paper_id        TEXT NOT NULL,
    position        INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- MAIN TABLE 15: evidence_items
-- ============================================================
CREATE TABLE IF NOT EXISTS evidence_items (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    hypothesis_id           TEXT NOT NULL,
    paper_id                TEXT DEFAULT '',
    paper_title             TEXT DEFAULT '',
    stance                  TEXT DEFAULT '',
    evidence_description    TEXT NOT NULL,
    strength                TEXT DEFAULT '',
    relevance               REAL DEFAULT 0.0,
    FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(hypothesis_id),
    FOREIGN KEY (paper_id) REFERENCES insights(paper_id)
);
CREATE INDEX IF NOT EXISTS idx_evidence_hypothesis ON evidence_items(hypothesis_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_items_dedup ON evidence_items(hypothesis_id, paper_id);

-- ============================================================
-- MAIN TABLE 16: ideas
-- ============================================================
CREATE TABLE IF NOT EXISTS ideas (
    id                          TEXT PRIMARY KEY,
    title                       TEXT NOT NULL,
    description                 TEXT DEFAULT '',
    category                    TEXT DEFAULT '',
    methodology                 TEXT DEFAULT '',
    expected_results            TEXT DEFAULT '',
    required_resources          TEXT DEFAULT '',
    risk_analysis               TEXT DEFAULT '',
    seed_type                   TEXT DEFAULT '',
    rationale                   TEXT DEFAULT '',
    novelty_score               REAL DEFAULT 0.0,
    feasibility_score           REAL DEFAULT 0.0,
    impact_score                REAL DEFAULT 0.0,
    overall_score               REAL DEFAULT 0.0,
    direction_alignment_score   REAL DEFAULT 0.0,
    is_archived                 INTEGER DEFAULT 0,
    extra_json                  TEXT DEFAULT '{}',
    created_at                  TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ideas_title ON ideas(LOWER(TRIM(title)));
CREATE INDEX IF NOT EXISTS idx_ideas_score ON ideas(overall_score DESC);
CREATE INDEX IF NOT EXISTS idx_ideas_archived ON ideas(is_archived);

CREATE TABLE IF NOT EXISTS idea_source_papers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id     TEXT NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
    paper_id    TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_isp_idea ON idea_source_papers(idea_id);

CREATE TABLE IF NOT EXISTS idea_strengths (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id     TEXT NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
    strength    TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS idea_weaknesses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id     TEXT NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
    weakness    TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- MAIN TABLE 17: explorations
-- ============================================================
CREATE TABLE IF NOT EXISTS explorations (
    idea_id                 TEXT PRIMARY KEY REFERENCES ideas(id),
    idea_title              TEXT DEFAULT '',
    related_work            TEXT DEFAULT '',
    novelty_validation      TEXT DEFAULT '',
    direction_alignment     REAL DEFAULT 0.0,
    extra_json              TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS exploration_search_queries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id     TEXT NOT NULL REFERENCES explorations(idea_id) ON DELETE CASCADE,
    query       TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS exploration_found_papers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id     TEXT NOT NULL REFERENCES explorations(idea_id) ON DELETE CASCADE,
    title       TEXT DEFAULT '',
    year        INTEGER DEFAULT 0,
    abstract    TEXT DEFAULT '',
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS exploration_found_insights (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id     TEXT NOT NULL REFERENCES explorations(idea_id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS exploration_refined_ideas (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id                     TEXT NOT NULL REFERENCES explorations(idea_id) ON DELETE CASCADE,
    title                       TEXT DEFAULT '',
    description                 TEXT DEFAULT '',
    category                    TEXT DEFAULT '',
    methodology                 TEXT DEFAULT '',
    expected_results            TEXT DEFAULT '',
    required_resources          TEXT DEFAULT '',
    risk_analysis               TEXT DEFAULT '',
    seed_type                   TEXT DEFAULT '',
    rationale                   TEXT DEFAULT '',
    novelty_score               REAL DEFAULT 0.0,
    feasibility_score           REAL DEFAULT 0.0,
    impact_score                REAL DEFAULT 0.0,
    overall_score               REAL DEFAULT 0.0,
    direction_alignment_score   REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS exploration_refined_source_papers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    refined_id  INTEGER NOT NULL REFERENCES exploration_refined_ideas(id) ON DELETE CASCADE,
    paper_id    TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS exploration_refined_strengths (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    refined_id  INTEGER NOT NULL REFERENCES exploration_refined_ideas(id) ON DELETE CASCADE,
    strength    TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS exploration_refined_weaknesses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    refined_id  INTEGER NOT NULL REFERENCES exploration_refined_ideas(id) ON DELETE CASCADE,
    weakness    TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS exploration_references_needed (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id         TEXT NOT NULL REFERENCES explorations(idea_id) ON DELETE CASCADE,
    reference_topic TEXT NOT NULL,
    position        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS exploration_innovation_gaps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id     TEXT NOT NULL REFERENCES explorations(idea_id) ON DELETE CASCADE,
    gap         TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- MAIN TABLE 18: idea_references
-- ============================================================
CREATE TABLE IF NOT EXISTS idea_references (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_idea_id      TEXT NOT NULL,
    target_type         TEXT NOT NULL,
    target_id           TEXT NOT NULL,
    reference_kind      TEXT DEFAULT '',
    context             TEXT DEFAULT '',
    confidence          REAL DEFAULT 1.0,
    FOREIGN KEY (source_idea_id) REFERENCES ideas(id)
);
CREATE INDEX IF NOT EXISTS idx_refs_source ON idea_references(source_idea_id);
CREATE INDEX IF NOT EXISTS idx_refs_target ON idea_references(target_type, target_id);

-- ============================================================
-- MAIN TABLE 19: run_log
-- ============================================================
CREATE TABLE IF NOT EXISTS run_log (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline                    TEXT DEFAULT '',
    direction                   TEXT DEFAULT '',
    new_insights                INTEGER DEFAULT 0,
    new_seeds                   INTEGER DEFAULT 0,
    new_ideas                   INTEGER DEFAULT 0,
    new_references              INTEGER DEFAULT 0,
    total_insights              INTEGER DEFAULT 0,
    total_seeds                 INTEGER DEFAULT 0,
    total_ideas                 INTEGER DEFAULT 0,
    papers_crawled              INTEGER DEFAULT 0,
    new_replication_problems    INTEGER DEFAULT 0,
    new_transfer_ideas          INTEGER DEFAULT 0,
    new_critiques               INTEGER DEFAULT 0,
    new_theory_improvements     INTEGER DEFAULT 0,
    new_trends                  INTEGER DEFAULT 0,
    new_meta_gaps               INTEGER DEFAULT 0,
    new_follow_ups              INTEGER DEFAULT 0,
    new_failures                INTEGER DEFAULT 0,
    new_limitations             INTEGER DEFAULT 0,
    new_hypotheses              INTEGER DEFAULT 0,
    new_evidence                INTEGER DEFAULT 0,
    created_at                  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_run_log_created ON run_log(created_at);

-- ============================================================
-- MAIN TABLE 20: store_metadata
-- ============================================================
CREATE TABLE IF NOT EXISTS store_metadata (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);

-- ============================================================
-- MAIN TABLE 21: vectors
-- ============================================================
CREATE TABLE IF NOT EXISTS vectors (
    id              TEXT PRIMARY KEY,
    collection      TEXT NOT NULL CHECK(collection IN ('ideas','insights','seeds','explorations')),
    reference_id    TEXT NOT NULL,
    vector_blob     BLOB,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_vectors_collection ON vectors(collection);
CREATE INDEX IF NOT EXISTS idx_vectors_ref ON vectors(collection, reference_id);

-- ============================================================
-- MAIN TABLE 22: scheduler_ideas
-- ============================================================
CREATE TABLE IF NOT EXISTS scheduler_ideas (
    idea_id         TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    category        TEXT DEFAULT '',
    methodology     TEXT DEFAULT '',
    expected_results TEXT DEFAULT '',
    required_resources TEXT DEFAULT '',
    risk_analysis   TEXT DEFAULT '',
    seed_type       TEXT DEFAULT '',
    rationale       TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft','generated','evaluating','evaluated',
                                      'accepted','rejected','refined','archived')),
    best_score      REAL NOT NULL DEFAULT 0.0,
    extra_json      TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    batch_id        TEXT DEFAULT '',
    paper_count     INTEGER DEFAULT 0,
    insight_count   INTEGER DEFAULT 0,
    seed_count      INTEGER DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_si_title ON scheduler_ideas(LOWER(TRIM(title)));
CREATE INDEX IF NOT EXISTS idx_si_status ON scheduler_ideas(status);
CREATE INDEX IF NOT EXISTS idx_si_score ON scheduler_ideas(best_score DESC);
CREATE INDEX IF NOT EXISTS idx_si_batch ON scheduler_ideas(batch_id);

CREATE TABLE IF NOT EXISTS scheduler_idea_source_papers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id     TEXT NOT NULL REFERENCES scheduler_ideas(idea_id) ON DELETE CASCADE,
    paper_id    TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scheduler_idea_tags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id     TEXT NOT NULL REFERENCES scheduler_ideas(idea_id) ON DELETE CASCADE,
    tag         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sit_tag ON scheduler_idea_tags(tag);

-- ============================================================
-- MAIN TABLE 23: scheduler_evaluations
-- ============================================================
CREATE TABLE IF NOT EXISTS scheduler_evaluations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id         TEXT NOT NULL,
    evaluator       TEXT NOT NULL DEFAULT '',
    novelty_score   REAL DEFAULT 0.0,
    feasibility_score REAL DEFAULT 0.0,
    impact_score    REAL DEFAULT 0.0,
    overall_score   REAL DEFAULT 0.0,
    recommendation  TEXT DEFAULT '',
    timestamp       TEXT NOT NULL,
    notes           TEXT DEFAULT '',
    FOREIGN KEY (idea_id) REFERENCES scheduler_ideas(idea_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_se_idea ON scheduler_evaluations(idea_id);
CREATE INDEX IF NOT EXISTS idx_se_score ON scheduler_evaluations(overall_score DESC);

CREATE TABLE IF NOT EXISTS scheduler_evaluation_strengths (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_id   INTEGER NOT NULL REFERENCES scheduler_evaluations(id) ON DELETE CASCADE,
    strength        TEXT NOT NULL,
    position        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scheduler_evaluation_weaknesses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_id   INTEGER NOT NULL REFERENCES scheduler_evaluations(id) ON DELETE CASCADE,
    weakness        TEXT NOT NULL,
    position        INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- MAIN TABLE 24: scheduler_evaluation_queue
-- ============================================================
CREATE TABLE IF NOT EXISTS scheduler_evaluation_queue (
    idea_id TEXT PRIMARY KEY REFERENCES scheduler_ideas(idea_id) ON DELETE CASCADE
);

-- ============================================================
-- MAIN TABLE 25: scheduler_history
-- ============================================================
CREATE TABLE IF NOT EXISTS scheduler_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT NOT NULL CHECK (action IN ('submit', 'evaluate')),
    timestamp   TEXT NOT NULL,
    batch_id    TEXT,
    evaluator   TEXT,
    count       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sh_action ON scheduler_history(action);
CREATE INDEX IF NOT EXISTS idx_sh_timestamp ON scheduler_history(timestamp);

-- ============================================================
-- MAIN TABLE 26: raw_ideas
-- ============================================================
CREATE TABLE IF NOT EXISTS raw_ideas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    idea            TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT '',
    source_type     TEXT DEFAULT '',
    extra_json      TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_raw_ideas_source ON raw_ideas(source_type);
CREATE INDEX IF NOT EXISTS idx_raw_ideas_created ON raw_ideas(created_at DESC);

-- ============================================================
-- FTS5 for vectors
-- ============================================================
CREATE VIRTUAL TABLE IF NOT EXISTS vectors_fts USING fts5(
    vector_id,
    collection,
    content,
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS vectors_fts_insert AFTER INSERT ON vectors BEGIN
    INSERT INTO vectors_fts(vector_id, collection, content)
    SELECT NEW.id, NEW.collection,
        CASE NEW.collection
            WHEN 'ideas' THEN (
                SELECT i.title || ' ' || i.description || ' ' || i.methodology
                FROM ideas i WHERE i.id = NEW.reference_id
            )
            WHEN 'insights' THEN (
                SELECT ins.title || ' ' || ins.core_insight || ' ' || ins.problem_solved
                FROM insights ins WHERE ins.paper_id = NEW.reference_id
            )
            WHEN 'seeds' THEN (
                SELECT s.seed || ' ' || s.rationale
                FROM seeds s WHERE s.id = NEW.reference_id
            )
            WHEN 'explorations' THEN (
                SELECT e.idea_title || ' ' || e.related_work
                FROM explorations e WHERE e.idea_id = NEW.reference_id
            )
            ELSE ''
        END;
END;

CREATE TRIGGER IF NOT EXISTS vectors_fts_delete AFTER DELETE ON vectors BEGIN
    DELETE FROM vectors_fts WHERE vector_id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS vectors_fts_update AFTER UPDATE ON vectors BEGIN
    DELETE FROM vectors_fts WHERE vector_id = OLD.id;
    INSERT INTO vectors_fts(vector_id, collection, content)
    SELECT NEW.id, NEW.collection,
        CASE NEW.collection
            WHEN 'ideas' THEN (
                SELECT i.title || ' ' || i.description || ' ' || i.methodology
                FROM ideas i WHERE i.id = NEW.reference_id
            )
            WHEN 'insights' THEN (
                SELECT ins.title || ' ' || ins.core_insight || ' ' || ins.problem_solved
                FROM insights ins WHERE ins.paper_id = NEW.reference_id
            )
            WHEN 'seeds' THEN (
                SELECT s.seed || ' ' || s.rationale
                FROM seeds s WHERE s.id = NEW.reference_id
            )
            WHEN 'explorations' THEN (
                SELECT e.idea_title || ' ' || e.related_work
                FROM explorations e WHERE e.idea_id = NEW.reference_id
            )
            ELSE ''
        END;
END;

-- ============================================================
-- VIEWS: JSON reconstruction views
-- ============================================================

CREATE VIEW IF NOT EXISTS v_insights_full AS
SELECT
    i.paper_id,
    i.title,
    i.year,
    i.core_insight,
    i.problem_solved,
    i.key_trick,
    i.novelty_signal,
    i.extra_json,
    i.created_at,
    (
        SELECT json_group_array(limitation)
        FROM insight_limitations
        WHERE paper_id = i.paper_id
    ) AS limitations_json,
    (
        SELECT json_group_array(question)
        FROM insight_open_questions
        WHERE paper_id = i.paper_id
    ) AS open_questions_json,
    (
        SELECT json_group_array(component)
        FROM insight_reusable_components
        WHERE paper_id = i.paper_id
    ) AS reusable_components_json,
    (
        SELECT json_group_array(assumption)
        FROM insight_assumptions
        WHERE paper_id = i.paper_id
    ) AS assumed_but_not_proven_json
FROM insights i;

CREATE VIEW IF NOT EXISTS v_ideas_full AS
SELECT
    i.id,
    i.title,
    i.description,
    i.category,
    i.methodology,
    i.expected_results,
    i.required_resources,
    i.risk_analysis,
    i.seed_type,
    i.rationale,
    i.novelty_score,
    i.feasibility_score,
    i.impact_score,
    i.overall_score,
    i.direction_alignment_score,
    i.is_archived,
    i.extra_json,
    i.created_at,
    (
        SELECT json_group_array(paper_id)
        FROM idea_source_papers
        WHERE idea_id = i.id
    ) AS source_papers_json,
    (
        SELECT json_group_array(strength)
        FROM idea_strengths
        WHERE idea_id = i.id
    ) AS strengths_json,
    (
        SELECT json_group_array(weakness)
        FROM idea_weaknesses
        WHERE idea_id = i.id
    ) AS weaknesses_json
FROM ideas i;

CREATE VIEW IF NOT EXISTS v_seeds_full AS
SELECT
    s.id,
    s.seed,
    s.seed_type,
    s.rationale,
    s.extra_json,
    s.created_at,
    (
        SELECT json_group_array(paper_id)
        FROM seed_source_papers
        WHERE seed_id = s.id
    ) AS source_papers_json,
    (
        SELECT json_group_array(insight)
        FROM seed_related_insights
        WHERE seed_id = s.id
    ) AS related_insights_json
FROM seeds s;

CREATE VIEW IF NOT EXISTS v_explorations_full AS
SELECT
    e.idea_id,
    e.idea_title,
    e.related_work,
    e.novelty_validation,
    e.direction_alignment,
    e.extra_json,
    (
        SELECT json_group_array(query)
        FROM exploration_search_queries
        WHERE idea_id = e.idea_id
    ) AS search_queries_json,
    (
        SELECT json_group_array(
            json_object('title', title, 'year', year, 'abstract', abstract)
        )
        FROM exploration_found_papers
        WHERE idea_id = e.idea_id
    ) AS found_papers_json,
    (
        SELECT json_group_array(title)
        FROM exploration_found_insights
        WHERE idea_id = e.idea_id
    ) AS found_insights_json,
    (
        SELECT json_group_array(reference_topic)
        FROM exploration_references_needed
        WHERE idea_id = e.idea_id
    ) AS references_needed_json,
    (
        SELECT json_group_array(gap)
        FROM exploration_innovation_gaps
        WHERE idea_id = e.idea_id
    ) AS innovation_gaps_json
FROM explorations e;

CREATE VIEW IF NOT EXISTS v_seed_clusters_full AS
SELECT
    sc.id,
    sc.theme,
    sc.created_at,
    (
        SELECT json_group_array(paper_id)
        FROM seed_cluster_insights
        WHERE cluster_id = sc.id
    ) AS insight_indices_json,
    (
        SELECT json_group_array(limitation)
        FROM seed_cluster_limitations
        WHERE cluster_id = sc.id
    ) AS common_limitations_json,
    (
        SELECT json_group_array(
            json_object(
                'seed', seed, 'seed_type', seed_type,
                'rationale', rationale, 'novelty_signal', novelty_signal
            )
        )
        FROM seed_cluster_gaps
        WHERE cluster_id = sc.id
    ) AS gaps_json
FROM seed_clusters sc;

CREATE VIEW IF NOT EXISTS v_transfer_ideas_full AS
SELECT
    t.method_name,
    t.source_domain,
    t.target_domain,
    t.method_description,
    t.transfer_rationale,
    t.adaptation_needed,
    t.feasibility_score,
    (
        SELECT json_group_array(paper_id)
        FROM transfer_idea_source_papers
        WHERE method_name = t.method_name
    ) AS source_papers_json
FROM transfer_ideas t;

CREATE VIEW IF NOT EXISTS v_hypotheses_full AS
SELECT
    h.hypothesis_id,
    h.statement,
    h.rationale,
    h.testability,
    h.predicted_outcome,
    h.required_experiment,
    h.confidence,
    (
        SELECT json_group_array(paper_id)
        FROM hypothesis_source_papers
        WHERE hypothesis_id = h.hypothesis_id
    ) AS source_papers_json
FROM hypotheses h;

CREATE VIEW IF NOT EXISTS v_trends_full AS
SELECT
    t.trend_name,
    t.description,
    t.growth_rate,
    (
        SELECT json_group_array(paper_id)
        FROM trend_supporting_papers
        WHERE trend_name = t.trend_name
    ) AS supporting_papers_json,
    (
        SELECT json_group_array(gap)
        FROM trend_related_gaps
        WHERE trend_name = t.trend_name
    ) AS related_gaps_json
FROM trends t;

CREATE VIEW IF NOT EXISTS v_meta_gaps_full AS
SELECT
    m.gap_description,
    m.domain,
    m.opportunity_score,
    (
        SELECT json_group_array(paper_id)
        FROM meta_gap_evidence_papers
        WHERE gap_description = m.gap_description
    ) AS evidence_papers_json
FROM meta_gaps m;

CREATE VIEW IF NOT EXISTS v_replication_problems_full AS
SELECT
    r.paper_id,
    r.paper_title,
    r.claimed_result,
    r.reproduction_issue,
    r.suggested_experiment,
    r.potential_improvement,
    (
        SELECT json_group_array(detail)
        FROM replication_missing_details
        WHERE paper_id = r.paper_id
    ) AS missing_details_json
FROM replication_problems r;

CREATE VIEW IF NOT EXISTS v_scheduler_ideas_full AS
SELECT
    s.idea_id,
    s.title,
    s.description,
    s.category,
    s.methodology,
    s.expected_results,
    s.required_resources,
    s.risk_analysis,
    s.seed_type,
    s.rationale,
    s.status,
    s.best_score,
    s.extra_json,
    s.created_at,
    s.updated_at,
    s.batch_id,
    s.paper_count,
    s.insight_count,
    s.seed_count,
    (
        SELECT json_group_array(paper_id)
        FROM scheduler_idea_source_papers
        WHERE idea_id = s.idea_id
    ) AS source_papers_json,
    (
        SELECT json_group_array(tag)
        FROM scheduler_idea_tags
        WHERE idea_id = s.idea_id
    ) AS tags_json
FROM scheduler_ideas s;

CREATE VIEW IF NOT EXISTS v_scheduler_evaluations_full AS
SELECT
    e.id,
    e.idea_id,
    e.evaluator,
    e.novelty_score,
    e.feasibility_score,
    e.impact_score,
    e.overall_score,
    e.recommendation,
    e.timestamp,
    e.notes,
    (
        SELECT json_group_array(strength)
        FROM scheduler_evaluation_strengths
        WHERE evaluation_id = e.id
    ) AS strengths_json,
    (
        SELECT json_group_array(weakness)
        FROM scheduler_evaluation_weaknesses
        WHERE evaluation_id = e.id
    ) AS weaknesses_json
FROM scheduler_evaluations e;

-- ============================================================
-- VIEWS: vectors views (from doc 21)
-- ============================================================

CREATE VIEW IF NOT EXISTS v_vectors_full AS
SELECT
    v.id,
    v.collection,
    v.reference_id,
    v.vector_blob,
    v.created_at,
    CASE v.collection
        WHEN 'ideas' THEN (
            SELECT json_object(
                'id', i.id,
                'title', i.title,
                'description', i.description,
                'category', i.category,
                'methodology', i.methodology,
                'expected_results', i.expected_results,
                'required_resources', i.required_resources,
                'risk_analysis', i.risk_analysis,
                'seed_type', i.seed_type,
                'rationale', i.rationale,
                'novelty_score', i.novelty_score,
                'feasibility_score', i.feasibility_score,
                'impact_score', i.impact_score,
                'overall_score', i.overall_score,
                'direction_alignment_score', i.direction_alignment_score,
                'is_archived', i.is_archived,
    'extra_json', i.extra_json,
    'created_at', i.created_at,
    'source_papers', (
        SELECT COALESCE(json_group_array(isp.paper_id), '[]')
        FROM idea_source_papers isp
        WHERE isp.idea_id = i.id
    ),
    'strengths', (
        SELECT COALESCE(json_group_array(istr.strength), '[]')
        FROM idea_strengths istr
        WHERE istr.idea_id = i.id
    ),
    'weaknesses', (
        SELECT COALESCE(json_group_array(istrw.weakness), '[]')
        FROM idea_weaknesses istrw
        WHERE istrw.idea_id = i.id
    )
)
FROM ideas i
            WHERE i.id = v.reference_id
        )
        WHEN 'insights' THEN (
            SELECT json_object(
                'paper_id', ins.paper_id,
                'title', ins.title,
                'year', ins.year,
                'core_insight', ins.core_insight,
                'problem_solved', ins.problem_solved,
                'key_trick', ins.key_trick,
    'novelty_signal', ins.novelty_signal,
    'extra_json', ins.extra_json,
    'created_at', ins.created_at,
    'limitations', (
                    SELECT COALESCE(json_group_array(il.limitation), '[]')
                    FROM insight_limitations il
                    WHERE il.paper_id = ins.paper_id
                ),
                'open_questions', (
                    SELECT COALESCE(json_group_array(ioq.question), '[]')
                    FROM insight_open_questions ioq
                    WHERE ioq.paper_id = ins.paper_id
                ),
                'reusable_components', (
                    SELECT COALESCE(json_group_array(irc.component), '[]')
                    FROM insight_reusable_components irc
                    WHERE irc.paper_id = ins.paper_id
                ),
                'assumed_but_not_proven', (
                    SELECT COALESCE(json_group_array(ia.assumption), '[]')
                    FROM insight_assumptions ia
                    WHERE ia.paper_id = ins.paper_id
                )
            )
            FROM insights ins
            WHERE ins.paper_id = v.reference_id
        )
        WHEN 'seeds' THEN (
            SELECT json_object(
                'id', s.id,
                'seed', s.seed,
                'seed_type', s.seed_type,
    'rationale', s.rationale,
    'extra_json', s.extra_json,
    'created_at', s.created_at,
    'source_papers', (
                    SELECT COALESCE(json_group_array(ssp.paper_id), '[]')
                    FROM seed_source_papers ssp
                    WHERE ssp.seed_id = s.id
                ),
                'related_insights', (
                    SELECT COALESCE(json_group_array(sri.insight), '[]')
                    FROM seed_related_insights sri
                    WHERE sri.seed_id = s.id
                )
            )
            FROM seeds s
            WHERE s.id = v.reference_id
        )
        WHEN 'explorations' THEN (
            SELECT json_object(
                'idea_id', e.idea_id,
                'idea_title', e.idea_title,
                'related_work', e.related_work,
                'novelty_validation', e.novelty_validation,
    'direction_alignment', e.direction_alignment,
    'extra_json', e.extra_json,
    'search_queries', (
                    SELECT COALESCE(json_group_array(esq.query), '[]')
                    FROM exploration_search_queries esq
                    WHERE esq.idea_id = e.idea_id
                ),
                'found_papers', (
                    SELECT COALESCE(json_group_array(
                        json_object('title', efp.title, 'year', efp.year, 'abstract', efp.abstract)
                    ), '[]')
                    FROM exploration_found_papers efp
                    WHERE efp.idea_id = e.idea_id
                ),
                'found_insights', (
                    SELECT COALESCE(json_group_array(efi.title), '[]')
                    FROM exploration_found_insights efi
                    WHERE efi.idea_id = e.idea_id
                ),
                'refined_idea', (
                    SELECT json_object(
                        'title', eri.title,
                        'description', eri.description,
                        'category', eri.category,
                        'methodology', eri.methodology,
                        'expected_results', eri.expected_results,
                        'required_resources', eri.required_resources,
                        'risk_analysis', eri.risk_analysis,
                        'seed_type', eri.seed_type,
                        'rationale', eri.rationale,
                        'novelty_score', eri.novelty_score,
                        'feasibility_score', eri.feasibility_score,
                        'impact_score', eri.impact_score,
                        'overall_score', eri.overall_score,
                        'direction_alignment_score', eri.direction_alignment_score
                    )
                    FROM exploration_refined_ideas eri
                    WHERE eri.idea_id = e.idea_id
                    LIMIT 1
                ),
                'references_needed', (
                    SELECT COALESCE(json_group_array(ern.reference_topic), '[]')
                    FROM exploration_references_needed ern
                    WHERE ern.idea_id = e.idea_id
                ),
                'innovation_gaps', (
                    SELECT COALESCE(json_group_array(eig.gap), '[]')
                    FROM exploration_innovation_gaps eig
                    WHERE eig.idea_id = e.idea_id
                )
            )
            FROM explorations e
            WHERE e.idea_id = v.reference_id
        )
        ELSE NULL
    END AS payload_json
FROM vectors v;

-- ============================================================
-- VIEWS: Flattened views
-- ============================================================

CREATE VIEW IF NOT EXISTS v_ideas_flat AS
SELECT
    i.id AS idea_id,
    i.title,
    i.description,
    i.category,
    i.methodology,
    i.expected_results,
    i.required_resources,
    i.risk_analysis,
    i.seed_type,
    i.rationale,
    i.novelty_score,
    i.feasibility_score,
    i.impact_score,
    i.overall_score,
    i.direction_alignment_score,
    i.is_archived,
    i.extra_json,
    i.created_at,
    GROUP_CONCAT(DISTINCT isp.paper_id) AS all_source_papers,
    GROUP_CONCAT(DISTINCT istr.strength) AS all_strengths,
    GROUP_CONCAT(DISTINCT istrw.weakness) AS all_weaknesses
FROM ideas i
LEFT JOIN idea_source_papers isp ON isp.idea_id = i.id
LEFT JOIN idea_strengths istr ON istr.idea_id = i.id
LEFT JOIN idea_weaknesses istrw ON istrw.idea_id = i.id
GROUP BY i.id;

CREATE VIEW IF NOT EXISTS v_insights_flat AS
SELECT
    i.paper_id,
    i.title,
    i.year,
    i.core_insight,
    i.problem_solved,
    i.key_trick,
    i.novelty_signal,
    GROUP_CONCAT(DISTINCT il.limitation) AS all_limitations,
    GROUP_CONCAT(DISTINCT ioq.question) AS all_open_questions
FROM insights i
LEFT JOIN insight_limitations il ON il.paper_id = i.paper_id
LEFT JOIN insight_open_questions ioq ON ioq.paper_id = i.paper_id
GROUP BY i.paper_id;

CREATE VIEW IF NOT EXISTS v_vectors_ideas_flat AS
SELECT
    v.id AS vector_id,
    v.collection,
    v.reference_id AS idea_id,
    i.title,
    i.category,
    i.overall_score,
    i.is_archived,
    GROUP_CONCAT(DISTINCT isp.paper_id) AS all_source_papers
FROM vectors v
JOIN ideas i ON i.id = v.reference_id
LEFT JOIN idea_source_papers isp ON isp.idea_id = i.id
WHERE v.collection = 'ideas'
GROUP BY v.id;

CREATE VIEW IF NOT EXISTS v_vectors_insights_flat AS
SELECT
    v.id AS vector_id,
    v.collection,
    v.reference_id AS paper_id,
    ins.title,
    ins.year,
    ins.core_insight,
    GROUP_CONCAT(DISTINCT il.limitation) AS all_limitations
FROM vectors v
JOIN insights ins ON ins.paper_id = v.reference_id
LEFT JOIN insight_limitations il ON il.paper_id = ins.paper_id
WHERE v.collection = 'insights'
GROUP BY v.id;

CREATE VIEW IF NOT EXISTS v_vectors_seeds_flat AS
SELECT
    v.id AS vector_id,
    v.collection,
    v.reference_id AS seed_id,
    s.seed,
    s.seed_type,
    s.rationale,
    GROUP_CONCAT(DISTINCT ssp.paper_id) AS all_source_papers
FROM vectors v
JOIN seeds s ON s.id = v.reference_id
LEFT JOIN seed_source_papers ssp ON ssp.seed_id = s.id
WHERE v.collection = 'seeds'
GROUP BY v.id;

CREATE VIEW IF NOT EXISTS v_vectors_explorations_flat AS
SELECT
    v.id AS vector_id,
    v.collection,
    v.reference_id AS idea_id,
    e.idea_title,
    e.direction_alignment,
    e.novelty_validation
FROM vectors v
JOIN explorations e ON e.idea_id = v.reference_id
WHERE v.collection = 'explorations';

-- ============================================================
-- VIEWS: Aggregate views
-- ============================================================

CREATE VIEW IF NOT EXISTS v_idea_source_papers_count AS
SELECT
    i.id AS idea_id,
    i.title,
    COUNT(isp.paper_id) AS source_paper_count
FROM ideas i
LEFT JOIN idea_source_papers isp ON isp.idea_id = i.id
GROUP BY i.id;

CREATE VIEW IF NOT EXISTS v_ideas_by_category AS
SELECT
    category,
    COUNT(*) AS idea_count,
    AVG(overall_score) AS avg_score,
    AVG(novelty_score) AS avg_novelty,
    AVG(feasibility_score) AS avg_feasibility,
    AVG(impact_score) AS avg_impact
FROM ideas
WHERE category != ''
GROUP BY category
ORDER BY idea_count DESC;

CREATE VIEW IF NOT EXISTS v_insight_stats AS
SELECT
    i.year,
    COUNT(*) AS insight_count,
    AVG(LENGTH(i.core_insight)) AS avg_core_insight_length,
    COUNT(il.id) AS total_limitations,
    COUNT(ioq.id) AS total_open_questions
FROM insights i
LEFT JOIN insight_limitations il ON il.paper_id = i.paper_id
LEFT JOIN insight_open_questions ioq ON ioq.paper_id = i.paper_id
GROUP BY i.year;

CREATE VIEW IF NOT EXISTS v_seed_type_distribution AS
SELECT
    seed_type,
    COUNT(*) AS seed_count,
    COUNT(DISTINCT id) AS unique_seed_count
FROM seeds
GROUP BY seed_type;

CREATE VIEW IF NOT EXISTS v_scheduler_evaluation_summary AS
SELECT
    se.idea_id,
    si.title,
    si.status,
    COUNT(se.id) AS evaluation_count,
    MAX(se.overall_score) AS best_score,
    AVG(se.overall_score) AS avg_score,
    MAX(se.timestamp) AS last_evaluation_at
FROM scheduler_evaluations se
JOIN scheduler_ideas si ON si.idea_id = se.idea_id
GROUP BY se.idea_id;

-- ============================================================
-- VIEWS: Cross-table association views
-- ============================================================

CREATE VIEW IF NOT EXISTS v_ideas_with_explorations AS
SELECT
    i.id AS idea_id,
    i.title AS idea_title,
    i.category,
    i.overall_score,
    i.is_archived,
    i.extra_json,
    e.direction_alignment,
    e.novelty_validation,
    (
        SELECT COUNT(*) FROM exploration_found_papers WHERE idea_id = i.id
    ) AS found_papers_count,
    (
        SELECT COUNT(*) FROM exploration_found_insights WHERE idea_id = i.id
    ) AS found_insights_count
FROM ideas i
LEFT JOIN explorations e ON e.idea_id = i.id;

CREATE VIEW IF NOT EXISTS v_ideas_with_scheduler_status AS
SELECT
    i.id AS idea_id,
    i.title,
    i.overall_score,
    i.is_archived,
    si.status AS scheduler_status,
    si.best_score AS scheduler_best_score,
    si.updated_at AS last_scheduler_update
FROM ideas i
LEFT JOIN scheduler_ideas si ON si.idea_id = i.id;

CREATE VIEW IF NOT EXISTS v_insights_with_seeds AS
SELECT
    i.paper_id,
    i.title,
    i.year,
    i.core_insight,
    COUNT(DISTINCT ssp.seed_id) AS source_seed_count,
    GROUP_CONCAT(DISTINCT s.seed) AS related_seeds
FROM insights i
LEFT JOIN seed_source_papers ssp ON ssp.paper_id = i.paper_id
LEFT JOIN seeds s ON s.id = ssp.seed_id
GROUP BY i.paper_id;

-- ============================================================
-- VIEW: FTS search view
-- ============================================================

CREATE VIEW IF NOT EXISTS vectors_fts_search AS
SELECT
    v.id AS vector_id,
    v.collection,
    v.reference_id,
    vf.content AS search_content,
    vf.rank
FROM vectors_fts vf
JOIN vectors v ON v.id = vf.vector_id;
"""
