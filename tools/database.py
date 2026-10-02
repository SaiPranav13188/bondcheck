"""Database tools: connections, find_company, run_readonly_sql, save_record and friends.

Works on PostgreSQL (DATABASE_URL) or SQLite (local default). Queries are written
with `?` placeholders and translated for psycopg.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Iterable

from rapidfuzz import fuzz, process

from core.config import ROOT, settings

JSON_COLUMNS = {"aliases", "other_risky_clauses", "values_seen", "steps"}
BOOL_COLUMNS = {"has_bond", "training_cost_recovery", "certificates_retained", "alert_all"}
READONLY_TABLES = {"company_summary", "offer_records", "evidence", "conflicts"}
APP_TABLES = ["alerts_sent", "data_requests", "agent_runs", "subscriptions", "users", "placement_drives",
              "moderation_queue", "conflicts", "evidence", "offer_records", "companies"]

_lock = threading.RLock()


# --------------------------------------------------------------------------- connections

def _sqlite_connect(readonly: bool = False) -> sqlite3.Connection:
    path = settings.sqlite_path
    if readonly:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _pg_connect(url: str):
    import psycopg
    from psycopg.rows import dict_row

    # prepare_threshold=None: Supabase/Neon poolers (PgBouncer) don't support prepared statements.
    return psycopg.connect(url, row_factory=dict_row, autocommit=False, prepare_threshold=None, connect_timeout=15)


@contextmanager
def connect():
    """Read-write connection used by the agents' own tools (never by text-to-SQL)."""
    if settings.use_postgres:
        conn = _pg_connect(settings.database_url)
    else:
        conn = _sqlite_connect()
    try:
        with _lock if not settings.use_postgres else _nullcontext():
            yield conn
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def _nullcontext():
    yield


def _sql(q: str) -> str:
    return q.replace("?", "%s") if settings.use_postgres else q


def _decode(row: Any) -> dict:
    d = dict(row)
    for k, v in d.items():
        if k in JSON_COLUMNS and isinstance(v, str):
            try:
                d[k] = json.loads(v)
            except json.JSONDecodeError:
                pass
        elif k in BOOL_COLUMNS and isinstance(v, int) and not isinstance(v, bool):
            d[k] = bool(v)
        elif isinstance(v, (datetime, date)):
            d[k] = v.isoformat()
        elif k == "confidence" and v is not None:
            d[k] = float(v)
    return d


def _encode(col: str, v: Any) -> Any:
    if col in JSON_COLUMNS and not isinstance(v, str) and v is not None:
        if col == "aliases" and settings.use_postgres:
            return list(v)
        return json.dumps(v)
    if col in BOOL_COLUMNS and v is not None and not settings.use_postgres:
        return int(bool(v))
    return v


def query(q: str, params: Iterable = (), conn=None) -> list[dict]:
    def run(c):
        cur = c.execute(_sql(q), tuple(params))
        rows = cur.fetchall() if cur.description else []
        return [_decode(r) for r in rows]

    if conn is not None:
        return run(conn)
    with connect() as c:
        return run(c)


def query_one(q: str, params: Iterable = (), conn=None) -> dict | None:
    rows = query(q, params, conn)
    return rows[0] if rows else None


def execute(q: str, params: Iterable = (), conn=None) -> Any:
    """Execute a write. Returns the `id` when the statement has RETURNING id."""
    def run(c):
        cur = c.execute(_sql(q), tuple(params))
        if "RETURNING" in q.upper():
            row = cur.fetchone()
            return dict(row)["id"] if row else None
        return cur.rowcount

    if conn is not None:
        return run(conn)
    with connect() as c:
        return run(c)


def insert(table: str, values: dict, conn=None) -> int:
    cols = list(values)
    q = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)}) RETURNING id"
    return execute(q, [_encode(c, values[c]) for c in cols], conn)


def update(table: str, row_id: int, values: dict, conn=None) -> None:
    sets = ", ".join(f"{c} = ?" for c in values)
    execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*(_encode(c, v) for c, v in values.items()), row_id], conn)


# --------------------------------------------------------------------------- setup

