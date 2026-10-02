# BondCheck: an agentic AI platform for job-bond transparency

> AI agents that read offer letters, extract and verify job-bond terms, and warn freshers **before** they sign.

Seven specialised agents turn anonymously uploaded offer letters into a verified, evidence-backed, searchable database of bond terms, answer students' questions with citations, and proactively alert them before placement drives.

| | |
|---|---|
| **Agents** | Orchestrator · Privacy · Extraction · Verification · Q&A · Monitor · Alert |
| **Stack** | LangGraph · Claude API (Haiku + Sonnet) · FastAPI · PostgreSQL / SQLite · Next.js 16 + Tailwind 4 + Framer Motion |
| **Runs without an API key** | Yes. A deterministic offline engine drives the same agent graph, so everything works locally out of the box. |

All demo companies and people are fictional. BondCheck shows information reported in uploaded documents and public sources. It is not legal advice.

---

## Quick start

**Backend** (Python 3.12):

```bash
cd bondcheck
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # optional: add ANTHROPIC_API_KEY, DATABASE_URL, …
python -m db.seed                 # runs ~70 synthetic letters through the real agent pipeline
uvicorn api.main:app --port 8000  # API docs at http://localhost:8000/docs
```

**Frontend** (Node 20+):

```bash
cd bondcheck/frontend
npm install
cp .env.example .env.local        # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                       # http://localhost:3000
```

Moderator console: `http://localhost:3000/admin` (local token: `dev-admin-token`).

**Tests and evaluation:**

```bash
pytest -q                         # 35 tests: tools, agents, guardrails, API
python -m eval.run_eval           # writes eval/results.json + eval/report.md (shown on /how-it-works)
```

### Modes

| Setting | Effect |
|---|---|
| No `ANTHROPIC_API_KEY` | **Offline rule engine** for classification, PII detection and extraction; a deterministic planner for Q&A; web search disabled; scanned letters need Tesseract. |
| `ANTHROPIC_API_KEY` set | `claude-haiku-4-5` classifies documents, double-checks PII and transcribes scans; `claude-sonnet-5-5` extracts fields (structured JSON output), answers questions in a tool-use loop and researches public sources with web search. Sonnet calls opt in to server-side refusal fallbacks. |
| No `DATABASE_URL` | Local SQLite at `data/bondcheck.db` (auto-created and seeded on first API start). |
| `DATABASE_URL` set | PostgreSQL (Neon/Supabase). Run `db/schema.sql`, then optionally `db/seed.sql`. Create the read-only Q&A role from the bottom of `schema.sql` and put it in `DATABASE_URL_READONLY`. |

---

## Architecture

```
                        ┌──────────────────────────────┐
   Events ─────────────▶│      ORCHESTRATOR AGENT      │  LangGraph state graph:
   • New upload         │  plans, routes, retries (≤2), │  routing, retries, token budget,
   • Student question   │  budgets, escalates to humans │  interrupt() for human input
   • Scheduled job      └──────────────┬───────────────┘
   ┌─────────────────┬─────────────────┼──────────────────┬─────────────────┐
   ▼                 ▼                 ▼                  ▼                 ▼
 PRIVACY ──▶    EXTRACTION ──▶   VERIFICATION         Q&A AGENT        MONITOR ──▶ ALERT
 redact +       quote-verified    corroborate /        read-only SQL,   (daily)      (7 days before
 re-scan ×3     self-check loop   variant / conflict / exit-cost calc,               a drive)
                    │             outlier / new_company citations
                    ▼                   ▼
            uploader confirms     moderation queue        PostgreSQL + agent_runs log
```

**Workflow A, upload.** `intake → [ocr] → classify → privacy → extraction ⟲ → [confirm: interrupt()] → verification → finalize (document deleted)`. Any step can route to `reject` (not an offer letter, PII left after 3 scans, unreadable) or `escalate` (failed after 2 retries, over the token budget). Every event streams to the UI as NDJSON.

**Workflow B, question.** The Q&A agent calls `find_company`, `run_readonly_sql`, `calc_exit_cost` and `get_evidence`, and must cite record IDs, upload counts and dates.

**Workflow C, monitoring.** The Monitor agent checks drives in the next 30 days for missing, stale or conflicting data, saves public findings as *unverified* records, and creates "data needed" requests. The Alert agent emails subscribers 7 days before a drive, and skips "no bond, high confidence" alerts unless the student opted in.

### The self-verification loop (Extraction Agent)

1. Extract all 12 fields, each with a verbatim evidence quote.
2. `verify_quote()` confirms every quote exists in the (redacted) document, which catches made-up values.
3. Re-derive the value from the quote with deterministic normalisers (`₹1.5 lakh` → 150000, `two (2) years` → 24).
4. Check relevance and consistency: a probation clause isn't a bond, a salary isn't a penalty, "no bond" isn't a bond, a bond needs a period or a penalty.
5. Re-read just the failing section with the failure as feedback (max 2 rounds).
6. Drop anything whose quote can't be found; ask the uploader about the rest.

