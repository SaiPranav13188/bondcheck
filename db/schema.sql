-- BondCheck schema (PostgreSQL: Neon / Supabase)
-- Tables from the design doc, plus four small support tables marked "extension".

CREATE TABLE IF NOT EXISTS companies (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    normalized_name TEXT UNIQUE NOT NULL,
    aliases         TEXT[] DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS offer_records (
    id                     SERIAL PRIMARY KEY,
    company_id             INT REFERENCES companies(id),
    batch_year             INT NOT NULL,
    role                   TEXT,
    ctc_annual             INT,
    has_bond               BOOLEAN,
    bond_months            INT,
    penalty_amount         INT,
    penalty_prorated       TEXT CHECK (penalty_prorated IN ('yes','no','not_mentioned')),
    notice_days            INT,
    training_cost_recovery BOOLEAN,
    certificates_retained  BOOLEAN,
    other_risky_clauses    JSONB DEFAULT '[]',
    source_type            TEXT CHECK (source_type IN ('upload','public_web')),
    source_url             TEXT,              -- only for public sources
    confidence             NUMERIC(3,2),
    status                 TEXT DEFAULT 'pending'
                           CHECK (status IN ('pending','verified','rejected')),
    created_at             TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evidence (
    id         SERIAL PRIMARY KEY,
    record_id  INT REFERENCES offer_records(id) ON DELETE CASCADE,
    field      TEXT NOT NULL,
    quote      TEXT NOT NULL                   -- redacted clause text only
);

CREATE TABLE IF NOT EXISTS conflicts (
    id          SERIAL PRIMARY KEY,
    company_id  INT REFERENCES companies(id),
    batch_year  INT,
    role        TEXT,
    field       TEXT,
    values_seen JSONB,                          -- e.g. {"75000": 2, "150000": 5}
    status      TEXT DEFAULT 'open' CHECK (status IN ('open','resolved')),
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS moderation_queue (
    id         SERIAL PRIMARY KEY,
    record_id  INT REFERENCES offer_records(id),
    reason     TEXT,                            -- outlier | new_company | conflict
    status     TEXT DEFAULT 'pending',
    note       TEXT,                            -- extension: agent's explanation for the moderator
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS placement_drives (
    id         SERIAL PRIMARY KEY,
    company_id INT REFERENCES companies(id),
    college    TEXT,
    drive_date DATE
);

CREATE TABLE IF NOT EXISTS users (
    id        SERIAL PRIMARY KEY,
    email     TEXT UNIQUE NOT NULL,
    alert_all BOOLEAN DEFAULT FALSE             -- extension: opt in to "no bond" alerts too
);

CREATE TABLE IF NOT EXISTS subscriptions (
    user_id    INT REFERENCES users(id),
    company_id INT REFERENCES companies(id),
    PRIMARY KEY (user_id, company_id)
);

CREATE TABLE IF NOT EXISTS agent_runs (                       -- observability
    id          SERIAL PRIMARY KEY,
    run_ref     TEXT,                           -- extension: groups the agents of one workflow run
    workflow    TEXT,                           -- upload | question | monitor | alert
    agent       TEXT,
    steps       JSONB,                          -- tool calls, decisions, retries
    tokens_used INT,
    duration_ms INT,
    status      TEXT,                           -- success | retried | escalated | failed
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- extension: "data needed" requests created by the Monitor Agent
CREATE TABLE IF NOT EXISTS data_requests (
    id          SERIAL PRIMARY KEY,
    company_id  INT REFERENCES companies(id),
    batch_year  INT,
    reason      TEXT,                           -- no_data | stale | conflict
    message     TEXT,
    status      TEXT DEFAULT 'open',
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- extension: lets the Alert Agent avoid sending the same alert twice
CREATE TABLE IF NOT EXISTS alerts_sent (
    id         SERIAL PRIMARY KEY,
    user_id    INT REFERENCES users(id),
    company_id INT REFERENCES companies(id),
    drive_id   INT REFERENCES placement_drives(id),
    subject    TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, drive_id)
);

CREATE INDEX IF NOT EXISTS idx_records_company ON offer_records(company_id, batch_year, role);
CREATE INDEX IF NOT EXISTS idx_evidence_record ON evidence(record_id);

-- Company summary used by the website and Q&A agent
CREATE OR REPLACE VIEW company_summary AS
SELECT c.id AS company_id, c.name, r.batch_year, r.role,
       MODE() WITHIN GROUP (ORDER BY r.bond_months)    AS typical_bond_months,
       MODE() WITHIN GROUP (ORDER BY r.penalty_amount) AS typical_penalty,
       COUNT(*)                                        AS supporting_uploads,
       MAX(r.created_at)                               AS latest_upload
FROM offer_records r
JOIN companies c ON c.id = r.company_id
WHERE r.status = 'verified' AND r.source_type = 'upload'
GROUP BY c.id, c.name, r.batch_year, r.role;

-- Read-only role for the Q&A agent: SELECT on the summary, records, evidence and conflicts only.
-- Run once as the database owner, then put this role's URL in DATABASE_URL_READONLY.
--   CREATE ROLE bondcheck_qa LOGIN PASSWORD '<choose-a-password>';
--   GRANT CONNECT ON DATABASE <db> TO bondcheck_qa;
--   GRANT USAGE ON SCHEMA public TO bondcheck_qa;
--   GRANT SELECT ON company_summary, offer_records, evidence, conflicts TO bondcheck_qa;
--   ALTER ROLE bondcheck_qa SET default_transaction_read_only = on;
--   ALTER ROLE bondcheck_qa SET statement_timeout = '5s';