def init_db(reset: bool = False) -> None:
    if settings.use_postgres:
        schema = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
        with connect() as c:
            if reset:  # only BondCheck's own objects; never the whole schema (Supabase keeps grants there)
                c.execute("DROP VIEW IF EXISTS company_summary")
                c.execute("DROP TABLE IF EXISTS " + ", ".join(APP_TABLES) + " CASCADE")
            c.execute(schema)
    else:
        if reset and settings.sqlite_path.exists():
            settings.sqlite_path.unlink()
        schema = (ROOT / "db" / "schema_sqlite.sql").read_text(encoding="utf-8")
        with connect() as c:
            c.executescript(schema)


def is_empty() -> bool:
    try:
        return (query_one("SELECT COUNT(*) AS n FROM companies") or {"n": 0})["n"] == 0
    except Exception:
        return True


# --------------------------------------------------------------------------- company tools

_SUFFIXES = r"\b(private|pvt|limited|ltd|llp|inc|incorporated|corp|corporation|co|company|india|technologies|technology|tech|solutions|systems|services|software|infotech|labs)\b"


def normalize_company(name: str) -> str:
    """'Nexora Technologies Pvt. Ltd.' -> 'nexora'. Used as the unique key and for fuzzy matching."""
    s = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    core = re.sub(_SUFFIXES, " ", s)
    core = re.sub(r"\s+", " ", core).strip()
    return core or re.sub(r"\s+", " ", s).strip()


def find_company(name: str, limit: int = 3) -> list[dict]:
    """Fuzzy-match a company name against names and aliases. Returns [{id, name, score}]."""
    if not name:
        return []
    companies = query("SELECT id, name, normalized_name, aliases FROM companies")
    choices: dict[str, int] = {}
    for c in companies:
        choices[c["normalized_name"]] = c["id"]
        for a in c.get("aliases") or []:
            choices[normalize_company(a)] = c["id"]
    target = normalize_company(name)
    if not choices or not target:
        return []
    best: dict[int, float] = {}
    for key, score, _ in process.extract(target, list(choices), scorer=fuzz.WRatio, limit=10):
        cid = choices[key]
        # Short keys (e.g. "tcs") need an exact match to avoid false positives.
        if len(key) <= 3 and key != target:
            continue
        best[cid] = max(best.get(cid, 0), score)
    by_id = {c["id"]: c for c in companies}
    ranked = sorted(best.items(), key=lambda kv: -kv[1])[:limit]
    return [{"id": cid, "name": by_id[cid]["name"], "score": round(s, 1)} for cid, s in ranked]


def create_company(name: str, conn=None) -> int:
    norm = normalize_company(name)
    existing = query_one("SELECT id FROM companies WHERE normalized_name = ?", [norm], conn)
    if existing:
        return existing["id"]
    return insert("companies", {"name": name.strip(), "normalized_name": norm, "aliases": [name.strip()]}, conn)


def add_alias(company_id: int, alias: str, conn=None) -> None:
    row = query_one("SELECT aliases FROM companies WHERE id = ?", [company_id], conn)
    aliases = list(row.get("aliases") or []) if row else []
    if alias and alias not in aliases:
        aliases.append(alias)
        update("companies", company_id, {"aliases": aliases}, conn)


# --------------------------------------------------------------------------- records

RECORD_FIELDS = [
    "batch_year", "role", "ctc_annual", "has_bond", "bond_months", "penalty_amount", "penalty_prorated",
    "notice_days", "training_cost_recovery", "certificates_retained", "other_risky_clauses",
]


def save_record(company_id: int, fields: dict, evidence: list[tuple[str, str]], *, status: str,
                confidence: float, source_type: str = "upload", source_url: str | None = None,
                conn=None) -> int:
    """Store a record and its evidence quotes (redacted clause text only)."""
    values = {k: fields.get(k) for k in RECORD_FIELDS}
    values["other_risky_clauses"] = values.get("other_risky_clauses") or []
    values["penalty_prorated"] = values.get("penalty_prorated") or "not_mentioned"
    values.update(company_id=company_id, status=status, confidence=round(confidence, 2),
                  source_type=source_type, source_url=source_url)
    rid = insert("offer_records", values, conn)
    for field, quote in evidence:
        if quote:
            insert("evidence", {"record_id": rid, "field": field, "quote": quote[:1000]}, conn)
    return rid


def get_evidence(record_id: int) -> dict:
    rec = query_one(
        "SELECT r.*, c.name AS company_name FROM offer_records r JOIN companies c ON c.id = r.company_id "
        "WHERE r.id = ?", [record_id])
    if not rec:
        raise ValueError(f"record {record_id} not found")
    rec["evidence"] = query("SELECT field, quote FROM evidence WHERE record_id = ? ORDER BY id", [record_id])
    return rec


