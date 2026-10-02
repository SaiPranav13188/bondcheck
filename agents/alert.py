"""Alert Agent (proactive). Goal: warn students before it's too late.

7 days before a drive it emails subscribed students a short summary of the bond terms, the
confidence level and a link. It decides *whether* an alert is worth sending: "no bond, high
confidence" is skipped unless the student opted in to all alerts.
"""
from __future__ import annotations

from datetime import date, timedelta

from core.config import settings
from core.runlog import RunContext
from tools import database as db
from tools.calculator import inr
from tools.notify import send_email

A = "Alert Agent"


def get_subscriptions(company_id: int) -> list[dict]:
    return db.query("SELECT u.id, u.email, u.alert_all FROM subscriptions s JOIN users u ON u.id = s.user_id "
                    "WHERE s.company_id = ?", [company_id])


def compose(summary: dict, drive: dict) -> tuple[str, str, bool]:
    """(subject, body, worth_sending_to_everyone)."""
    name = summary["company"]["name"]
    latest = summary["latest"]
    url = f"{settings.site_url}/companies/{summary['company']['id']}"
    when = drive["drive_date"]
    if not latest:
        subject = f"{name} visits on {when}: no verified bond data yet"
        body = (f"{name} is visiting {drive['college'] or 'campus'} on {when}.\n\nWe don't have verified uploads for "
                f"{name} yet, so ask HR for the service agreement in writing before you accept.\n\n{url}")
        return subject, body, True
    months, pen = latest.get("typical_bond_months"), latest.get("typical_penalty")
    has_bond = bool(months or pen)
    conf = summary["confidence"]
    lines = [f"{name} is visiting {drive['college'] or 'campus'} on {when}.", ""]
    if has_bond:
        lines.append(f"Reported bond ({latest['batch_year']} batch): {months or '?'} months, penalty {inr(pen)}.")
    else:
        lines.append(f"Reported terms ({latest['batch_year']} batch): no bond.")
    lines.append(f"Confidence: {conf} ({summary['verified_uploads']} verified uploads, latest "
                 f"{str(summary['latest_upload'])[:10]}).")
    if summary["conflicts"]:
        lines.append("Note: uploads disagree on some terms. See the company page.")
    if summary.get("trend") and summary["trend"]["direction"] != "unchanged":
        t = summary["trend"]
        lines.append(f"Trend: the penalty got {t['direction']} since the {t['from_batch']} batch.")
    lines += ["", f"Details and evidence: {url}", "",
              "BondCheck shows terms reported in uploaded letters. It is not legal advice."]
    subject = (f"⚠ {name} ({when}): {months}-month bond, {inr(pen)} penalty" if has_bond
               else f"{name} ({when}): no bond reported")
    worth = has_bond or conf != "high" or bool(summary["conflicts"])
    return subject, "\n".join(lines), worth


def run(ctx: RunContext, days_before: int = 7) -> dict:
    target = date.today() + timedelta(days=days_before)
    stats = {"drives": 0, "sent": 0, "skipped": 0}
    with ctx.agent(A):
        drives = db.query("SELECT d.*, c.name FROM placement_drives d JOIN companies c ON c.id = d.company_id "
                          "WHERE d.drive_date > ? AND d.drive_date <= ?", [date.today().isoformat(), target.isoformat()])
        ctx.emit(A, "tool", f"Drives within {days_before} days: {len(drives)}")
        stats["drives"] = len(drives)
        for d in drives:
            subs = get_subscriptions(d["company_id"])
            ctx.emit(A, "tool", f"get_subscriptions({d['name']}): {len(subs)} student(s)")
            if not subs:
                continue
            summary = db.get_company_summary(d["company_id"])
            subject, body, worth = compose(summary, d)
            for u in subs:
                if db.query_one("SELECT id FROM alerts_sent WHERE user_id = ? AND drive_id = ?", [u["id"], d["id"]]):
                    continue
                if not worth and not u["alert_all"]:
                    stats["skipped"] += 1
                    ctx.emit(A, "decision", f"Skip {u['email']}: no bond with high confidence and not opted in to all alerts")
                    continue
                res = send_email(u["email"], subject, body)
                db.insert("alerts_sent", {"user_id": u["id"], "company_id": d["company_id"], "drive_id": d["id"],
                                          "subject": subject})
                stats["sent"] += 1
                ctx.emit(A, "tool", f"send_email → {u['email']} via {res['provider']}: {subject}")
        ctx.emit(A, "done", f"{stats['sent']} alert(s) sent, {stats['skipped']} skipped")
    return stats
