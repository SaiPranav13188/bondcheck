"""Verification Agent. Goal: decide how a new record relates to existing knowledge and keep the
database trustworthy.

Decisions: corroborate | variant | conflict | outlier | new_company
"""
from __future__ import annotations

from collections import Counter

from rapidfuzz import fuzz

from core.config import settings
from core.runlog import RunContext
from tools import database as db
from tools.calculator import inr

COMPARE_FIELDS = ["has_bond", "bond_months", "penalty_amount"]
MATCH_SCORE = 90      # find_company score treated as the same company
DUPLICATE_SCORE = 75  # below MATCH_SCORE but above this: maybe a duplicate, flag for review


def compare_records(new: dict, existing: list[dict]) -> dict:
    """Compare a new record with the existing records of the same company/batch/role."""
    differing = {}
    for f in COMPARE_FIELDS:
        seen = Counter(str(r.get(f)) for r in existing if r.get(f) is not None)
        if not seen:
            continue
        typical = seen.most_common(1)[0][0]
        if new.get(f) is not None and str(new.get(f)) != typical:
            seen[str(new.get(f))] += 1
            differing[f] = dict(seen)
    return {"matches": not differing, "differing": differing}


def outlier_reasons(fields: dict) -> list[str]:
    reasons = []
    pen, months, ctc = fields.get("penalty_amount"), fields.get("bond_months"), fields.get("ctc_annual")
    if pen and pen > settings.outlier_penalty:
        reasons.append(f"penalty {inr(pen)} is above {inr(settings.outlier_penalty)}")
    if months and months > settings.outlier_bond_months:
        reasons.append(f"bond of {months} months is longer than {settings.outlier_bond_months}")
    if pen and ctc and pen > 3 * ctc:
        reasons.append(f"penalty is more than 3× the annual CTC ({inr(ctc)})")
    if ctc and (ctc < 60_000 or ctc > 10_000_000):
        reasons.append(f"CTC {inr(ctc)} is outside the usual fresher range")
    return reasons


def _same_role(a: str | None, b: str | None) -> bool:
    if not a or not b:  # an unknown role is not evidence of a different role
        return True
    return fuzz.token_sort_ratio(a.lower(), b.lower()) >= 85


