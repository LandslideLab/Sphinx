"""WebSocket live-update tests: mutations must publish events over /api/ws."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sphinx.main import create_app


@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def _hello(ws):
    evt = ws.receive_json()
    assert evt["topic"] == "hello"
    return evt


def _create_pending(client):
    r = client.post(
        "/api/requests",
        json={"agent_id": "ws-agent", "title": "WS flow", "action_payload": {"action": "deploy"}, "risk_level": "high"},
    )
    assert r.status_code == 201
    return r.json()


class TestEventStream:
    def test_create_publishes_request_event(self, client):
        with client.websocket_connect("/api/ws") as ws:
            _hello(ws)
            req = _create_pending(client)
            evt = ws.receive_json()
            assert evt["topic"] == "requests"
            assert evt["data"]["type"] == "created"
            assert evt["data"]["request"]["id"] == req["id"]
            assert evt["data"]["request"]["status"] == "pending"

    def test_approve_publishes_decided_event(self, client):
        with client.websocket_connect("/api/ws") as ws:
            _hello(ws)
            req = _create_pending(client)
            ws.receive_json()  # consume created

            r = client.post(f"/api/requests/{req['id']}/approve", json={"reviewer_id": "alice", "note": "go"})
            assert r.status_code == 200
            evt = ws.receive_json()
            assert evt["topic"] == "requests"
            assert evt["data"]["type"] == "decided"
            assert evt["data"]["request"]["status"] == "approved"

    def test_reject_escalate_cancel_feedback_publish(self, client):
        with client.websocket_connect("/api/ws") as ws:
            _hello(ws)

            # reject
            req = _create_pending(client)
            ws.receive_json()
            client.post(f"/api/requests/{req['id']}/reject", json={"reviewer_id": "alice"})
            assert ws.receive_json()["data"]["type"] == "decided"

            # escalate
            req2 = _create_pending(client)
            ws.receive_json()
            client.post(f"/api/requests/{req2['id']}/escalate", json={"reviewer_id": "alice"})
            assert ws.receive_json()["data"]["type"] == "escalated"

            # cancel
            req3 = _create_pending(client)
            ws.receive_json()
            client.post(f"/api/requests/{req3['id']}/cancel")
            assert ws.receive_json()["data"]["type"] == "cancelled"

            # feedback
            req4 = _create_pending(client)
            ws.receive_json()
            client.post(f"/api/requests/{req4['id']}/approve", json={"reviewer_id": "alice"})
            ws.receive_json()
            client.post(f"/api/requests/{req4['id']}/feedback", json={"outcome": "success"})
            assert ws.receive_json()["data"]["type"] == "feedback"

    def test_policy_change_publishes(self, client):
        with client.websocket_connect("/api/ws") as ws:
            _hello(ws)
            r = client.post(
                "/api/policies",
                json={"name": "ws-policy-xyz", "risk_levels": ["low"], "timeout_seconds": 30, "on_timeout": "auto_approve"},
            )
            assert r.status_code == 201
            evt = ws.receive_json()
            assert evt["topic"] == "policies"
            assert evt["data"]["type"] == "created"
            assert evt["data"]["policy"]["name"] == "ws-policy-xyz"

    def test_two_ws_clients_both_get_events(self, client):
        with client.websocket_connect("/api/ws") as ws1, client.websocket_connect("/api/ws") as ws2:
            _hello(ws1)
            _hello(ws2)
            req = _create_pending(client)
            e1 = ws1.receive_json()
            e2 = ws2.receive_json()
            assert e1["data"]["request"]["id"] == req["id"]
            assert e2["data"]["request"]["id"] == req["id"]

    def test_disconnect_does_not_break_others(self, client):
        with client.websocket_connect("/api/ws") as ws1:
            _hello(ws1)
            with client.websocket_connect("/api/ws") as ws2:
                _hello(ws2)
            # ws2 disconnected
            req = _create_pending(client)
            evt = ws1.receive_json()
            assert evt["data"]["request"]["id"] == req["id"]
