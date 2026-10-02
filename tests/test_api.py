import json

from fastapi.testclient import TestClient

from api.main import app
from core.config import settings


def _events(resp):
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def test_public_endpoints(seeded_db):
    c = TestClient(app)
    assert c.get("/health").json()["ok"]
    assert c.get("/stats").json()["verified_uploads"] > 0
    cos = c.get("/companies").json()
    assert cos and "summary" in cos[0]
    detail = c.get(f"/company/{cos[0]['id']}").json()
    assert detail["records"] and detail["records"][0]["evidence"]
    assert c.post("/calc/exit-cost", json={"penalty": 100000, "bond_months": 12, "months_served": 6,
                                           "prorated": "yes"}).json()["amount"] == 50000


def test_upload_stream_and_ask(seeded_db):
    c = TestClient(app)
    events = _events(c.post("/upload", files={"file": ("note.txt", b"Shopping list: rice, dal", "text/plain")}))
    assert events[-1]["kind"] == "result" and events[-1]["result"]["status"] == "rejected"
    events = _events(c.post("/ask", json={"question": "What is the bond at Nexora Technologies?"}))
    assert any(e.get("agent") == "Q&A Agent" for e in events)
    assert events[-1]["result"]["citations"]


def test_admin_requires_token(seeded_db):
    c = TestClient(app)
    assert c.get("/admin/queue").status_code == 401
    items = c.get("/admin/queue", headers={"x-admin-token": settings.admin_token}).json()
    assert any(i["reason"] == "outlier" for i in items)
    assert c.get("/cron/monitor").status_code == 401
    assert c.get("/cron/monitor", headers={"authorization": f"Bearer {settings.cron_secret}"}).json()["result"]


def test_subscribe(seeded_db):
    c = TestClient(app)
    r = c.post("/subscribe", json={"email": "new.student@example.com", "company_ids": [1, 2], "alert_all": True})
    assert r.json()["subscribed"] == 2
    assert c.post("/subscribe", json={"email": "not-an-email", "company_ids": [1]}).status_code == 422
