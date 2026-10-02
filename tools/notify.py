"""send_email via Resend. Without RESEND_API_KEY, emails are written to data/outbox/ for inspection."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import httpx

from core.config import DATA_DIR, settings

OUTBOX = DATA_DIR / "outbox"


def send_email(to: str, subject: str, body: str, html: str | None = None) -> dict:
    if settings.resend_api_key:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={"from": settings.alert_from, "to": [to], "subject": subject, "text": body,
                  **({"html": html} if html else {})},
            timeout=15,
        )
        resp.raise_for_status()
        return {"delivered": True, "provider": "resend", "id": resp.json().get("id")}
    OUTBOX.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    safe = re.sub(r"[^a-z0-9]+", "_", to.lower())
    path = OUTBOX / f"{stamp}_{safe}.json"
    path.write_text(json.dumps({"to": to, "subject": subject, "body": body, "html": html}, indent=2), encoding="utf-8")
    return {"delivered": False, "provider": "outbox", "path": str(path)}
