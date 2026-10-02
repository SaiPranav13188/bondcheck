"""BondCheck API (FastAPI).

Public:  /upload, /upload/{id}/confirm, /ask, /companies, /company/{id}, /drives, /subscribe, /samples, /stats
Admin:   /admin/queue, /admin/conflicts, /admin/runs, /admin/overview, /admin/drives  (X-Admin-Token)
Cron:    /cron/monitor, /cron/alerts  (Authorization: Bearer CRON_SECRET, as sent by Vercel Cron)

Upload and ask stream NDJSON: one JSON event per line while the agents work, then a final
{"kind": "result", ...} line.
"""
from __future__ import annotations

import json
import logging
import queue
import re
import threading
from collections import Counter
from contextlib import asynccontextmanager
from datetime import date, timedelta
from statistics import median
from typing import Iterator

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, EmailStr, Field

from agents import alert, monitor, orchestrator, qa
from core import runlog
from core.config import ROOT, settings
from core.runlog import RunContext
from tools import database as db
from tools.calculator import calc_exit_cost

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("bondcheck.api")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not settings.offline:
        from core.llm import verify_credentials

        reason = verify_credentials()
        if reason:  # a bad key would make every agent call fail; run the offline engine instead
            log.warning("%s: falling back to the offline rule engine", reason)
            object.__setattr__(settings, "offline", True)
            object.__setattr__(settings, "offline_reason", reason)
    db.init_db()
    if db.is_empty() and not settings.use_postgres:
        log.info("empty database: seeding demo data through the agent pipeline")
        from db.seed import seed

        seed(verbose=False)
    yield