def get_company_summary(company_id: int) -> dict:
    """Typical terms per batch/role, upload counts, latest date, conflicts and the year-on-year trend."""
    company = query_one("SELECT * FROM companies WHERE id = ?", [company_id])
    if not company:
        raise ValueError(f"company {company_id} not found")
    groups = query("SELECT * FROM company_summary WHERE company_id = ? ORDER BY batch_year DESC, supporting_uploads DESC",
                   [company_id])
    records = query("SELECT * FROM offer_records WHERE company_id = ? AND status = 'verified' AND source_type = 'upload' "
                    "ORDER BY batch_year DESC, created_at DESC", [company_id])
    conflicts = query("SELECT * FROM conflicts WHERE company_id = ? AND status = 'open'", [company_id])
    latest = groups[0] if groups else None
    trend = None
    if latest:
        prev = next((g for g in groups if g["batch_year"] < latest["batch_year"] and g["role"] == latest["role"]), None) \
            or next((g for g in groups if g["batch_year"] < latest["batch_year"]), None)
        if prev and prev.get("typical_penalty") is not None and latest.get("typical_penalty") is not None:
            diff = (latest["typical_penalty"] or 0) - (prev["typical_penalty"] or 0)
            trend = {"from_batch": prev["batch_year"], "to_batch": latest["batch_year"],
                     "penalty_change": diff,
                     "bond_months_change": (latest["typical_bond_months"] or 0) - (prev["typical_bond_months"] or 0),
                     "direction": "harsher" if diff > 0 else "softer" if diff < 0 else "unchanged"}
    with_bond = [r for r in records if r.get("has_bond")]
    total = len(records)
    confidence = "none" if total == 0 else "low" if total < 3 else "medium" if total < 6 else "high"
    if conflicts and confidence == "high":
        confidence = "medium"
    return {
        "company": company,
        "groups": groups,
        "latest": latest,
        "trend": trend,
        "conflicts": conflicts,
        "verified_uploads": total,
        "bond_share": round(len(with_bond) / total, 2) if total else None,
        "confidence": confidence,
        "latest_upload": max((r["created_at"] for r in records), default=None),
    }


# --------------------------------------------------------------------------- read-only SQL

class UnsafeQuery(ValueError):
    pass


_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|truncate|grant|revoke|attach|detach|pragma|vacuum|"
    r"copy|call|execute|do|set|reset|lock|comment|merge|refresh|listen|notify|load)\b", re.I)


def _check_select(sql: str) -> str:
    s = sql.strip().rstrip(";").strip()
    if ";" in s:
        raise UnsafeQuery("only a single statement is allowed")
    if not re.match(r"^(select|with)\b", s, re.I):
        raise UnsafeQuery("only SELECT queries are allowed")
    stripped = re.sub(r"'(?:[^']|'')*'", "''", s)  # ignore string literals when scanning keywords
    if _FORBIDDEN.search(stripped):
        raise UnsafeQuery("query contains a forbidden keyword")
    tables = {t.lower() for t in re.findall(r"\b(?:from|join)\s+([a-z_][a-z0-9_]*)", stripped, re.I)}
    ctes = {t.lower() for t in re.findall(r"\b([a-z_][a-z0-9_]*)\s+as\s*\(", stripped, re.I)}
    bad = tables - READONLY_TABLES - ctes
    if bad:
        raise UnsafeQuery(f"table(s) not allowed: {', '.join(sorted(bad))}. "
                          f"Allowed: {', '.join(sorted(READONLY_TABLES))}")
    return s


