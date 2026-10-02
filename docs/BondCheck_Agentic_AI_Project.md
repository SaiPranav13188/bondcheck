# BondCheck — An Agentic AI Platform for Job Bond Transparency

> AI agents that read offer letters, extract and verify job bond terms, and warn freshers **before** they sign.

---

## 1. Problem Statement

Every year, lakhs of Indian freshers sign offer letters and service agreements that contain **job bonds**: a commitment to stay 1–3 years or pay a penalty that is often ₹50,000–₹2,00,000, sometimes much more. These students face three problems:

1. **They find out too late.** Bond terms are usually seen after selection, when walking away is no longer realistic.
2. **The available information is unreliable.** Blog posts and forums contradict each other about the same company's bond terms, and nobody shows evidence or dates.
3. **Small and mid-size companies are invisible.** Online articles cover only big IT companies, but the harshest bonds are often at smaller firms nobody writes about.

**BondCheck** solves this with a team of AI agents that turn anonymously uploaded offer letters into a **verified, evidence-backed, searchable database** of bond terms, and proactively warn students before placement drives.

---

## 2. Why This Is an *Agentic* AI Project (Not Just an LLM App)

A normal LLM app takes one prompt and returns one response. BondCheck's agents **plan, use tools, check their own work, make decisions, recover from errors and act without being asked.**

| Agentic concept | Where it appears in BondCheck |
|---|---|
| **Autonomy / goal-driven behaviour** | Agents pursue goals ("produce a verified, PII-free record"), not single prompts |
| **Tool / function calling** | Agents call PDF readers, OCR, SQL, web search, calculators and notifications |
| **Planning & routing** | The Orchestrator decides which agents to run and in what order for each event |
| **Self-verification & self-correction** | The Extraction Agent proves every field with a quote from the document and re-reads when a check fails |
| **Decision-making** | The Verification Agent decides whether a new record corroborates, varies from or conflicts with existing data |
| **Multi-agent collaboration** | 7 specialised agents share state and pass structured results to each other |
| **Memory & state** | Shared state per run, a persistent database, and a full log of every agent step |
| **Proactive behaviour** | The Monitor and Alert agents run on schedules and act without a user request |
| **Human-in-the-loop** | Low-confidence fields go to the uploader; conflicts and outliers go to a moderator |
| **Guardrails** | PII-free storage, read-only SQL, cited answers, retry limits and no legal advice |
| **Evaluation** | A measured benchmark comparing single-pass LLM extraction with the agentic loop |

---

## 3. System Overview

```
                        ┌──────────────────────────────┐
   Events ─────────────▶│      ORCHESTRATOR AGENT      │
   • New upload         │  (plans, routes, retries,    │
   • Student question   │   escalates to humans)       │
   • Scheduled job      └──────────────┬───────────────┘
                                       │
   ┌─────────────────┬─────────────────┼──────────────────┬─────────────────┐
   ▼                 ▼                 ▼                  ▼                 ▼
┌─────────┐   ┌────────────┐   ┌──────────────┐   ┌─────────────┐   ┌───────────┐
│ PRIVACY │──▶│ EXTRACTION │──▶│ VERIFICATION │   │   Q&A       │   │  MONITOR  │
│  AGENT  │   │   AGENT    │   │    AGENT     │   │   AGENT     │   │   AGENT   │
└─────────┘   └────────────┘   └──────┬───────┘   └─────────────┘   └─────┬─────┘
                    │                 │                                   │
                    ▼                 ▼                                   ▼
            Uploader confirms   Moderation queue                    ┌───────────┐
            low-confidence      (human review)                      │  ALERT    │
            fields                                                  │  AGENT    │
                                                                    └───────────┘
                         ┌──────────────────────────────┐
                         │  PostgreSQL + Agent Run Logs │
                         └──────────────────────────────┘
```

### Three main workflows

**Workflow A: New upload**
`Upload → Privacy Agent → Extraction Agent (self-check loop) → [uploader confirms uncertain fields] → Verification Agent → database / moderation queue → document deleted`

