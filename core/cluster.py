"""Running as several replicas behind a Kubernetes Service.

Almost every endpoint is stateless (all data lives in PostgreSQL), so the Service can send any
request to any pod. One flow is stateful by design: an upload that pauses for the uploader to
confirm uncertain fields keeps its LangGraph checkpoint *in the memory of the pod that ran it*,
so the document's text never reaches disk or the database.

To let any replica accept the follow-up `POST /upload/{id}/confirm`, the pod that pauses an
upload records itself as the owner in `upload_owners` (upload id -> pod address, no document
data). A replica that receives a confirmation for an upload it doesn't hold forwards the request
to the owner pod and streams the owner's response back. If the owner pod is gone, the upload has
expired, exactly as it would after a restart of a single instance.

Cluster mode is on when `POD_IP` is set (the Deployment injects it via the downward API). Without
it (local dev, Render, tests) every function here is a no-op.
"""
from __future__ import annotations

import logging
import os
import socket

log = logging.getLogger("bondcheck.cluster")

INSTANCE = os.getenv("POD_NAME") or socket.gethostname()
POD_IP = os.getenv("POD_IP", "")
PORT = int(os.getenv("PORT", "8000"))
FORWARDED_HEADER = "X-BondCheck-Forwarded-By"
OWNER_TTL_HOURS = 24


def enabled() -> bool:
    return bool(POD_IP)


def self_url() -> str:
    host = f"[{POD_IP}]" if ":" in POD_IP else POD_IP  # IPv6 pod addresses need brackets
    return f"http://{host}:{PORT}" if POD_IP else ""


def claim(upload_id: str) -> None:
    """Record this pod as the holder of a paused upload's checkpoint."""
    if not enabled():
        return
    from tools import database as db

    try:
        with db.connect() as c:
            db.execute("DELETE FROM upload_owners WHERE upload_id = ?", [upload_id], conn=c)
            db.execute("INSERT INTO upload_owners (upload_id, owner_url, instance) VALUES (?, ?, ?)",
                       [upload_id, self_url(), INSTANCE], conn=c)
        _prune()
    except Exception:  # never break an upload over bookkeeping; the confirm will just 404 elsewhere
        log.exception("could not record owner of upload %s", upload_id)


def owner_url(upload_id: str) -> str | None:
    if not enabled():
        return None
    from tools import database as db

    try:
        row = db.query_one("SELECT owner_url FROM upload_owners WHERE upload_id = ?", [upload_id])
    except Exception:
        log.exception("could not look up owner of upload %s", upload_id)
        return None
    return row["owner_url"] if row else None


def release(upload_id: str) -> None:
    if not enabled():
        return
    from tools import database as db

    try:
        db.execute("DELETE FROM upload_owners WHERE upload_id = ?", [upload_id])
    except Exception:
        log.exception("could not release upload %s", upload_id)


def _prune() -> None:
    """Drop ownership rows for uploads abandoned long ago (their checkpoints are gone anyway)."""
    from datetime import datetime, timedelta, timezone

    from tools import database as db

    cutoff = datetime.now(timezone.utc) - timedelta(hours=OWNER_TTL_HOURS)
    db.execute("DELETE FROM upload_owners WHERE created_at < ?",
               [cutoff if db.settings.use_postgres else cutoff.strftime("%Y-%m-%d %H:%M:%S")])
