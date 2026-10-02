"""Seed the database by running synthetic letters through the real agent pipeline.

    python -m db.seed            # reset + seed (SQLite, or Postgres if DATABASE_URL is set)
    python -m db.seed --export   # also write db/seed.sql (PostgreSQL INSERTs of the seeded data)

The seed data is produced by the agents themselves (Orchestrator -> Privacy -> Extraction ->
Verification), so evidence quotes, decisions and agent_runs logs are all genuine. Uploader
confirmations are answered from the letters' ground truth, and moderator approvals are simulated
for each company's first upload. All companies and people are fictional.
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, datetime, timedelta, timezone

from agents import alert, monitor, orchestrator
from core.config import DATA_DIR, ROOT
from core.runlog import RunContext
from eval.letters import COMPANIES, Letter, make_letter, render_pdf
from tools import database as db

SAMPLES_DIR = DATA_DIR / "samples"

# short name -> [(batch, number of uploads, overrides)]
PLAN = {
    "Nexora Technologies": [(2025, 3, {"penalty": 100000}), (2026, 7, {})],
    "Quantiva Systems": [(2026, 4, {})],
    "Brightloom Infotech": [(2025, 2, {}), (2026, 5, {})],
    "Veltrix Solutions": [(2026, 4, {})],
    "Cognivista Labs": [(2026, 3, {})],
    "Zentrova Software": [(2025, 1, {}), (2026, 3, {})],
    "Aarohan Digital": [(2025, 3, {})],
    "Trinetra Analytics": [(2026, 3, {})],
    "Orbitel Networks": [(2025, 2, {"penalty": 200000}), (2026, 3, {})],
    "Lumenstack Technologies": [(2026, 5, {})],
    "Corvanta Systems": [(2026, 4, {})],
    "Sahyadri CloudWorks": [(2026, 2, {})],
    "Finlogic Microsystems": [(2025, 2, {}), (2026, 3, {})],
    "Pixelmint Studios": [(2026, 2, {})],
    "Indigrid Consulting": [(2026, 3, {})],
    "Rivanta Infotech": [(2026, 3, {}), (2026, 2, {"penalty": 75000})],
}

NEW_COMPANY = dict(name="Stellarbyte Technologies Pvt. Ltd.", short="Stellarbyte Technologies", city="Chennai",
                   roles=["Junior Software Engineer"], ctc=[380000], bond=24, penalty=175000, prorated="not_mentioned",
                   notice=60, training=False, certs=False, risky=[])

DRIVES = [  # short name, days from today, college
    ("Nexora Technologies", 5, "Hyderabad Pool Campus Drive"),
    ("Veltrix Solutions", 4, "Bengaluru Off-Campus Drive"),
    ("Aarohan Digital", 6, "Ahmedabad Pool Campus Drive"),
    ("Stellarbyte Technologies", 9, "Chennai Joint Campus Drive"),
    ("Rivanta Infotech", 12, "Vizag Pool Campus Drive"),
    ("Brightloom Infotech", 18, "Chennai Pool Campus Drive"),
    ("Quantiva Systems", 25, "Pune Joint Campus Drive"),
    ("Corvanta Systems", 29, "Coimbatore Campus Drive"),
    ("Lumenstack Technologies", 41, "Bengaluru Pool Campus Drive"),
]

USERS = [
    ("aarav.student@example.com", False, ["Nexora Technologies", "Aarohan Digital", "Veltrix Solutions"]),
    ("diya.cse26@example.com", True, ["Veltrix Solutions", "Rivanta Infotech", "Nexora Technologies"]),
    ("placement.cell@example.com", True, ["Stellarbyte Technologies", "Brightloom Infotech"]),
]


def by_short(short: str) -> dict:
    return next(c for c in COMPANIES if c["short"] == short)


def answer_from_truth(questions: list[dict], truth: dict) -> dict:
    """Simulated uploader: confirms correct readings, corrects wrong ones."""
    answers = {}
    for q in questions:
        f, cur, true = q["field"], q.get("current"), truth.get(q["field"])
        if cur is not None and cur == true:
            answers[f] = "yes"
        elif true is None:
            answers[f] = "not in letter"
        elif isinstance(true, bool):
            answers[f] = "yes" if true else "no"
        else:
            answers[f] = str(true)
    return answers


def run_letter(letter: Letter, scanned: bool = False) -> dict:
    pdf = render_pdf(letter.text, scanned=scanned, seed=hash(letter.id) % 1000)
    ctx = orchestrator.start_upload(pdf, f"{letter.id}.pdf", background=False)
    res = ctx.result
    if res["status"] == "needs_confirmation":
        ctx = orchestrator.resume_upload(res["upload_id"], answer_from_truth(res["questions"], letter.truth),
                                         background=False)
        res = ctx.result
    return res


def approve_pending(record_id: int) -> None:
    item = db.query_one("SELECT id FROM moderation_queue WHERE record_id = ? AND status = 'pending'", [record_id])
    if item:
        db.resolve_queue_item(item["id"], "approve", note="seed: approved first upload")


def spread_dates(rng: random.Random) -> None:
    today = date.today()
    for r in db.query("SELECT id, batch_year FROM offer_records"):
        start = date(r["batch_year"], 1, 15)
        end = min(date(r["batch_year"], 9, 20), today - timedelta(days=2))
        d = start + timedelta(days=rng.randint(0, max(0, (end - start).days)))
        ts = datetime(d.year, d.month, d.day, rng.randint(8, 22), rng.randint(0, 59), tzinfo=timezone.utc)
        db.update("offer_records", r["id"], {"created_at": ts.strftime("%Y-%m-%dT%H:%M:%SZ")})


def write_samples(rng: random.Random) -> None:
    """Demo letters for the website's 'try a sample' buttons."""
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    samples = []

    def add(key, title, desc, letter_text, scanned=False, expect=""):
        (SAMPLES_DIR / f"{key}.pdf").write_bytes(render_pdf(letter_text, scanned=scanned, seed=len(samples)))
        samples.append({"key": key, "title": title, "description": desc, "expect": expect, "scanned": scanned})

    L = make_letter(901, rng, by_short("Nexora Technologies"), 2026, "formal")
    add("nexora_2026_offer", "Nexora 2026 offer letter", "A standard appointment letter with a 24-month bond.",
        L.text, expect="corroborate")
    L = make_letter(902, rng, by_short("Rivanta Infotech"), 2026, "annexure", overrides={"penalty": 90000})
    add("rivanta_conflicting_terms", "Rivanta letter with different terms",
        "Reports a different penalty from earlier uploads.", L.text, expect="conflict")
    L = make_letter(903, rng, by_short("Orbitel Networks"), 2026, "tricky")
    add("orbitel_tricky_clauses", "Orbitel letter with tricky clauses",
        "Probation, a training stipend and the bond are all in different clauses.", L.text, expect="self-correction")
    L = make_letter(904, rng, by_short("Trinetra Analytics"), 2026, "email")
    add("trinetra_no_bond", "Trinetra email offer (no bond)", "An email-style offer without a bond.", L.text,
        expect="variant/corroborate")
    unclear = make_letter(905, rng, by_short("Pixelmint Studios"), 2026, "formal").text
    unclear = unclear.replace(
        next(line for line in unclear.split("\n") if "liquidated damages" in line or "bond amount" in line
             or "sum of" in line),
        "4. You agree to serve the Company for a minimum period of 12 months. If you leave earlier, you shall be "
        "liable to pay liquidated damages as determined by the management.")
    add("pixelmint_unclear_penalty", "Pixelmint letter with an unclear penalty",
        "The penalty amount is not written in the letter, so the agent asks you.", unclear, expect="asks uploader")
    L = make_letter(906, rng, NEW_COMPANY, 2026, "table")
    add("stellarbyte_new_company", "Stellarbyte offer (new company)", "A company BondCheck hasn't seen yet.", L.text,
        expect="new_company")
    L = make_letter(907, rng, by_short("Brightloom Infotech"), 2026, "formal")
    add("brightloom_scanned", "Scanned Brightloom letter", "An image-only scan that needs OCR.", L.text, scanned=True,
        expect="ocr")
    add("not_an_offer_letter", "A college fee receipt", "Not an offer letter; the Orchestrator should reject it.",
        "SRI SAI COLLEGE OF ENGINEERING\nFEE RECEIPT\nReceipt No: 2026/4471\nReceived with thanks the semester fee "
        "of Rs. 85,000 for the academic year 2026-27.\nMode of payment: UPI\nThis is a computer generated receipt.",
        expect="rejected")
    (SAMPLES_DIR / "samples.json").write_text(json.dumps(samples, indent=2), encoding="utf-8")