**Workflow B: Student question**
`Question → Q&A Agent → (company search + read-only SQL + exit-cost calculator) → cited answer`

**Workflow C: Proactive monitoring (scheduled daily)**
`Monitor Agent → finds upcoming drives with missing or stale data → researches public sources → Alert Agent notifies subscribed students`

---

## 4. The Agents

### 4.1 Orchestrator Agent (Supervisor)

**Goal:** Handle each event correctly and completely, within cost and retry limits.

**Responsibilities:**
- Classify the incoming event and build a plan (which agents, in what order)
- Pass shared state between agents
- Retry failed steps (maximum 2 retries per agent), then escalate to a human
- Stop runaway loops and enforce a token/cost budget per run
- Log every step to `agent_runs`

**Decisions it makes:**
- Is the upload a real offer letter or service agreement? If not, reject it politely.
- Is the document scanned? If yes, route it to OCR before extraction.
- Did any agent fail its checks? If yes, retry, ask the user or escalate to a moderator.

### 4.2 Privacy Agent

**Goal:** Guarantee that no personal information is ever stored.

**Tools:** `extract_text(pdf)`, `ocr_image(page)`, `detect_pii(text)`, `redact(text, spans)`, `scan_for_remaining_pii(text)`

**Loop:**
1. Detect personal information: candidate name, address, phone, email, employee ID, PAN/Aadhaar, signatures, salary account details.
2. Redact it.
3. **Re-scan the redacted text.** If anything is still found, redact again. After 3 failed attempts, **reject the upload** rather than risk a leak.

**Output:** Redacted text plus a pass/fail privacy report.

### 4.3 Extraction Agent

**Goal:** Produce a structured, evidence-backed record of the offer terms.

**Tools:** `read_section(text, section)`, `verify_quote(quote, document)`, `normalize_amount(text)`, `normalize_duration(text)`, `ask_uploader(field, question)`

**Fields extracted:**

| Field | Example |
|---|---|
| company_name | "Nexora Technologies Pvt Ltd" |
| batch_year | 2026 |
| role | "Graduate Engineer Trainee" |
| ctc_annual | 400000 |
| has_bond | true |
| bond_months | 24 |
| penalty_amount | 150000 |
| penalty_prorated | yes / no / not_mentioned |
| notice_days | 90 |
| training_cost_recovery | true |
| certificates_retained | true |
| other_risky_clauses | ["salary withheld during probation"] |

**Self-verification loop (the core agentic behaviour):**
1. Extract all fields **with an evidence quote** for each value.
2. For each field, call `verify_quote()` to confirm the quote really exists in the document. This catches made-up values.
3. If a quote doesn't exist or the value doesn't match the quote, **re-read that section** and try again.
4. Give each field a confidence score.
5. For fields still below the confidence threshold, **ask the uploader** a short question ("We read the bond as 24 months. Is that correct?").
6. Return the final record with evidence.

### 4.4 Verification Agent

**Goal:** Decide how a new record relates to existing knowledge, and keep the database trustworthy.

**Tools:** `find_company(name)` (fuzzy matching of name variants), `run_readonly_sql(query)`, `compare_records(new, existing)`, `create_conflict(...)`, `send_to_moderation(...)`

**Decisions:**

| Situation | Decision |
|---|---|
| Matches existing records for the same company, batch and role | **Corroborate**: increase the confidence count |
| Different terms, but a different role or batch | **New variant**: store it separately |
| Different terms for the same company, batch and role | **Conflict**: create a conflict record and show it to users |
| Extreme or suspicious values (e.g. ₹50,00,000 penalty) | **Outlier**: hold it for moderator review |
| Company not in the database | **New company**: create it, possibly a duplicate, so flag it for review |

It also recalculates the company summary: typical terms, number of supporting uploads, latest date, and any trend compared with the previous batch.

### 4.5 Q&A Agent

**Goal:** Answer student questions accurately, using only verified data, with sources.

**Tools:**
- `find_company(name)`
- `run_readonly_sql(query)`: text-to-SQL over a **read-only database user** with an automatic `LIMIT`
- `calc_exit_cost(penalty, bond_months, months_served, prorated)`: plain Python, **not the LLM**, so the arithmetic is always right
- `get_evidence(record_id)`

