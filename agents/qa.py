"""Q&A Agent. Goal: answer student questions accurately, using only verified data, with sources.

Tools: find_company, run_readonly_sql (read-only role, auto LIMIT), calc_exit_cost (plain Python),
get_evidence. Every factual claim cites record IDs, the number of uploads and dates. Missing or
conflicting data is said out loud. Never legal advice.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date

from core import llm
from core.config import settings
from core.runlog import RunContext
from tools import database as db
from tools.calculator import calc_exit_cost, inr

A = "Q&A Agent"
DISCLAIMER = "Information from uploaded letters, not legal advice."

SCHEMA_DOC = """Tables you may query (read-only, SELECT only, automatic LIMIT):
- company_summary(company_id, name, batch_year, role, typical_bond_months, typical_penalty, supporting_uploads, latest_upload)
  -- verified uploads only
- offer_records(id, company_id, batch_year, role, ctc_annual, has_bond, bond_months, penalty_amount,
  penalty_prorated ['yes'|'no'|'not_mentioned'], notice_days, training_cost_recovery, certificates_retained,
  other_risky_clauses (JSON list), source_type ['upload'|'public_web'], source_url, confidence,
  status ['pending'|'verified'|'rejected'], created_at)
  -- only use status='verified' AND source_type='upload' for facts; public_web rows are unverified
- evidence(id, record_id, field, quote)   -- redacted clause text supporting each field
- conflicts(id, company_id, batch_year, role, field, values_seen (JSON {value: count}), status ['open'|'resolved'])
Join company names via company_summary.company_id = offer_records.company_id."""

SYSTEM = f"""You are BondCheck's Q&A agent. You help Indian students understand job-bond terms before they sign.

Rules:
- Use only data returned by your tools. Never guess or rely on outside knowledge about companies.
- Every factual claim must cite the record IDs, the number of verified uploads and the upload dates,
  e.g. "(records #12, #15; 7 verified 2026 uploads, latest 2026-08-14)".
- If data is missing, old, or conflicting, say so plainly. Show conflicting values with their counts.
- For any "what would I owe" question call calc_exit_cost. Never do the arithmetic yourself.
- Never give legal advice. Suggest questions to ask HR, or a lawyer for disputes.
- Be brief and friendly: 2-6 sentences, plain language, amounts in Indian format (₹1,50,000).
- End with: "({DISCLAIMER})"