def run(fields_fv: dict, ctx: RunContext) -> dict:
    """fields_fv: field -> {value, quote, confidence}. Returns decision details."""
    A = "Verification Agent"
    fields = {f: v.get("value") for f, v in fields_fv.items()}
    evidence: dict[str, str] = {}
    for f, v in fields_fv.items():
        if v.get("value") not in (None, []) and v.get("quote"):
            evidence[f] = v["quote"]
        for i, q in enumerate(v.get("quotes") or []):
            if i:  # extra risky-clause quotes
                evidence[f"{f}#{i}"] = q
    key_conf = [fields_fv[f].get("confidence", 0.5) for f in ("company_name", "has_bond", "bond_months", "penalty_amount")
                if fields_fv[f].get("value") is not None]
    confidence = sum(key_conf) / len(key_conf) if key_conf else 0.5

    with ctx.agent(A) as run_:
        name = fields.get("company_name") or "Unknown company"
        matches = db.find_company(name)
        ctx.emit(A, "tool", f"find_company('{name}') → " +
                 (", ".join(f"{m['name']} ({m['score']})" for m in matches) or "no match"), matches=matches)
        best = matches[0] if matches else None
        outliers = outlier_reasons(fields)
        batch = fields.get("batch_year")
        role = fields.get("role")

        with db.connect() as conn:
            def save(company_id: int, status: str) -> int:
                pairs = [(k.split("#")[0], q) for k, q in evidence.items()]
                return db.save_record(company_id, fields, pairs, status=status, confidence=confidence, conn=conn)

            # 1. Outlier: extreme or suspicious values are held for a moderator.
            if outliers:
                cid = best["id"] if best and best["score"] >= MATCH_SCORE else db.create_company(name, conn)
                rid = save(cid, "pending")
                db.insert("moderation_queue", {"record_id": rid, "reason": "outlier", "note": "; ".join(outliers)}, conn)
                ctx.emit(A, "decision", f"OUTLIER: {'; '.join(outliers)}. Held for moderator review.")
                run_.status = "escalated"
                return {"decision": "outlier", "record_id": rid, "company_id": cid, "reasons": outliers}

            # 2. New company (possibly a duplicate of an existing one).
            if not best or best["score"] < MATCH_SCORE:
                cid = db.create_company(name, conn)
                rid = save(cid, "pending")
                note = (f"possible duplicate of '{best['name']}' (match score {best['score']})"
                        if best and best["score"] >= DUPLICATE_SCORE else "first upload for this company")
                db.insert("moderation_queue", {"record_id": rid, "reason": "new_company", "note": note}, conn)
                ctx.emit(A, "decision", f"NEW COMPANY: created '{name}' ({note}); flagged for review.")
                return {"decision": "new_company", "record_id": rid, "company_id": cid, "note": note}

            cid = best["id"]
            if best["name"].lower() != name.lower():
                db.add_alias(cid, name, conn)
            existing = db.query(
                "SELECT * FROM offer_records WHERE company_id = ? AND status = 'verified' AND source_type = 'upload'",
                [cid], conn)
            same_group = [r for r in existing if r["batch_year"] == batch and _same_role(r.get("role"), role)]
            ctx.emit(A, "tool", f"run_readonly_sql: {len(existing)} verified records for {best['name']}, "
                                f"{len(same_group)} for batch {batch} / {role or 'any role'}")

            # 3. Different batch or role -> a separate variant.
            if not same_group:
                rid = save(cid, "verified")
                why = "first record for this batch/role" if existing else "first verified record for this company"
                ctx.emit(A, "decision", f"NEW VARIANT: stored separately ({why}).")
                return {"decision": "variant", "record_id": rid, "company_id": cid, "note": why}

            cmp = compare_records(fields, same_group)
            ctx.emit(A, "tool", "compare_records → " + ("matches existing records" if cmp["matches"] else
                                                       f"differs on {', '.join(cmp['differing'])}"))
            # 4. Same terms -> corroborate.
            if cmp["matches"]:
                rid = save(cid, "verified")
                ctx.emit(A, "decision", f"CORROBORATE: matches {len(same_group)} earlier upload(s); "
                                        f"now {len(same_group) + 1} supporting uploads.")
                return {"decision": "corroborate", "record_id": rid, "company_id": cid,
                        "supporting_uploads": len(same_group) + 1}

            # 5. Same company/batch/role, different terms -> conflict, shown openly to users.
            rid = save(cid, "verified")
            conflict_ids = []
            for f, seen in cmp["differing"].items():
                row = db.query_one("SELECT id FROM conflicts WHERE company_id = ? AND batch_year = ? AND field = ? "
                                   "AND status = 'open' AND role IS NOT DISTINCT FROM ?",
                                   [cid, batch, f, role], conn)
                if row:
                    db.update("conflicts", row["id"], {"values_seen": seen}, conn)
                    conflict_ids.append(row["id"])
                else:
                    conflict_ids.append(db.insert("conflicts", {"company_id": cid, "batch_year": batch, "role": role,
                                                                "field": f, "values_seen": seen}, conn))
            db.insert("moderation_queue", {"record_id": rid, "reason": "conflict",
                                           "note": "; ".join(f"{f}: {v}" for f, v in cmp["differing"].items())}, conn)
            ctx.emit(A, "decision", "CONFLICT: " + "; ".join(f"{f} values seen {v}" for f, v in cmp["differing"].items())
                     + ". Shown to users and sent to a moderator.")
            return {"decision": "conflict", "record_id": rid, "company_id": cid, "conflicts": conflict_ids,
                    "differing": cmp["differing"]}