**Rules:**
- Every factual claim must cite record IDs, the number of uploads and the dates.
- If the data is missing or conflicting, say so. Never guess.
- Never give legal advice. Suggest questions to ask HR, or a lawyer for disputes.

**Example:**
> **Q:** If I join Nexora and leave after 10 months, what could I owe?
> **A:** Based on 7 verified 2026 uploads, the bond is 24 months with a ₹1,50,000 penalty. None of the letters mention reducing the penalty for time served, so the full amount may apply. Ask HR about pro-rating before signing. *(Information from uploaded letters, not legal advice.)*

### 4.6 Monitor Agent (Proactive, scheduled daily)

**Goal:** Keep data fresh for companies students care about **right now**.

**Tools:** `get_upcoming_drives()`, `run_readonly_sql(query)`, `web_search(query)`, `fetch_page(url)`, `save_public_source(...)`

**Loop:**
1. Get the companies visiting campus in the next 30 days.
2. For each, check database coverage: no data, old data (previous batch only) or unresolved conflicts.
3. For gaps, search public sources and save findings **separately, labelled "Unverified public source"**. They never overwrite verified records.
4. Create "data needed" requests ("We have no 2026 data for Nexora. Seniors who joined, please upload.").

### 4.7 Alert Agent (Proactive)

**Goal:** Warn students before it's too late.

**Tools:** `get_subscriptions()`, `get_company_summary(company_id)`, `send_email(to, subject, body)`

**Behaviour:**
- 7 days before a drive, it emails subscribed students a short summary of the bond terms, the confidence level, and a link to the company page.
- It decides **whether** an alert is worth sending (e.g. it skips "no bond, high confidence" unless the student opted in to all alerts) to avoid spam.

---

## 5. Shared State (passed between agents)

```python
class UploadState(TypedDict):
    upload_id: str
    raw_text: str                 # in memory only, never stored
    is_scanned: bool
    redacted_text: str
    privacy_passed: bool
    extracted: dict               # field -> {value, quote, confidence}
    needs_user_confirmation: list[str]
    verification_decision: str    # corroborate | variant | conflict | outlier | new_company
    record_id: int | None
    errors: list[str]
    retries: dict[str, int]
    cost_tokens: int
```

LangGraph checkpointing saves this state, so a run can pause (e.g. while waiting for the uploader to confirm a field) and resume later.

---

## 6. Database Design (PostgreSQL)

```sql
CREATE TABLE companies (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    normalized_name TEXT UNIQUE NOT NULL,
    aliases         TEXT[] DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE offer_records (
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

CREATE TABLE evidence (
    id         SERIAL PRIMARY KEY,
    record_id  INT REFERENCES offer_records(id) ON DELETE CASCADE,
    field      TEXT NOT NULL,
    quote      TEXT NOT NULL                   -- redacted clause text only
);

CREATE TABLE conflicts (
    id          SERIAL PRIMARY KEY,
    company_id  INT REFERENCES companies(id),
    batch_year  INT,
    role        TEXT,
    field       TEXT,
    values_seen JSONB,                          -- e.g. {"75000": 2, "150000": 5}
    status      TEXT DEFAULT 'open' CHECK (status IN ('open','resolved')),
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE moderation_queue (
    id         SERIAL PRIMARY KEY,
    record_id  INT REFERENCES offer_records(id),
    reason     TEXT,                            -- outlier | new_company | conflict
    status     TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE placement_drives (
    id         SERIAL PRIMARY KEY,
    company_id INT REFERENCES companies(id),
    college    TEXT,
    drive_date DATE
);

CREATE TABLE users (
    id    SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL
);

CREATE TABLE subscriptions (
    user_id    INT REFERENCES users(id),
    company_id INT REFERENCES companies(id),
    PRIMARY KEY (user_id, company_id)
);

CREATE TABLE agent_runs (                       -- observability
    id          SERIAL PRIMARY KEY,
    workflow    TEXT,                           -- upload | question | monitor
    agent       TEXT,
    steps       JSONB,                          -- tool calls, decisions, retries
    tokens_used INT,
    duration_ms INT,
    status      TEXT,                           -- success | retried | escalated | failed
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Company summary used by the website and Q&A agent
CREATE VIEW company_summary AS
SELECT c.name, r.batch_year, r.role,
       MODE() WITHIN GROUP (ORDER BY r.bond_months)    AS typical_bond_months,
       MODE() WITHIN GROUP (ORDER BY r.penalty_amount) AS typical_penalty,
       COUNT(*)                                        AS supporting_uploads,
       MAX(r.created_at)                               AS latest_upload
FROM offer_records r
JOIN companies c ON c.id = r.company_id
WHERE r.status = 'verified' AND r.source_type = 'upload'
GROUP BY c.name, r.batch_year, r.role;
```

