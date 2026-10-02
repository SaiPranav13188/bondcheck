"""Monitor Agent (scheduled daily). Goal: keep data fresh for companies students care about right now.

1. Get the companies visiting campus in the next 30 days.
2. Check coverage: no data, old data (previous batch only) or unresolved conflicts.
3. For gaps, search public sources and save findings separately, labelled "Unverified public source".
   They never overwrite verified records.
4. Create "data needed" requests asking seniors to upload.
"""
from __future__ import annotations

from datetime import date, timedelta

from core import llm
from core.config import settings
from core.runlog import RunContext
from tools import database as db
from tools import web

A = "Monitor Agent"


def get_upcoming_drives(days: int = 30) -> list[dict]:
    today = date.today()
    return db.query(
        "SELECT d.id, d.company_id, d.college, d.drive_date, c.name FROM placement_drives d "
        "JOIN companies c ON c.id = d.company_id WHERE d.drive_date >= ? AND d.drive_date <= ? ORDER BY d.drive_date",
        [today.isoformat(), (today + timedelta(days=days)).isoformat()])


def coverage_all(batch: int) -> dict[int, dict]:
    """Coverage for every company in two queries: {company_id: {gap, latest_batch, uploads, open_conflicts}}."""
    uploads = {r["company_id"]: r for r in db.run_readonly_sql(
        "SELECT company_id, MAX(batch_year) AS latest, COUNT(*) AS n FROM offer_records "
        "WHERE status = 'verified' AND source_type = 'upload' GROUP BY company_id")}
    conflicts = {r["company_id"]: r["n"] for r in db.run_readonly_sql(
        "SELECT company_id, COUNT(*) AS n FROM conflicts WHERE status = 'open' GROUP BY company_id")}

    class _All(dict):
        def __missing__(self, cid):
            return _one(cid)

    def _one(cid: int) -> dict:
        u = uploads.get(cid)
        latest = u["latest"] if u else None
        n_conf = conflicts.get(cid, 0)
        gap = "no_data" if not u else "stale" if latest < batch else "conflict" if n_conf else None
        return {"gap": gap, "latest_batch": latest, "uploads": int(u["n"]) if u else 0, "open_conflicts": int(n_conf)}

    return _All()


def coverage(company_id: int, batch: int) -> dict:
    return coverage_all(batch)[company_id]


EXTRACT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["found", "has_bond", "bond_months", "penalty_amount", "batch_year", "source_url", "summary"],
    "properties": {
        "found": {"type": "boolean"},
        "has_bond": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
        "bond_months": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "penalty_amount": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "batch_year": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "source_url": {"type": "string"},
        "summary": {"type": "string"},
    },
}


def save_public_source(company_id: int, finding: dict, batch: int) -> int:
    """Stored as source_type='public_web', status='pending': shown separately, never counted as verified."""
    fields = {"batch_year": finding.get("batch_year") or batch, "has_bond": finding.get("has_bond"),
              "bond_months": finding.get("bond_months"), "penalty_amount": finding.get("penalty_amount")}
    return db.save_record(company_id, fields, [("public_summary", finding.get("summary", "")[:900])],
                          status="pending", confidence=0.3, source_type="public_web", source_url=finding["source_url"])


def run(ctx: RunContext, days: int = 30) -> dict:
    batch = date.today().year
    summary = {"drives": 0, "gaps": [], "public_sources": 0, "requests": 0}
    with ctx.agent(A):
        drives = get_upcoming_drives(days)
        ctx.emit(A, "tool", f"get_upcoming_drives: {len(drives)} drive(s) in the next {days} days")
        summary["drives"] = len(drives)
        seen: set[int] = set()
        cov_all = coverage_all(batch)
        for d in drives:
            if d["company_id"] in seen:
                continue
            seen.add(d["company_id"])
            cov = cov_all[d["company_id"]]
            if not cov["gap"]:
                ctx.emit(A, "check", f"{d['name']}: covered ({cov['uploads']} verified uploads, batch {cov['latest_batch']})")
                continue
            ctx.emit(A, "decision", f"{d['name']}: gap = {cov['gap']} (drive on {d['drive_date']})")
            summary["gaps"].append({"company": d["name"], "company_id": d["company_id"], **cov})

            # Research public sources (labelled unverified, never merged into verified data).
            if cov["gap"] in {"no_data", "stale"}:
                try:
                    res = web.web_search(f"{d['name']} fresher service agreement bond period penalty {batch}", ctx.meter)
                    ctx.emit(A, "tool", f"web_search: {len(res['urls'])} source(s) for {d['name']}")
                    if res["urls"]:
                        finding = llm.json_call(
                            model=settings.strong_model, schema=EXTRACT_SCHEMA, meter=ctx.meter,
                            system="Extract publicly reported fresher bond terms. Only report what the text states. "
                                   + llm.DATA_ONLY_RULE,
                            prompt=f"Company: {d['name']}\nSources: {res['urls']}\n\nResearch notes:\n{res['summary']}")
                        if finding.get("found") and finding.get("source_url", "").startswith("http"):
                            save_public_source(d["company_id"], finding, batch)
                            summary["public_sources"] += 1
                            ctx.emit(A, "tool", f"save_public_source: {finding['source_url']} (unverified)")
                except web.WebUnavailable as e:
                    ctx.emit(A, "info", f"Skipped public search: {e}")
                except Exception as e:  # noqa: BLE001 - research is best-effort
                    ctx.emit(A, "error", f"Public search for {d['name']} failed: {e}")

            name = d["name"].rstrip(".")
            msg = {
                "no_data": f"We have no {batch} data for {name}. Seniors who joined, please upload your offer letter.",
                "stale": f"Our latest {name} data is from the {cov['latest_batch']} batch. "
                         f"If you got a {batch} offer, please upload it.",
                "conflict": f"Uploads for {name} disagree. More {batch} letters will help settle it.",
            }[cov["gap"]]
            exists = db.query_one("SELECT id FROM data_requests WHERE company_id = ? AND batch_year = ? AND status = 'open'",
                                  [d["company_id"], batch])
            if not exists:
                db.insert("data_requests", {"company_id": d["company_id"], "batch_year": batch, "reason": cov["gap"],
                                            "message": msg})
                summary["requests"] += 1
                ctx.emit(A, "tool", f"create_data_request: {msg}")
        ctx.emit(A, "done", f"{len(summary['gaps'])} gap(s), {summary['requests']} new request(s), "
                            f"{summary['public_sources']} public source(s) saved")
    return summary