def seed(verbose: bool = True) -> dict:
    rng = random.Random(2026)
    db.init_db(reset=True)
    stats: dict[str, int] = {}
    idx = 0
    seen_companies: set[str] = set()

    def log(msg):
        if verbose:
            print(msg)

    plan = list(PLAN.items())
    for short, batches in plan:
        co = by_short(short)
        for batch, n, overrides in batches:
            for _ in range(n):
                idx += 1
                L = make_letter(idx, rng, co, batch, overrides=overrides)
                res = run_letter(L)
                d = res.get("decision") or res["status"]
                stats[d] = stats.get(d, 0) + 1
                if res.get("decision") == "new_company" and short not in seen_companies:
                    approve_pending(res["record_id"])
                seen_companies.add(short)
                log(f"  {L.id} {short:<24} {batch} {L.template:<9} -> {d}")

    # A new company (stays in the moderation queue) and an outlier (held for review).
    res = run_letter(make_letter(idx + 1, rng, NEW_COMPANY, 2026, "formal"))
    log(f"  new company -> {res.get('decision')}")
    res = run_letter(make_letter(idx + 2, rng, by_short("Zentrova Software"), 2026, "formal",
                                 overrides={"penalty": 5000000}))
    log(f"  outlier -> {res.get('decision')}")

    spread_dates(rng)

    # Placement drives, students and subscriptions.
    ids = {c["name"]: c["id"] for c in db.query("SELECT id, name FROM companies")}

    def cid(short):
        return next(v for k, v in ids.items() if k.startswith(short.split()[0]))

    for short, days, college in DRIVES:
        db.insert("placement_drives", {"company_id": cid(short), "college": college,
                                       "drive_date": (date.today() + timedelta(days=days)).isoformat()})
    for email, alert_all, subs in USERS:
        uid = db.insert("users", {"email": email, "alert_all": alert_all})
        for s in subs:
            db.execute("INSERT INTO subscriptions (user_id, company_id) VALUES (?, ?)", [uid, cid(s)])

    # One run of each proactive agent so the dashboard has real logs.
    m = monitor.run(RunContext("monitor"))
    a = alert.run(RunContext("alert"))
    log(f"  monitor: {m['requests']} data requests; alert: {a['sent']} sent, {a['skipped']} skipped")

    write_samples(random.Random(99))
    stats["companies"] = len(ids)
    stats["records"] = db.query_one("SELECT COUNT(*) AS n FROM offer_records")["n"]
    return stats


