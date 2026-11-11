"""Multi-replica behaviour (Kubernetes): pod identity, readiness, and forwarding a paused upload's
confirmation to the replica that holds its in-memory checkpoint."""
import json
import random

import httpx
import pytest
from fastapi.testclient import TestClient

import api.main as main
from agents import orchestrator
from core import cluster
from eval.letters import COMPANIES, make_letter, render_pdf
from tools import database as db

OWNER = "http://10.0.0.9:8000"
SELF = "http://10.0.0.5:8000"


def _events(text: str):
    return [json.loads(line) for line in text.splitlines() if line.strip()]


@pytest.fixture
def cluster_mode(monkeypatch):
    monkeypatch.setattr(cluster, "POD_IP", "10.0.0.5")
    monkeypatch.setattr(cluster, "INSTANCE", "bondcheck-api-test-a")


def _paused_upload() -> str:
    """An upload whose penalty is unclear, so the graph pauses for the uploader."""
    text = make_letter(777, random.Random(7), COMPANIES[13], 2026, "formal").text
    text = "\n".join(
        "4. You agree to serve the Company for a minimum period of 12 months, failing which liquidated damages "
        "as determined by the management are payable." if ("bond amount" in ln or "liquidated" in ln or "sum of" in ln)
        else ln for ln in text.split("\n"))
    ctx = orchestrator.start_upload(render_pdf(text), "z.pdf", background=False)
    assert ctx.result["status"] == "needs_confirmation"
    return ctx.result["upload_id"]


def test_every_response_names_the_pod_and_ready_checks_db(seeded_db, cluster_mode):
    c = TestClient(main.app)
    r = c.get("/health")
    assert r.headers["x-served-by"] == "bondcheck-api-test-a"
    assert r.json()["instance"] == "bondcheck-api-test-a"
    assert c.get("/ready").json() == {"ready": True, "instance": "bondcheck-api-test-a"}


def test_ready_fails_when_database_is_down(seeded_db, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(main.db, "query_one", boom)
    assert TestClient(main.app).get("/ready").status_code == 503


def test_owner_registry_is_noop_outside_cluster(seeded_db):
    cluster.claim("abc")
    assert cluster.owner_url("abc") is None


def test_paused_upload_is_claimed_and_released(seeded_db, cluster_mode):
    upload_id = _paused_upload()
    assert cluster.owner_url(upload_id) == SELF
    orchestrator.resume_upload(upload_id, {"penalty_amount": "50000"}, background=False)
    assert cluster.owner_url(upload_id) is None


def test_confirm_on_another_replica_is_forwarded_to_the_owner(seeded_db, cluster_mode, monkeypatch):
    """Two 'pods' in one process: the receiving pod doesn't hold the checkpoint, looks up the
    owner and relays the request; the owner (the same app, reached through the forwarded hop)
    resumes the graph and streams the result back."""
    upload_id = _paused_upload()
    owner_app = TestClient(main.app)
    seen = {}

    def owner_pod(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["forwarded_by"] = request.headers.get(cluster.FORWARDED_HEADER)
        r = owner_app.post(request.url.path, content=request.content,
                           headers={"content-type": "application/json",
                                    cluster.FORWARDED_HEADER: request.headers[cluster.FORWARDED_HEADER]})
        return httpx.Response(r.status_code, content=r.content,
                              headers={"x-served-by": "bondcheck-api-test-b"})

    real_client = httpx.Client
    monkeypatch.setattr(main.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(owner_pod), **kw))
    monkeypatch.setattr(main.cluster, "owner_url", lambda _id: OWNER)
    # Only the receiving pod's check says "not here"; the owner's own check (in resume_upload) is real.
    real_is_waiting, calls = orchestrator.is_waiting, []
    monkeypatch.setattr(orchestrator, "is_waiting",
                        lambda _id: real_is_waiting(_id) if calls.append(_id) or len(calls) > 1 else False)

    r = TestClient(main.app).post(f"/upload/{upload_id}/confirm", json={"answers": {"penalty_amount": "50000"}})
    assert r.status_code == 200
    assert r.headers["x-upload-owner"] == "bondcheck-api-test-b"
    assert seen == {"url": f"{OWNER}/upload/{upload_id}/confirm", "forwarded_by": "bondcheck-api-test-a"}
    result = _events(r.text)[-1]["result"]
    assert result["status"] == "stored"
    assert db.get_evidence(result["record_id"])["penalty_amount"] == 50000


def test_confirm_for_a_vanished_owner_pod_expires(seeded_db, cluster_mode, monkeypatch):
    def unreachable(request):
        raise httpx.ConnectError("no route to host", request=request)

    real_client = httpx.Client
    released = []
    monkeypatch.setattr(main.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(unreachable), **kw))
    monkeypatch.setattr(main.cluster, "owner_url", lambda _id: OWNER)
    monkeypatch.setattr(main.cluster, "release", released.append)
    r = TestClient(main.app).post("/upload/deadbeef0000/confirm", json={"answers": {}})
    assert r.status_code == 404 and "expired" in r.json()["detail"]
    assert released == ["deadbeef0000"]


def test_unknown_upload_still_404s_in_cluster_mode(seeded_db, cluster_mode):
    r = TestClient(main.app).post("/upload/nosuchupload/confirm", json={"answers": {}})
    assert r.status_code == 404