def run_readonly_sql(sql: str, params: Iterable = (), limit: int | None = None) -> list[dict]:
    """Text-to-SQL tool: SELECT only, allow-listed tables, automatic LIMIT, timeout, read-only connection."""
    limit = min(limit or settings.sql_row_limit, settings.sql_row_limit)
    s = _check_select(sql)
    wrapped = f"SELECT * FROM ({s}) AS q LIMIT {int(limit)}"
    if settings.use_postgres:
        conn = _pg_connect(settings.readonly_database_url or settings.database_url)
        try:
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute(f"SET LOCAL statement_timeout = {settings.sql_timeout_ms}")
            rows = conn.execute(_sql(wrapped), tuple(params)).fetchall()
            return [_decode(r) for r in rows]
        finally:
            conn.rollback()
            conn.close()

    conn = _sqlite_connect(readonly=True)
    deadline = time.monotonic() + settings.sql_timeout_ms / 1000

    def authorizer(action, arg1, arg2, dbname, source):
        if action == sqlite3.SQLITE_READ:
            # Views read their underlying tables with `source` set to the view name.
            table = (arg1 or "").lower()
            if table in READONLY_TABLES or (source or "").lower() in READONLY_TABLES:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE):
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    conn.set_authorizer(authorizer)
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 2000)
    try:
        rows = conn.execute(wrapped, tuple(params)).fetchall()
        return [_decode(r) for r in rows]
    except sqlite3.DatabaseError as e:
        raise UnsafeQuery(f"query failed: {e}") from e
    finally:
        conn.close()


# --------------------------------------------------------------------------- run logging

def log_agent_run(*, run_ref: str, workflow: str, agent: str, steps: list, tokens: int,
                  duration_ms: int, status: str) -> int:
    return insert("agent_runs", {"run_ref": run_ref, "workflow": workflow, "agent": agent, "steps": steps,
                                 "tokens_used": tokens, "duration_ms": duration_ms, "status": status})


# --------------------------------------------------------------------------- moderation (human-in-the-loop)

def resolve_queue_item(item_id: int, action: str, merge_into: int | None = None, note: str | None = None) -> dict:
    """Moderator decision on a queued record: approve | reject | merge (new company -> existing company)."""
    with connect() as conn:
        item = query_one("SELECT * FROM moderation_queue WHERE id = ?", [item_id], conn)
        if not item:
            raise ValueError("queue item not found")
        rid = item.get("record_id")
        if action == "approve" and rid:
            update("offer_records", rid, {"status": "verified"}, conn)
        elif action == "reject" and rid:
            update("offer_records", rid, {"status": "rejected"}, conn)
        elif action == "merge" and rid and merge_into:
            rec = query_one("SELECT company_id FROM offer_records WHERE id = ?", [rid], conn)
            old = query_one("SELECT * FROM companies WHERE id = ?", [rec["company_id"]], conn)
            update("offer_records", rid, {"company_id": merge_into, "status": "verified"}, conn)
            for alias in old.get("aliases") or [old["name"]]:
                add_alias(merge_into, alias, conn)
            others = query_one("SELECT COUNT(*) AS n FROM offer_records WHERE company_id = ?", [old["id"]], conn)
            if others["n"] == 0:
                execute("UPDATE placement_drives SET company_id = ? WHERE company_id = ?", [merge_into, old["id"]], conn)
                execute("DELETE FROM subscriptions WHERE company_id = ?", [old["id"]], conn)
                execute("DELETE FROM data_requests WHERE company_id = ?", [old["id"]], conn)
                execute("DELETE FROM companies WHERE id = ?", [old["id"]], conn)
        elif action not in {"approve", "reject", "merge", "dismiss"}:
            raise ValueError("action must be approve, reject, merge or dismiss")
        update("moderation_queue", item_id, {"status": "resolved" if action != "reject" else "rejected",
                                             "note": (item.get("note") or "") + (f" | moderator: {note}" if note else "")},
               conn)
        return {"id": item_id, "action": action, "record_id": rid}


def resolve_conflict(conflict_id: int, keep_value: str | None = None) -> dict:
    """Close a conflict. If keep_value is given, records with other values for that field are rejected."""
    with connect() as conn:
        c = query_one("SELECT * FROM conflicts WHERE id = ?", [conflict_id], conn)
        if not c:
            raise ValueError("conflict not found")
        rejected = 0
        if c["field"] not in {"has_bond", "bond_months", "penalty_amount"}:
            raise ValueError("unexpected conflict field")
        if keep_value is not None:
            rows = query("SELECT id, " + c["field"] + " AS v FROM offer_records WHERE company_id = ? AND batch_year = ? "
                         "AND status = 'verified' AND source_type = 'upload'", [c["company_id"], c["batch_year"]], conn)
            for r in rows:
                if str(r["v"]) != str(keep_value):
                    update("offer_records", r["id"], {"status": "rejected"}, conn)
                    rejected += 1
        update("conflicts", conflict_id, {"status": "resolved"}, conn)
        return {"id": conflict_id, "rejected_records": rejected}