app = FastAPI(title="BondCheck API", version="1.0.0", lifespan=lifespan,
              description="Agentic AI platform for job-bond transparency. Not legal advice.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins + ["http://127.0.0.1:3000"],
                   allow_origin_regex=settings.cors_origin_regex or None,
                   allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SAMPLES_DIR = ROOT / "data" / "samples"


# --------------------------------------------------------------------------- helpers

def ndjson(ctx: RunContext) -> Iterator[str]:
    while True:
        try:
            ev = ctx.events.get(timeout=300)
        except queue.Empty:
            yield json.dumps({"kind": "error", "message": "timed out"}) + "\n"
            return
        if ev is None:
            return
        yield json.dumps(ev, default=str, ensure_ascii=False) + "\n"


def require_admin(x_admin_token: str = Header(default="")) -> None:
    if x_admin_token != settings.admin_token:
        raise HTTPException(401, "admin token required")


def require_cron(authorization: str = Header(default=""), x_admin_token: str = Header(default="")) -> None:
    if authorization != f"Bearer {settings.cron_secret}" and x_admin_token != settings.admin_token:
        raise HTTPException(401, "cron secret required")


def _mode(values):
    vals = [v for v in values if v is not None]
    return Counter(vals).most_common(1)[0][0] if vals else None


def risk_profile(recs: list[dict]) -> dict:
    """A simple, explainable 0-100 bond-risk score from verified records of one batch."""
    if not recs:
        return {"score": None, "level": "unknown", "factors": []}
    bonded = [r for r in recs if r.get("has_bond")]
    if len(bonded) * 2 < len(recs):
        return {"score": 8, "level": "low", "factors": ["No bond in most letters"]}
    months = _mode(r.get("bond_months") for r in bonded) or 0
    pen = _mode(r.get("penalty_amount") for r in bonded) or 0
    ctc = median([r["ctc_annual"] for r in recs if r.get("ctc_annual")] or [0]) or 0
    score, factors = 25.0, []
    score += min(25, months / 36 * 25)
    factors.append(f"{months}-month bond")
    if ctc:
        ratio = pen / ctc
        score += min(25, ratio * 30)
        factors.append(f"penalty = {ratio:.0%} of annual CTC")
    if sum(1 for r in recs if r.get("certificates_retained")) * 2 > len(recs):
        score += 10
        factors.append("original certificates retained")
    if _mode(r.get("penalty_prorated") for r in bonded) != "yes":
        score += 7
        factors.append("penalty not pro-rated")
    risky = Counter(c for r in recs for c in (r.get("other_risky_clauses") or []))
    if risky:
        score += min(8, 4 * len(risky))
        factors.append(f"{len(risky)} other risky clause type(s)")
    score = int(min(100, round(score)))
    return {"score": score, "level": "high" if score >= 65 else "moderate" if score >= 40 else "low",
            "factors": factors}


def group_stats(recs: list[dict]) -> dict:
    n = len(recs)
    bonded = [r for r in recs if r.get("has_bond")]
    risky = Counter(c for r in recs for c in (r.get("other_risky_clauses") or []))
    ctcs = [r["ctc_annual"] for r in recs if r.get("ctc_annual")]
    return {
        "uploads": n,
        "bond_share": round(len(bonded) / n, 2) if n else None,
        "typical_bond_months": _mode(r.get("bond_months") for r in bonded),
        "typical_penalty": _mode(r.get("penalty_amount") for r in bonded),
        "penalty_values": dict(Counter(str(r.get("penalty_amount")) for r in bonded if r.get("penalty_amount"))),
        "prorated": _mode(r.get("penalty_prorated") for r in bonded) if bonded else None,
        "typical_notice_days": _mode(r.get("notice_days") for r in recs),
        "median_ctc": int(median(ctcs)) if ctcs else None,
        "ctc_range": [min(ctcs), max(ctcs)] if ctcs else None,
        "certificates_retained_share": round(sum(1 for r in recs if r.get("certificates_retained")) / n, 2) if n else None,
        "training_recovery_share": round(sum(1 for r in recs if r.get("training_cost_recovery")) / n, 2) if n else None,
        "risky_clauses": [{"clause": c, "count": k} for c, k in risky.most_common()],
        "latest_upload": max((r["created_at"] for r in recs), default=None),
        "risk": risk_profile(recs),
    }


def company_card(c: dict, recs: list[dict], drives: dict, conflicts: Counter, public: Counter) -> dict:
    latest_batch = max((r["batch_year"] for r in recs), default=None)
    latest = [r for r in recs if r["batch_year"] == latest_batch]
    stats = group_stats(latest) if latest else None
    return {
        "id": c["id"], "name": c["name"], "aliases": c.get("aliases") or [],
        "latest_batch": latest_batch, "verified_uploads": len(recs),
        "summary": stats, "open_conflicts": conflicts.get(c["id"], 0), "public_sources": public.get(c["id"], 0),
        "next_drive": drives.get(c["id"]),
        "roles": sorted({r["role"] for r in recs if r.get("role")}),
        "confidence": "none" if not recs else "low" if len(recs) < 3 else "medium" if len(recs) < 6 else "high",
    }


# --------------------------------------------------------------------------- public endpoints

@app.get("/health")
def health() -> dict:
    return {"ok": True, "mode": "offline-rules" if settings.offline else "claude",
            "note": getattr(settings, "offline_reason", None),
            "models": None if settings.offline else {"fast": settings.fast_model, "strong": settings.strong_model},
            "database": "postgres" if settings.use_postgres else "sqlite",
            "ocr": "tesseract" if settings.tesseract_available else ("claude-vision" if not settings.offline else "none")}


@app.get("/stats")
def stats() -> dict:
    recs = db.query("SELECT company_id, has_bond, penalty_amount, bond_months FROM offer_records "
                    "WHERE status = 'verified' AND source_type = 'upload'")
    bonded = [r for r in recs if r["has_bond"]]
    runs = db.query_one("SELECT COUNT(DISTINCT run_ref) AS n FROM agent_runs WHERE workflow = 'upload'")
    redactions = 0
    for r in db.query("SELECT steps FROM agent_runs WHERE agent = 'Privacy Agent'"):
        for s in r["steps"] or []:
            m = re.search(r"found (\d+) personal", s.get("message", ""))
            if m:
                redactions += int(m.group(1))
    drives = db.query_one("SELECT COUNT(*) AS n FROM placement_drives WHERE drive_date >= ? AND drive_date <= ?",
                          [date.today().isoformat(), (date.today() + timedelta(days=30)).isoformat()])
    return {
        "companies": len({r["company_id"] for r in recs}),
        "verified_uploads": len(recs),
        "bond_share": round(len(bonded) / len(recs), 2) if recs else 0,
        "median_penalty": int(median([r["penalty_amount"] for r in bonded if r["penalty_amount"]] or [0])),
        "max_penalty": max((r["penalty_amount"] or 0 for r in bonded), default=0),
        "open_conflicts": db.query_one("SELECT COUNT(*) AS n FROM conflicts WHERE status = 'open'")["n"],
        "letters_processed": runs["n"],
        "pii_redacted": redactions,
        "drives_next_30_days": drives["n"],
    }


@app.get("/companies")
def companies(q: str = "", bond: str = Query("any", pattern="^(any|yes|no)$"),
              sort: str = Query("risk", pattern="^(risk|name|uploads|penalty|drive)$")) -> list[dict]:
    cos = db.query("SELECT * FROM companies ORDER BY name")
    recs = db.query("SELECT * FROM offer_records WHERE status = 'verified' AND source_type = 'upload'")
    by_co: dict[int, list] = {}
    for r in recs:
        by_co.setdefault(r["company_id"], []).append(r)
    drives = {}
    for d in db.query("SELECT company_id, MIN(drive_date) AS d FROM placement_drives WHERE drive_date >= ? "
                      "GROUP BY company_id", [date.today().isoformat()]):
        drives[d["company_id"]] = d["d"]
    conflicts = Counter(r["company_id"] for r in db.query("SELECT company_id FROM conflicts WHERE status = 'open'"))
    public = Counter(r["company_id"] for r in db.query("SELECT company_id FROM offer_records WHERE source_type = 'public_web'"))
    out = []
    for c in cos:
        card = company_card(c, by_co.get(c["id"], []), drives, conflicts, public)
        if q:
            matched = {m["id"] for m in db.find_company(q, limit=10) if m["score"] >= 70}
            if c["id"] not in matched and q.lower() not in c["name"].lower():
                continue
        s = card["summary"]
        if bond == "yes" and not (s and s["bond_share"] and s["bond_share"] >= 0.5):
            continue
        if bond == "no" and not (s and s["bond_share"] is not None and s["bond_share"] < 0.5):
            continue
        out.append(card)
    keys = {
        "risk": lambda c: -((c["summary"] or {}).get("risk", {}).get("score") or -1),
        "name": lambda c: c["name"].lower(),
        "uploads": lambda c: -c["verified_uploads"],
        "penalty": lambda c: -((c["summary"] or {}).get("typical_penalty") or 0),
        "drive": lambda c: c["next_drive"] or "9999",
    }
    return sorted(out, key=keys[sort])


@app.get("/company/{company_id}")
def company(company_id: int) -> dict:
    try:
        summary = db.get_company_summary(company_id)
    except ValueError:
        raise HTTPException(404, "company not found")
    recs = db.query("SELECT * FROM offer_records WHERE company_id = ? AND status = 'verified' AND source_type = 'upload' "
                    "ORDER BY created_at DESC", [company_id])
    ev = db.query("SELECT e.record_id, e.field, e.quote FROM evidence e JOIN offer_records r ON r.id = e.record_id "
                  "WHERE r.company_id = ? AND r.status = 'verified'", [company_id])
    ev_by: dict[int, list] = {}
    for e in ev:
        ev_by.setdefault(e["record_id"], []).append({"field": e["field"], "quote": e["quote"]})
    for r in recs:
        r["evidence"] = ev_by.get(r["id"], [])
    batches = {}
    for b in sorted({r["batch_year"] for r in recs}, reverse=True):
        group = [r for r in recs if r["batch_year"] == b]
        roles = {}
        for role in sorted({r.get("role") or "Unspecified" for r in group}):
            roles[role] = group_stats([r for r in group if (r.get("role") or "Unspecified") == role])
        batches[b] = {"all": group_stats(group), "roles": roles}
    public = db.query("SELECT r.id, r.batch_year, r.has_bond, r.bond_months, r.penalty_amount, r.source_url, r.created_at, "
                      "e.quote AS summary FROM offer_records r LEFT JOIN evidence e ON e.record_id = r.id "
                      "WHERE r.company_id = ? AND r.source_type = 'public_web'", [company_id])
    drives = db.query("SELECT * FROM placement_drives WHERE company_id = ? AND drive_date >= ? ORDER BY drive_date",
                      [company_id, date.today().isoformat()])
    requests_ = db.query("SELECT * FROM data_requests WHERE company_id = ? AND status = 'open'", [company_id])
    pending = db.query_one("SELECT COUNT(*) AS n FROM offer_records WHERE company_id = ? AND status = 'pending' "
                           "AND source_type = 'upload'", [company_id])["n"]
    timeline = [{"batch": b, "typical_penalty": v["all"]["typical_penalty"],
                 "typical_bond_months": v["all"]["typical_bond_months"], "uploads": v["all"]["uploads"],
                 "median_ctc": v["all"]["median_ctc"]} for b, v in sorted(batches.items())]
    return {"company": summary["company"], "confidence": summary["confidence"], "trend": summary["trend"],
            "conflicts": summary["conflicts"], "verified_uploads": len(recs), "batches": batches,
            "timeline": timeline, "records": recs[:50], "public_sources": public, "drives": drives,
            "data_requests": requests_, "pending_uploads": pending,
            "latest_upload": summary["latest_upload"]}


@app.post("/upload")
async def upload(file: UploadFile = File(...), batch_year: int | None = Form(default=None)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file too large (max 10 MB)")
    ctx = orchestrator.start_upload(data, file.filename or "upload", batch_year)
    del data  # the API keeps no copy; the agents hold it in memory only until the Privacy Agent finishes
    return StreamingResponse(ndjson(ctx), media_type="application/x-ndjson")


@app.post("/samples/{key}/upload")
def upload_sample(key: str):
    path = SAMPLES_DIR / f"{re.sub(r'[^a-z0-9_]', '', key)}.pdf"
    if not path.exists():
        raise HTTPException(404, "sample not found")
    ctx = orchestrator.start_upload(path.read_bytes(), path.name)
    return StreamingResponse(ndjson(ctx), media_type="application/x-ndjson")


class ConfirmBody(BaseModel):
    answers: dict[str, str | int | bool | None]


@app.post("/upload/{upload_id}/confirm")
def confirm(upload_id: str, body: ConfirmBody):
    try:
        ctx = orchestrator.resume_upload(upload_id, {k: v for k, v in body.answers.items() if v is not None})
    except KeyError as e:
        raise HTTPException(404, str(e))
    return StreamingResponse(ndjson(ctx), media_type="application/x-ndjson")


class AskBody(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    history: list[dict] = []


@app.post("/ask")
def ask(body: AskBody):
    ctx = runlog.register(RunContext("question"))
    history = [{"role": m["role"], "content": str(m["content"])[:2000]} for m in body.history
               if m.get("role") in {"user", "assistant"} and m.get("content")]

    def work():
        try:
            ctx.result = qa.answer(body.question, ctx, history)
        except Exception as e:  # noqa: BLE001
            log.exception("ask failed")
            ctx.result = {"answer": f"Sorry, I couldn't answer that right now ({type(e).__name__}).", "citations": []}
        finally:
            ctx.events.put({"kind": "result", "result": ctx.result})
            ctx.events.put(None)
            runlog.drop(ctx.run_ref)

    threading.Thread(target=work, daemon=True).start()
    return StreamingResponse(ndjson(ctx), media_type="application/x-ndjson")


class CalcBody(BaseModel):
    penalty: int = Field(ge=0)
    bond_months: int = Field(ge=0, le=120)
    months_served: float = Field(ge=0, le=240)
    prorated: str = Field(pattern="^(yes|no|not_mentioned)$")


@app.post("/calc/exit-cost")
def exit_cost(body: CalcBody) -> dict:
    return calc_exit_cost(body.penalty, body.bond_months, body.months_served, body.prorated)


@app.get("/record/{record_id}")
def record(record_id: int) -> dict:
    try:
        rec = db.get_evidence(record_id)
    except ValueError:
        raise HTTPException(404, "record not found")
    if rec["status"] != "verified":
        raise HTTPException(404, "record not found")
    return rec


@app.get("/drives")
def drives(days: int = 60) -> list[dict]:
    rows = db.query("SELECT d.*, c.name FROM placement_drives d JOIN companies c ON c.id = d.company_id "
                    "WHERE d.drive_date >= ? AND d.drive_date <= ? ORDER BY d.drive_date",
                    [date.today().isoformat(), (date.today() + timedelta(days=days)).isoformat()])
    for r in rows:
        r["days_left"] = (date.fromisoformat(str(r["drive_date"])[:10]) - date.today()).days
        cov = monitor.coverage(r["company_id"], date.today().year)
        r["coverage"] = cov
    return rows


@app.get("/data-requests")
def data_requests() -> list[dict]:
    return db.query("SELECT r.*, c.name FROM data_requests r JOIN companies c ON c.id = r.company_id "
                    "WHERE r.status = 'open' ORDER BY r.created_at DESC")


class SubscribeBody(BaseModel):
    email: EmailStr
    company_ids: list[int] = Field(min_length=1, max_length=50)
    alert_all: bool = False


@app.post("/subscribe")
def subscribe(body: SubscribeBody) -> dict:
    email = body.email.lower()
    user = db.query_one("SELECT id FROM users WHERE email = ?", [email])
    uid = user["id"] if user else db.insert("users", {"email": email, "alert_all": body.alert_all})
    if user:
        db.update("users", uid, {"alert_all": body.alert_all})
    valid = {c["id"] for c in db.query("SELECT id FROM companies")}
    added = 0
    for cid in body.company_ids:
        if cid in valid and not db.query_one("SELECT 1 AS x FROM subscriptions WHERE user_id = ? AND company_id = ?",
                                             [uid, cid]):
            db.execute("INSERT INTO subscriptions (user_id, company_id) VALUES (?, ?)", [uid, cid])
            added += 1
    return {"ok": True, "subscribed": added}


@app.get("/samples")
def samples() -> list[dict]:
    path = SAMPLES_DIR / "samples.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


@app.get("/samples/{key}.pdf")
def sample_file(key: str):
    path = SAMPLES_DIR / f"{re.sub(r'[^a-z0-9_]', '', key)}.pdf"
    if not path.exists():
        raise HTTPException(404, "sample not found")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@app.get("/eval/results")
def eval_results() -> dict:
    path = ROOT / "eval" / "results.json"
    if not path.exists():
        raise HTTPException(404, "run `python -m eval.run_eval` first")
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- admin

@app.get("/admin/overview", dependencies=[Depends(require_admin)])
def admin_overview() -> dict:
    agents = db.query("SELECT agent, COUNT(*) AS runs, AVG(duration_ms) AS avg_ms, SUM(tokens_used) AS tokens, "
                      "SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS ok, "
                      "SUM(CASE WHEN status <> 'success' THEN 1 ELSE 0 END) AS not_ok "
                      "FROM agent_runs GROUP BY agent ORDER BY runs DESC")
    workflows = db.query("SELECT workflow, COUNT(DISTINCT run_ref) AS runs FROM agent_runs GROUP BY workflow")
    retries = 0
    for r in db.query("SELECT steps FROM agent_runs"):
        retries += sum(1 for s in (r["steps"] or []) if s.get("kind") == "retry")
    return {"agents": agents, "workflows": workflows, "self_corrections": retries,
            "queue_pending": db.query_one("SELECT COUNT(*) AS n FROM moderation_queue WHERE status = 'pending'")["n"],
            "open_conflicts": db.query_one("SELECT COUNT(*) AS n FROM conflicts WHERE status = 'open'")["n"],
            "health": health()}


@app.get("/admin/queue", dependencies=[Depends(require_admin)])
def admin_queue(status: str = "pending") -> list[dict]:
    items = db.query("SELECT * FROM moderation_queue WHERE status = ? ORDER BY created_at DESC", [status])
    for it in items:
        if it.get("record_id"):
            rec = db.get_evidence(it["record_id"])
            it["record"] = rec
            it["similar"] = db.find_company(rec["company_name"], limit=4)
    return items


class QueueAction(BaseModel):
    action: str = Field(pattern="^(approve|reject|merge|dismiss)$")
    merge_into: int | None = None
    note: str | None = None


@app.post("/admin/queue/{item_id}", dependencies=[Depends(require_admin)])
def admin_queue_action(item_id: int, body: QueueAction) -> dict:
    try:
        return db.resolve_queue_item(item_id, body.action, body.merge_into, body.note)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/admin/conflicts", dependencies=[Depends(require_admin)])
def admin_conflicts() -> list[dict]:
    return db.query("SELECT f.*, c.name FROM conflicts f JOIN companies c ON c.id = f.company_id "
                    "ORDER BY f.status, f.created_at DESC")


class ConflictAction(BaseModel):
    keep_value: str | None = None


@app.post("/admin/conflicts/{conflict_id}/resolve", dependencies=[Depends(require_admin)])
def admin_resolve_conflict(conflict_id: int, body: ConflictAction) -> dict:
    try:
        return db.resolve_conflict(conflict_id, body.keep_value)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/admin/runs", dependencies=[Depends(require_admin)])
def admin_runs(workflow: str | None = None, limit: int = 40) -> list[dict]:
    q = ("SELECT run_ref, workflow, MIN(created_at) AS started, SUM(tokens_used) AS tokens, SUM(duration_ms) AS ms, "
         "COUNT(*) AS agents FROM agent_runs")
    params: list = []
    if workflow:
        q += " WHERE workflow = ?"
        params.append(workflow)
    q += " GROUP BY run_ref, workflow ORDER BY MIN(id) DESC LIMIT ?"
    runs = db.query(q, [*params, min(limit, 200)])
    for r in runs:
        rows = db.query("SELECT agent, status FROM agent_runs WHERE run_ref = ? ORDER BY id", [r["run_ref"]])
        r["agent_list"] = rows
        statuses = {x["status"] for x in rows}
        r["status"] = ("failed" if "failed" in statuses else "escalated" if "escalated" in statuses
                       else "paused" if "paused" in statuses else "success")
    return runs


@app.get("/admin/runs/{run_ref}", dependencies=[Depends(require_admin)])
def admin_run(run_ref: str) -> list[dict]:
    return db.query("SELECT * FROM agent_runs WHERE run_ref = ? ORDER BY id", [run_ref])


class DriveBody(BaseModel):
    company_id: int
    college: str
    drive_date: date


@app.post("/admin/drives", dependencies=[Depends(require_admin)])
def admin_add_drive(body: DriveBody) -> dict:
    rid = db.insert("placement_drives", {"company_id": body.company_id, "college": body.college,
                                         "drive_date": body.drive_date.isoformat()})
    return {"id": rid}


# --------------------------------------------------------------------------- cron (Monitor + Alert agents)

def _run_proactive(workflow: str, fn) -> dict:
    ctx = RunContext(workflow)
    result = fn(ctx)
    events = []
    while not ctx.events.empty():
        events.append(ctx.events.get())
    return {"result": result, "steps": events}


@app.api_route("/cron/monitor", methods=["GET", "POST"], dependencies=[Depends(require_cron)])
def cron_monitor() -> dict:
    return _run_proactive("monitor", monitor.run)


@app.api_route("/cron/alerts", methods=["GET", "POST"], dependencies=[Depends(require_cron)])
def cron_alerts() -> dict:
    return _run_proactive("alert", alert.run)