**Important:** the Q&A agent connects with a **read-only database role** that can only `SELECT` from `company_summary`, `offer_records`, `evidence` and `conflicts`.

---

## 7. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Agent orchestration | **LangGraph** | Stateful graphs, conditional routing, loops, checkpoints, human-in-the-loop pauses |
| LLM | **Claude API** (tool use) | Strong document understanding and tool calling. A small, cheap model (e.g. Haiku) for classification and PII checks, a stronger model (e.g. Sonnet) for extraction and Q&A |
| PDF / OCR | pdfplumber + Tesseract (or a vision model for scanned letters) | Text and scanned documents |
| Backend | **FastAPI** (Python) | API for uploads, questions and admin |
| Database | **PostgreSQL** on Neon or Supabase | Free tier, works with serverless |
| Frontend | **Next.js** on **Vercel** | Professional product UI |
| Scheduling | Vercel Cron Jobs or GitHub Actions | Runs the Monitor and Alert agents daily |
| Email | Resend or SendGrid free tier | Alerts |
| Testing | pytest + an evaluation script | Agent benchmark |

**Deployment notes (Vercel):**
- Vercel Functions on the free Hobby plan have a **300-second maximum duration**, which is enough for one upload. Never process many letters in one request.
- Functions have **no persistent file storage**, so letters are processed in memory and discarded. This matches the privacy design.
- **Faster alternative:** if you aren't using React yet, start with a Streamlit frontend on Streamlit Community Cloud. The agents live in a separate Python package, so you can switch frontends later without rewriting them.

---

## 8. Project Structure

```
bondcheck/
├── agents/
│   ├── orchestrator.py      # LangGraph graph: routing, retries, budgets
│   ├── privacy.py
│   ├── extraction.py
│   ├── verification.py
│   ├── qa.py
│   ├── monitor.py
│   └── alert.py
├── tools/
│   ├── documents.py         # extract_text, ocr_image, read_section, verify_quote
│   ├── pii.py               # detect_pii, redact, scan_for_remaining_pii
│   ├── database.py          # find_company, run_readonly_sql, save_record
│   ├── calculator.py        # calc_exit_cost (deterministic)
│   ├── web.py               # web_search, fetch_page
│   └── notify.py            # send_email
├── api/
│   └── main.py              # FastAPI: /upload, /ask, /company/{id}, /admin/queue
├── db/
│   ├── schema.sql
│   └── seed.sql
├── eval/
│   ├── synthetic_letters/   # generated letters with known correct answers
│   ├── ground_truth.json
│   └── run_eval.py          # metrics + single-pass vs agentic comparison
├── frontend/                # Next.js app (or streamlit_app.py)
├── tests/
├── .env.example
└── README.md
```

---

## 9. Guardrails & Safety