---

## Evaluation (offline engine, 50 synthetic letters)

| | Single-pass extraction | Agentic (self-check + re-read) | + uploader confirmation |
|---|---|---|---|
| Field accuracy | 88.5% | **99.6%** | 100% |
| Hallucinated fields | 22 | **0** | — |

| Metric | Target | Result |
|---|---|---|
| Field-level extraction accuracy | ≥ 90% | 99.6% |
| PII leak rate (stored records) | 0% | 0% (0 of 335 planted items; also 0 left in redacted text) |
| Hallucinated values stored | 0% | 0% |
| Conflict detection precision / recall | ≥ 85% | 100% / 100% |
| Q&A answers with correct citations | ≥ 95% | 100% (24 questions) |
| Time per upload | measured | ~0.01 s offline (0 tokens) |

**Read these honestly.** The test letters come from the same generator the extraction rules were developed against (different random seeds), so this is an upper bound. The 5 scanned letters were skipped because no OCR was available. Add real, consented letters to `eval/` and re-run with `ANTHROPIC_API_KEY` set to get the Claude numbers, plus cost per letter.

---

## Project structure

```
bondcheck/
├── agents/          orchestrator.py (LangGraph) · privacy · extraction · verification · qa · monitor · alert
├── tools/           documents (extract_text, ocr_image, read_section, verify_quote) · pii · database
│                    (find_company, run_readonly_sql, save_record, moderation) · calculator · normalize · web · notify
├── core/            config · llm (Claude wrapper, token budget) · state (UploadState) · runlog (events + agent_runs)
├── api/main.py      FastAPI: /upload, /upload/{id}/confirm, /ask, /companies, /company/{id}, /drives,
│                    /subscribe, /samples, /admin/*, /cron/*
├── db/              schema.sql (PostgreSQL) · schema_sqlite.sql · seed.py → seed.sql
├── eval/            letters.py (synthetic generator) · synthetic_letters/ · ground_truth.json · run_eval.py
├── tests/           pytest suite
├── frontend/        Next.js app: home, companies, company page, upload (live agent run), ask, drives, how-it-works, admin
├── .github/workflows/agents-cron.yml   daily Monitor + Alert (alternative to Vercel Cron)
└── Dockerfile       API image (includes Tesseract)
```

Additions beyond the design doc's schema: `moderation_queue.note`, `users.alert_all`, `agent_runs.run_ref`, and the `data_requests` and `alerts_sent` tables, which the Monitor and Alert agents need. `company_summary` also exposes `company_id`.

## Guardrails

| Risk | Guardrail |
|---|---|
| Personal data leak | Redact → independent re-scan with broader rules → redact again; reject after 3 failures. Files are processed in memory, and raw text leaves the graph state right after the Privacy Agent. |
| Made-up values | Every stored value needs a quote that `verify_quote()` finds; otherwise it's dropped. |
| Wrong arithmetic | `calc_exit_cost` is plain Python. |
| Dangerous SQL | SELECT-only, single statement, table allow-list, automatic LIMIT, timeout, read-only connection (SQLite authorizer / Postgres read-only role). |
| Fake uploads | Document-type check, outlier rules, moderation queue. |
| Prompt injection in letters | Letter text is wrapped as data with an explicit rule; instruction-like text is flagged in the run log. |
| Runaway agents | ≤ 2 retries per step, token budget per run, recursion limit, every step logged to `agent_runs`. |

## Deployment

- **Frontend:** deploy `frontend/` to Vercel. Set `NEXT_PUBLIC_API_URL` and `CRON_SECRET`; `vercel.json` schedules the Monitor and Alert agents daily through `/api/cron/[job]`.
- **API:** `docker build -t bondcheck-api .` and run on Render, Railway, Fly.io or Cloud Run with `DATABASE_URL`, `ANTHROPIC_API_KEY`, `ADMIN_TOKEN`, `CRON_SECRET`, `RESEND_API_KEY`, `CORS_ORIGINS`. Alternatively use the GitHub Actions cron in `.github/workflows`.
- **Pause/resume note:** uploads waiting for confirmation live in an in-memory LangGraph checkpointer, so documents never touch disk. Run a single API instance, or swap in a shared checkpointer that stores only redacted text.

## Resume line

> Built a multi-agent system (LangGraph, Claude API, FastAPI, PostgreSQL, Next.js) in which 7 specialised agents redact personal data, extract offer-letter terms with quote-verified self-checking, detect conflicting reports, answer questions with cited SQL-backed answers, and proactively alert students before placement drives. The agentic extraction loop improved field accuracy from 88.5% to 99.6% over single-pass extraction and cut hallucinated fields from 22 to 0, with a 0% PII leak rate across 50 synthetic test documents.

*(Re-measure with the Claude engine and real letters before using these numbers publicly.)*
