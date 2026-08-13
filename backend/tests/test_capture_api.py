"""Integration tests for the capture API: ingest, query, verify, tamper-detection."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sphinx.core import capture_service
from sphinx.main import app

client = TestClient(app)


@pytest.fixture()
def fresh_db(db):
    """Use the per-test wiped DB fixture from conftest."""
    yield db


def _events(n=3, **over):
    base = [
        {
            "event_type": "tool_call",
            "event_name": "lookup_order",
            "input_payload": {"order_id": f"ORD-{i}"},
            "output_payload": {"ok": True},
            "metadata": {"duration_ms": 10 * i},
        }
        for i in range(n)
    ]
    for i, patch in enumerate(over.get("patches", [])):
        base[i].update(patch)
    return base


class TestIngest:
    def test_ingest_single(self, db):
        r = client.post(
            "/api/capture",
            json={"agent_id": "a1", "session_id": "s1", "events": _events(1)},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["received"] == 1
        ev = body["last"]
        assert ev["agent_id"] == "a1"
        assert ev["sequence"] == 1
        assert ev["prev_hash"] is None
        assert len(ev["content_hash"]) == 64
        assert ev["signature"]

    def test_ingest_batch_chains_sequentially(self, db):
        r = client.post(
            "/api/capture",
            json={"agent_id": "a2", "session_id": "s1", "events": _events(3)},
        )
        body = r.json()
        assert body["received"] == 3
        first, last = body["first"], body["last"]
        assert first["sequence"] == 1
        assert last["sequence"] == 3
        assert first["prev_hash"] is None
        # the last event links to the *previous* event's hash, not the first's
        assert last["prev_hash"] is not None
        assert last["prev_hash"] != first["content_hash"]

    def test_ingest_two_events_link_directly(self, db):
        r = client.post(
            "/api/capture",
            json={"agent_id": "a2b", "session_id": "s1", "events": _events(2)},
        )
        body = r.json()
        assert body["received"] == 2
        first, last = body["first"], body["last"]
        assert last["prev_hash"] == first["content_hash"]

    def test_ingest_requires_agent_id(self, db):
        r = client.post("/api/capture", json={"session_id": "s1", "events": _events(1)})
        assert r.status_code == 422

    def test_ingest_rejects_bad_event_type(self, db):
        r = client.post(
            "/api/capture",
            json={"agent_id": "a1", "session_id": "s1", "events": _events(1, patches=[{"event_type": "nope"}])},
        )
        assert r.status_code == 422  # schema regex

    def test_ingest_rejects_empty_events(self, db):
        r = client.post("/api/capture", json={"agent_id": "a1", "session_id": "s1", "events": []})
        assert r.status_code == 422

    def test_ingest_unknown_type_via_service(self, db):
        from sphinx.core import capture_service

        key = capture_service.get_signing_key(db)
        with pytest.raises(ValueError):
            capture_service.ingest_event(
                db, signing_key=key, agent_id="a1", session_id="s1",
                event_type="bogus", event_name="x",
            )


class TestQuery:
    def test_list_returns_ingested(self, db):
        client.post("/api/capture", json={"agent_id": "q1", "session_id": "s1", "events": _events(2)})
        r = client.get("/api/capture", params={"agent_id": "q1"})
        assert r.status_code == 200
        assert r.json()["total"] == 2

    def test_filter_by_event_type(self, db):
        client.post("/api/capture", json={"agent_id": "q2", "session_id": "s1", "events": [
            {"event_type": "tool_call", "event_name": "t", "input_payload": {}, "output_payload": {}},
            {"event_type": "llm_inference", "event_name": "l", "input_payload": {}, "output_payload": {}},
        ]})
        r = client.get("/api/capture", params={"agent_id": "q2", "event_type": "llm_inference"})
        assert r.json()["total"] == 1
        assert r.json()["items"][0]["event_type"] == "llm_inference"

    def test_filter_by_session(self, db):
        client.post("/api/capture", json={"agent_id": "q3", "session_id": "sess-a", "events": _events(1)})
        client.post("/api/capture", json={"agent_id": "q3", "session_id": "sess-b", "events": _events(1)})
        r = client.get("/api/capture", params={"agent_id": "q3", "session_id": "sess-b"})
        assert r.json()["total"] == 1
        assert r.json()["items"][0]["session_id"] == "sess-b"

    def test_pagination(self, db):
        client.post("/api/capture", json={"agent_id": "q4", "session_id": "s1", "events": _events(5)})
        r = client.get("/api/capture", params={"agent_id": "q4", "limit": 2, "offset": 2})
        assert r.json()["total"] == 5
        assert len(r.json()["items"]) == 2


class TestVerify:
    def test_verify_valid_chain(self, db):
        client.post("/api/capture", json={"agent_id": "v1", "session_id": "s1", "events": _events(3)})
        r = client.get("/api/capture/verify", params={"agent_id": "v1"})
        assert r.status_code == 200
        assert r.json()["valid"] is True
        assert r.json()["checked"] == 3
        assert r.json()["chains"] == 1

    def test_verify_multiple_sessions(self, db):
        client.post("/api/capture", json={"agent_id": "v2", "session_id": "s1", "events": _events(2)})
        client.post("/api/capture", json={"agent_id": "v2", "session_id": "s2", "events": _events(2)})
        r = client.get("/api/capture/verify", params={"agent_id": "v2"})
        assert r.json()["valid"] is True
        assert r.json()["checked"] == 4
        assert r.json()["chains"] == 2

    def test_verify_detects_db_tamper(self, db):
        client.post("/api/capture", json={"agent_id": "v3", "session_id": "s1", "events": _events(2)})
        # tamper with the stored output payload directly in the DB
        from sphinx.db import SessionLocal
        from sphinx.models import CaptureEvent

        with SessionLocal() as s:
            ev = s.query(CaptureEvent).filter(CaptureEvent.agent_id == "v3").order_by(CaptureEvent.sequence).first()
            ev.output_payload = {"evil": True}
            s.commit()
        r = client.get("/api/capture/verify", params={"agent_id": "v3"})
        assert r.json()["valid"] is False
        assert any("content hash mismatch" in e for e in r.json()["errors"])

    def test_verify_empty_ok(self, db):
        r = client.get("/api/capture/verify", params={"agent_id": "ghost"})
        assert r.json()["valid"] is True
        assert r.json()["checked"] == 0

    def test_signing_key_persists_across_requests(self, db):
        k1 = capture_service.get_signing_key(db)
        k2 = capture_service.get_signing_key(db)
        assert bytes(k1) == bytes(k2)
