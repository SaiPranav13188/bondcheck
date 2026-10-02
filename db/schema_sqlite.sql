-- SQLite equivalent of schema.sql, used for local development and the evaluation.
-- Arrays and JSONB are stored as JSON text; booleans as 0/1.

CREATE TABLE IF NOT EXISTS companies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    normalized_name TEXT UNIQUE NOT NULL,
    aliases         TEXT DEFAULT '[]',
    created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS offer_records (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id             INTEGER REFERENCES companies(id),
    batch_year             INTEGER NOT NULL,
    role                   TEXT,
    ctc_annual             INTEGER,
    has_bond               INTEGER,
    bond_months            INTEGER,
    penalty_amount         INTEGER,
    penalty_prorated       TEXT CHECK (penalty_prorated IN ('yes','no','not_mentioned')),
    notice_days            INTEGER,
    training_cost_recovery INTEGER,
    certificates_retained  INTEGER,
    other_risky_clauses    TEXT DEFAULT '[]',
    source_type            TEXT CHECK (source_type IN ('upload','public_web')),
    source_url             TEXT,
    confidence             REAL,
    status                 TEXT DEFAULT 'pending' CHECK (status IN ('pending','verified','rejected')),
    created_at             TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS evidence (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id  INTEGER REFERENCES offer_records(id) ON DELETE CASCADE,
    field      TEXT NOT NULL,
    quote      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conflicts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id  INTEGER REFERENCES companies(id),
    batch_year  INTEGER,
    role        TEXT,
    field       TEXT,
    values_seen TEXT,
    status      TEXT DEFAULT 'open' CHECK (status IN ('open','resolved')),
    created_at  TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS moderation_queue (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id  INTEGER REFERENCES offer_records(id),
    reason     TEXT,
    status     TEXT DEFAULT 'pending',
    note       TEXT,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS placement_drives (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER REFERENCES companies(id),
    college    TEXT,
    drive_date TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    email     TEXT UNIQUE NOT NULL,
    alert_all INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS subscriptions (
    user_id    INTEGER REFERENCES users(id),
    company_id INTEGER REFERENCES companies(id),
    PRIMARY KEY (user_id, company_id)
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_ref     TEXT,
    workflow    TEXT,
    agent       TEXT,
    steps       TEXT,
    tokens_used INTEGER,
    duration_ms INTEGER,
    status      TEXT,
    created_at  TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS data_requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id  INTEGER REFERENCES companies(id),
    batch_year  INTEGER,
    reason      TEXT,
    message     TEXT,
    status      TEXT DEFAULT 'open',
    created_at  TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS alerts_sent (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(id),
    company_id INTEGER REFERENCES companies(id),
    drive_id   INTEGER REFERENCES placement_drives(id),
    subject    TEXT,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE (user_id, drive_id)
);

CREATE INDEX IF NOT EXISTS idx_records_company ON offer_records(company_id, batch_year, role);
CREATE INDEX IF NOT EXISTS idx_evidence_record ON evidence(record_id);

-- SQLite has no MODE() aggregate, so the typical values use a correlated "most frequent" subquery.
DROP VIEW IF EXISTS company_summary;
CREATE VIEW company_summary AS
SELECT c.id AS company_id, c.name, r.batch_year, r.role,
       (SELECT r2.bond_months FROM offer_records r2
         WHERE r2.company_id = r.company_id AND r2.batch_year = r.batch_year AND r2.role IS r.role
           AND r2.status = 'verified' AND r2.source_type = 'upload'
         GROUP BY r2.bond_months ORDER BY COUNT(*) DESC, r2.bond_months LIMIT 1) AS typical_bond_months,
       (SELECT r2.penalty_amount FROM offer_records r2
         WHERE r2.company_id = r.company_id AND r2.batch_year = r.batch_year AND r2.role IS r.role
           AND r2.status = 'verified' AND r2.source_type = 'upload'
         GROUP BY r2.penalty_amount ORDER BY COUNT(*) DESC, r2.penalty_amount LIMIT 1) AS typical_penalty,
       COUNT(*)        AS supporting_uploads,
       MAX(r.created_at) AS latest_upload
FROM offer_records r
JOIN companies c ON c.id = r.company_id
WHERE r.status = 'verified' AND r.source_type = 'upload'
GROUP BY c.id, c.name, r.batch_year, r.role;