| Risk | Guardrail |
|---|---|
| Personal data leak | Privacy Agent with re-scan loop; uploads that fail are rejected; documents never stored |
| Made-up values | Every field needs a quote that `verify_quote()` confirms exists |
| Wrong arithmetic | Exit costs computed by Python code, not the LLM |
| Dangerous SQL | Read-only DB role, `SELECT` only, automatic `LIMIT`, query timeout |
| Fake or malicious uploads | Document-type check, outlier detection, moderation queue |
| Instructions hidden inside uploaded documents | Document text is treated as data only. Agents never follow instructions found inside a letter |
| Misleading answers | Citations, confidence levels and dates shown on every answer; conflicts displayed openly |
| Legal liability | Clear "not legal advice" notice; terms shown as reported by uploads, not as claims about the company |
| Runaway agents | Max 2 retries per agent, token budget per run, every step logged |

---

## 10. Evaluation Plan

An evaluation shows the agents actually work, and it's what makes this project stand out.

**Test set:** 50 **synthetic offer letters** generated with known correct answers (varied formats, wording, scanned versions, tricky clauses, and some with hidden personal details), plus real letters as they come in.

| Metric | Target |
|---|---|
| Field-level extraction accuracy | ≥ 90% |
| PII leak rate (personal data found in stored records) | **0%** |
| Hallucinated values (no supporting quote) | 0% stored |
| Conflict detection (precision / recall) | ≥ 85% |
| Q&A answers with correct citations | ≥ 95% |
| Average cost and time per upload | Measured and reported |

**Key experiment: single-pass LLM vs. agentic loop.** Run both on the same 50 letters:

| | Single-pass extraction | Agentic (self-check + re-read) |
|---|---|---|
| Accuracy | ? | ? |
| Hallucinated fields | ? | ? |
| Cost per letter | ? | ? |

This table shows *why* the agentic design matters, using measured results.

---

## 11. 4-Week Build Plan

### Week 1: Foundations
- [ ] Set up the repo, PostgreSQL (Neon/Supabase) and `schema.sql`
- [ ] Document tools: text extraction, OCR, `verify_quote`
- [ ] Generate 50 synthetic offer letters with `ground_truth.json`
- [ ] Privacy Agent with redaction and re-scan loop

### Week 2: Core agents
- [ ] Extraction Agent with evidence quotes and the self-check loop
- [ ] Verification Agent: fuzzy company matching and the 5 decision types
- [ ] Orchestrator in LangGraph: routing, retries, budget, logging to `agent_runs`
- [ ] First evaluation run

### Week 3: Users and proactive agents
- [ ] Q&A Agent: read-only SQL, exit-cost calculator, citations
- [ ] FastAPI endpoints
- [ ] Frontend: upload page, company page, Q&A chat, moderation queue
- [ ] Monitor and Alert agents with a daily cron job

### Week 4: Launch and proof
- [ ] Deploy (Vercel + Neon, or Streamlit Cloud)
- [ ] Collect real data from your batch and seniors (goal: 30–50 letters)
- [ ] Final evaluation and the single-pass vs. agentic comparison
- [ ] README with architecture diagram, results table and a 2–3 minute demo video

---

## 12. Final Outputs

1. **Live web app:** upload letters, browse company pages, ask questions, subscribe to alerts
2. **Verified dataset** of anonymised bond terms, the project's unique asset
3. **Evaluation report** with measured accuracy, privacy and cost results
4. **GitHub repo** with clean code, tests and documentation
5. **Demo video** for your resume and LinkedIn

---

## 13. Resume Description

> **BondCheck — Agentic AI Platform for Job Bond Transparency**
> Built a multi-agent system (LangGraph, Claude API, FastAPI, PostgreSQL) in which 7 specialised agents redact personal data, extract offer-letter terms with quote-verified self-checking, detect conflicting reports, answer questions with cited SQL-backed answers, and proactively alert students before placement drives. The agentic extraction loop improved accuracy from X% to Y% over single-pass extraction, with a 0% PII leak rate across 50 test documents.

*(Fill in X and Y with your measured results.)*

---

## 14. Future Extensions

- WhatsApp bot so students can ask questions without opening the website
- Hindi and Telugu support for questions and alerts
- Placement-cell dashboard with season-wide bond statistics
- Coverage beyond bonds: internship stipends, relocation clauses, probation terms
- A public, anonymised yearly report on bond trends

---

*BondCheck shows information reported in uploaded documents and public sources. It is not legal advice.*