{SCHEMA_DOC}"""

TOOLS = [
    {"name": "find_company", "description": "Fuzzy-find companies by name (handles variants like 'Nexora Tech Pvt Ltd'). "
                                            "Returns [{id, name, score}].",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["name"],
                      "properties": {"name": {"type": "string"}}}},
    {"name": "run_readonly_sql", "description": "Run one read-only SELECT over company_summary, offer_records, "
                                                "evidence, conflicts. A LIMIT is added automatically.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["query"],
                      "properties": {"query": {"type": "string"}}}},
    {"name": "calc_exit_cost", "description": "Deterministic exit-cost calculator. prorated is 'yes', 'no' or "
                                              "'not_mentioned'.",
     "input_schema": {"type": "object", "additionalProperties": False,
                      "required": ["penalty", "bond_months", "months_served", "prorated"],
                      "properties": {"penalty": {"type": "integer"}, "bond_months": {"type": "integer"},
                                     "months_served": {"type": "number"},
                                     "prorated": {"type": "string", "enum": ["yes", "no", "not_mentioned"]}}}},
    {"name": "get_evidence", "description": "A record with its evidence quotes.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["record_id"],
                      "properties": {"record_id": {"type": "integer"}}}},
]


class Citations:
    """Collects the record IDs the answer is based on, from tool outputs."""

    def __init__(self):
        self.records: dict[int, dict] = {}

    def add_rows(self, rows: list[dict]) -> None:
        for r in rows:
            if "id" in r and ("batch_year" in r or "bond_months" in r):
                self.records[r["id"]] = r

    def as_list(self) -> list[dict]:
        return [{"record_id": rid, "batch_year": r.get("batch_year"), "role": r.get("role"),
                 "created_at": r.get("created_at"), "company_id": r.get("company_id")}
                for rid, r in sorted(self.records.items())]


def _execute(name: str, args: dict, cites: Citations, ctx: RunContext):
    if name == "find_company":
        out = db.find_company(args["name"])
    elif name == "run_readonly_sql":
        out = db.run_readonly_sql(args["query"])
        cites.add_rows(out)
    elif name == "calc_exit_cost":
        out = calc_exit_cost(args["penalty"], args["bond_months"], args["months_served"], args.get("prorated", "not_mentioned"))
    elif name == "get_evidence":
        out = db.get_evidence(int(args["record_id"]))
        cites.add_rows([out])
    else:
        raise ValueError(f"unknown tool {name}")
    ctx.emit(A, "tool", f"{name}({json.dumps(args, ensure_ascii=False)[:140]})",
             rows=len(out) if isinstance(out, list) else None)
    return out


def answer(question: str, ctx: RunContext, history: list[dict] | None = None) -> dict:
    with ctx.agent(A):
        cites = Citations()
        if settings.offline:
            text = _offline_answer(question, ctx, cites)
        else:
            msgs = [*(history or [])[-6:], {"role": "user", "content": question}]
            text = llm.tool_loop(model=settings.strong_model, system=SYSTEM, messages=msgs, tools=TOOLS,
                                 execute=lambda n, a: _execute(n, a, cites, ctx), meter=ctx.meter, max_turns=8)
        if DISCLAIMER.lower() not in text.lower():
            text = f"{text.rstrip()}\n\n*({DISCLAIMER})*"
        cited_in_text = {int(x) for x in re.findall(r"#(\d+)", text)}
        citations = [c for c in cites.as_list() if c["record_id"] in cited_in_text] or cites.as_list()[:10]
        ctx.emit(A, "done", f"Answered with {len(citations)} cited record(s)")
        return {"answer": text, "citations": citations, "tokens": ctx.meter.used}


# --------------------------------------------------------------------------- offline planner

_MONTHS = re.compile(r"(?i)(?:after|within|in|at)\s+(\d+(?:\.\d+)?)\s*(months?|years?|yrs?)")


def _detect_company(question: str) -> dict | None:
    words = re.findall(r"[A-Za-z][A-Za-z0-9&.]+", question)
    cands = []
    for n in range(3, 0, -1):
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i:i + n])
            for m in db.find_company(phrase, limit=1):
                if m["score"] >= 88:
                    cands.append((m["score"] + n, m))
    return max(cands, key=lambda x: x[0])[1] if cands else None


def _fmt_cite(records: list[dict]) -> str:
    records = sorted(records, key=lambda r: r["id"])
    ids = ", ".join(f"#{r['id']}" for r in records[:6]) + (" …" if len(records) > 6 else "")
    latest = max(str(r["created_at"])[:10] for r in records)
    return f"records {ids}; latest upload {latest}"


def _offline_answer(q: str, ctx: RunContext, cites: Citations) -> str:
    ql = q.lower()
    company = _detect_company(q)
    ctx.emit(A, "tool", f"find_company → {company['name'] if company else 'no company named'}")

    if not company:
        if re.search(r"no bond|without (a )?bond|bond.?free", ql):
            rows = db.run_readonly_sql(
                "SELECT s.name, s.batch_year, COUNT(r.id) AS n, MAX(r.created_at) AS latest "
                "FROM company_summary s JOIN offer_records r ON r.company_id = s.company_id "
                "AND r.batch_year = s.batch_year AND r.status = 'verified' AND r.source_type = 'upload' "
                "WHERE s.typical_bond_months IS NULL OR s.typical_bond_months = 0 "
                "GROUP BY s.name, s.batch_year ORDER BY n DESC")
            ctx.emit(A, "tool", f"run_readonly_sql: companies with no bond → {len(rows)} rows")
            if not rows:
                return "I couldn't find verified uploads showing a no-bond offer yet."
            lst = "; ".join(f"{r['name']} ({r['batch_year']}, {r['n']} uploads)" for r in rows[:8])
            return f"Verified uploads with no bond: {lst}. Check each company page for the evidence quotes."
        if re.search(r"highest|harsh|worst|biggest|largest|strict", ql):
            rows = db.run_readonly_sql(
                "SELECT name, batch_year, role, typical_bond_months, typical_penalty, supporting_uploads "
                "FROM company_summary WHERE typical_penalty IS NOT NULL ORDER BY typical_penalty DESC")
            ctx.emit(A, "tool", f"run_readonly_sql: highest penalties → {len(rows)} rows")
            lst = "; ".join(f"{r['name']} {r['batch_year']}: {r['typical_bond_months']} months / "
                            f"{inr(r['typical_penalty'])} ({r['supporting_uploads']} uploads)" for r in rows[:5])
            return f"Highest typical bond penalties in verified uploads: {lst}."
        return ("I couldn't tell which company you mean, or it isn't in BondCheck yet. Try the full company name "
                "(for example “Nexora Technologies”). If it's missing, a senior's upload would help everyone.")

    recs = db.run_readonly_sql(
        "SELECT id, company_id, batch_year, role, ctc_annual, has_bond, bond_months, penalty_amount, penalty_prorated, "
        "notice_days, training_cost_recovery, certificates_retained, other_risky_clauses, created_at "
        "FROM offer_records WHERE company_id = ? AND status = 'verified' AND source_type = 'upload' "
        "ORDER BY batch_year DESC, created_at DESC", [company["id"]])
    ctx.emit(A, "tool", f"run_readonly_sql: {len(recs)} verified records for {company['name']}")
    cites.add_rows(recs)
    conflicts = db.run_readonly_sql("SELECT field, batch_year, values_seen FROM conflicts "
                                    "WHERE company_id = ? AND status = 'open'", [company["id"]])
    if not recs:
        pub = db.query("SELECT source_url FROM offer_records WHERE company_id = ? AND source_type = 'public_web'",
                       [company["id"]])
        extra = f" There are {len(pub)} unverified public source(s) on the company page." if pub else ""
        return (f"We don't have any verified uploads for {company['name']} yet, so I can't say what its bond terms "
                f"are.{extra} Ask HR for the service agreement in writing before you accept.")

    year_m = re.search(r"\b(20\d{2})\b", q)
    batch = int(year_m.group(1)) if year_m else recs[0]["batch_year"]
    group = [r for r in recs if r["batch_year"] == batch] or recs
    batch = group[0]["batch_year"]
    n = len(group)
    bonded = [r for r in group if r["has_bond"]]
    stale = batch < date.today().year
    parts: list[str] = []
    if not bonded:
        parts.append(f"Based on {n} verified {batch} upload(s), {company['name']} letters show no bond "
                     f"({_fmt_cite(group)}).")
    else:
        months = Counter(r["bond_months"] for r in bonded if r["bond_months"]).most_common()
        pens = Counter(r["penalty_amount"] for r in bonded if r["penalty_amount"]).most_common()
        bm, pen = (months[0][0] if months else None), (pens[0][0] if pens else None)
        pr = Counter(r["penalty_prorated"] for r in bonded).most_common(1)[0][0]
        parts.append(f"Based on {n} verified {batch} upload(s), the bond is {bm} months with a {inr(pen)} penalty "
                     f"({_fmt_cite(group)}).")
        if len(pens) > 1 or len(months) > 1:
            seen = ", ".join(f"{inr(v)} in {c}" for v, c in pens) if len(pens) > 1 else \
                ", ".join(f"{v} months in {c}" for v, c in months)
            parts.append(f"Uploads disagree: {seen} letter(s), so treat this as uncertain.")
        m = _MONTHS.search(q)
        if m or re.search(r"owe|leave|quit|exit|break|resign", ql):
            served = float(m.group(1)) * (12 if m and m.group(2).startswith("y") else 1) if m else 0
            calc = calc_exit_cost(pen, bm, served, pr)
            ctx.emit(A, "tool", f"calc_exit_cost(penalty={pen}, bond_months={bm}, months_served={served:g}, "
                                f"prorated={pr}) → {calc['amount']}")
            if m:
                parts.append(f"If you leave after {served:g} months: {calc['explanation']}")
            else:
                parts.append(calc["explanation"].replace("Full penalty", "Leaving early could cost the full penalty"))
            if pr != "yes" and "Ask HR" not in parts[-1]:
                parts.append("Ask HR whether the penalty is pro-rated before signing.")
        risky = Counter(c for r in group for c in (r.get("other_risky_clauses") or []))
        if risky:
            parts.append("Other clauses reported: " + ", ".join(f"{c} ({k}/{n})" for c, k in risky.most_common(3)) + ".")
        certs = sum(1 for r in group if r.get("certificates_retained"))
        if certs:
            parts.append(f"{certs} of {n} letters say original certificates are kept by the company.")
    if conflicts:
        parts.append(f"There {'is' if len(conflicts) == 1 else 'are'} {len(conflicts)} open conflict(s) on this "
                     f"company's page.")
    if stale:
        parts.append(f"Note: the latest data is from the {batch} batch; terms may have changed.")
    return " ".join(parts)