# ---------------------------------------------------------------- export for PostgreSQL

EXPORT_TABLES = ["companies", "offer_records", "evidence", "conflicts", "moderation_queue", "placement_drives",
                 "users", "subscriptions", "data_requests"]


def _lit(col: str, v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    if col == "aliases":
        items = ",".join('"' + str(a).replace('"', '\\"') + '"' for a in v)
        return "'{" + items.replace("'", "''") + "}'"
    if isinstance(v, (list, dict)):
        return "'" + json.dumps(v).replace("'", "''") + "'::jsonb"
    return "'" + str(v).replace("'", "''") + "'"


def export_sql() -> str:
    lines = ["-- Generated by `python -m db.seed --export` from the agent-seeded database. Fictional data.",
             "BEGIN;"]
    for t in EXPORT_TABLES:
        rows = db.query(f"SELECT * FROM {t} ORDER BY 1")
        for r in rows:
            cols = list(r)
            vals = ", ".join(_lit(c, r[c]) for c in cols)
            lines.append(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({vals});")
        if rows and "id" in rows[0]:
            lines.append(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), (SELECT MAX(id) FROM {t}));")
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    print(seed(verbose=not args.quiet))
    if args.export:
        (ROOT / "db" / "seed.sql").write_text(export_sql(), encoding="utf-8")
        print("wrote db/seed.sql")
