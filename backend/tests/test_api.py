"""REST API integration tests against the FastAPI app (TestClient)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sphinx.main import create_app


@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def _create(client, **over):
    body = {
        "agent_id": "api-test-agent",
        "title": "Approve refund of $300",
        "action_payload": {"action": "refund", "amount": 300.0},
        "risk_level": "medium",
        **over,
    }
    r = client.post("/api/requests", json=body)
    assert r.status_code == 201, r.text
    return r.json()


class TestHealth:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_health_when_db_empty(self):
        pass  # smoke guard


class TestRequests:
    def test_create_and_get(self, client):
        req = _create(client)
        assert req["status"] == "pending"
        assert req["policy_name"] == "standard-review"
        got = client.get(f"/api/requests/{req['id']}").json()
        assert got["id"] == req["id"]
        assert got["ref"] == req["ref"]

    def test_create_by_ref_lookup(self, client):
        req = _create(client)
        got = client.get(f"/api/requests/{req['ref']}").json()
        assert got["id"] == req["id"]

    def test_create_missing_body_422(self, client):
        r = client.post("/api/requests", json={})
        assert r.status_code == 422

    def test_create_validation_error(self, client):
        r = client.post("/api/requests", json={"agent_id": "", "title": "", "action_payload": {}})
        assert r.status_code == 422

    def test_low_risk_auto_approves(self, client):
        req = _create(client, risk_level="low")
        assert req["status"] == "auto_approved"

    def test_list_filters(self, client):
        _create(client, title="Filter me 99111", agent_id="filter-agent")
        r = client.get("/api/requests", params={"agent_id": "filter-agent"}).json()
        assert r["total"] == 1
        assert r["items"][0]["agent_id"] == "filter-agent"

    def test_list_search_q(self, client):
        _create(client, title="UniqueSearchableTitleXYZ")
        r = client.get("/api/requests", params={"q": "UniqueSearchableTitleXYZ"}).json()
        assert r["total"] >= 1

    def test_list_invalid_status_400(self, client):
        r = client.get("/api/requests", params={"status": "bogus"})
        assert r.status_code == 400

    def test_list_pagination(self, client):
        for i in range(3):
            _create(client, title=f"pagination-{i}")
        r = client.get("/api/requests", params={"limit": 2, "offset": 0}).json()
        assert len(r["items"]) == 2
        assert r["total"] >= 3

    def test_get_404(self, client):
        assert client.get("/api/requests/nope").status_code == 404


class TestLifecycle:
    def test_approve_flow(self, client):
        req = _create(client)
        r = client.post(f"/api/requests/{req['id']}/approve", json={"reviewer_id": "alice", "note": "looks good"})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "approved"
        assert body["reviewer_id"] == "alice"
        assert body["decision_payload"] == req["action_payload"]

    def test_approve_amended_payload_records_delta(self, client):
        req = _create(client)
        r = client.post(
            f"/api/requests/{req['id']}/approve",
            json={
                "reviewer_id": "bob",
                "note": "lower amount",
                "decision_payload": {"action": "refund", "amount": 250.0},
                "amend": True,
            },
        )
        assert r.status_code == 200
        assert r.json()["decision_payload"]["amount"] == 250.0
        decisions = client.get("/api/decisions", params={"source": "human_review"}).json()["items"]
        mine = [d for d in decisions if d["request_id"] == req["id"]]
        assert len(mine) == 1
        assert mine[0]["agreement"] is False
        assert any(c["path"] == "amount" for c in mine[0]["delta"])

    def test_reject_flow(self, client):
        req = _create(client)
        r = client.post(f"/api/requests/{req['id']}/reject", json={"reviewer_id": "carol", "note": "denied"})
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"
        assert r.json()["decision_payload"] is None

    def test_escalate_flow(self, client):
        req = _create(client)
        r = client.post(f"/api/requests/{req['id']}/escalate", json={"reviewer_id": "dave", "note": "needs sr review"})
        assert r.status_code == 200
        assert r.json()["escalated"] is True
        assert r.json()["status"] == "pending"

    def test_cancel_flow(self, client):
        req = _create(client)
        r = client.post(f"/api/requests/{req['id']}/cancel")
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"

    def test_feedback_flow(self, client):
        req = _create(client)
        client.post(f"/api/requests/{req['id']}/approve", json={"reviewer_id": "alice"})
        r = client.post(f"/api/requests/{req['id']}/feedback", json={"outcome": "failure", "note": "it broke"})
        assert r.status_code == 200
        assert r.json()["outcome"] == "failure"

    def test_act_on_decided_returns_409(self, client):
        req = _create(client)
        client.post(f"/api/requests/{req['id']}/approve", json={"reviewer_id": "alice"})
        assert client.post(f"/api/requests/{req['id']}/approve", json={}).status_code == 409
        assert client.post(f"/api/requests/{req['id']}/reject", json={}).status_code == 409
        assert client.post(f"/api/requests/{req['id']}/escalate", json={}).status_code == 409
        assert client.post(f"/api/requests/{req['id']}/cancel").status_code == 409

    def test_feedback_on_pending_409(self, client):
        req = _create(client)
        r = client.post(f"/api/requests/{req['id']}/feedback", json={"outcome": "success"})
        assert r.status_code == 409

    def test_feedback_invalid_outcome_422(self, client):
        req = _create(client)
        client.post(f"/api/requests/{req['id']}/approve", json={"reviewer_id": "alice"})
        r = client.post(f"/api/requests/{req['id']}/feedback", json={"outcome": "bogus"})
        assert r.status_code == 422


class TestPolicies:
    def test_list_seeded_policies(self, client):
        r = client.get("/api/policies")
        assert r.status_code == 200
        names = {p["name"] for p in r.json()["items"]}
        assert {"standard-review", "low-risk-auto", "high-risk-gate", "release-sla"} <= names

    def test_create_policy(self, client):
        r = client.post(
            "/api/policies",
            json={
                "name": "custom-gate",
                "description": "custom",
                "risk_levels": ["critical"],
                "timeout_seconds": 120,
                "on_timeout": "auto_reject",
                "enabled": True,
            },
        )
        assert r.status_code == 201
        assert r.json()["on_timeout"] == "auto_reject"

    def test_create_duplicate_policy_409(self, client):
        body = {
            "name": "dup-policy",
            "risk_levels": ["medium"],
            "timeout_seconds": 60,
            "on_timeout": "escalate",
        }
        assert client.post("/api/policies", json=body).status_code == 201
        assert client.post("/api/policies", json=body).status_code == 409

    def test_update_policy(self, client):
        name = "update-me-policy"
        created = client.post(
            "/api/policies",
            json={"name": name, "risk_levels": ["medium"], "timeout_seconds": 60, "on_timeout": "escalate"},
        ).json()
        r = client.put(f"/api/policies/{created['id']}", json={"enabled": False, "timeout_seconds": 99})
        assert r.status_code == 200
        assert r.json()["enabled"] is False
        assert r.json()["timeout_seconds"] == 99

    def test_update_missing_policy_404(self, client):
        assert client.put("/api/policies/nope", json={"enabled": False}).status_code == 404

    def test_invalid_on_timeout_422(self, client):
        r = client.post(
            "/api/policies",
            json={"name": "bad", "risk_levels": ["low"], "timeout_seconds": 60, "on_timeout": "explode"},
        )
        assert r.status_code == 422


class TestDecisions:
    def test_list_decisions_after_approve(self, client):
        req = _create(client)
        client.post(f"/api/requests/{req['id']}/approve", json={"reviewer_id": "alice"})
        r = client.get("/api/decisions")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        assert any(d["request_id"] == req["id"] for d in items)

    def test_filter_by_agreement(self, client):
        req = _create(client)
        client.post(
            f"/api/requests/{req['id']}/approve",
            json={"reviewer_id": "bob", "decision_payload": {"action": "refund", "amount": 1.0}, "amend": True},
        )
        agreed = client.get("/api/decisions", params={"agreement": "true"}).json()
        disagreed = client.get("/api/decisions", params={"agreement": "false"}).json()
        mine_disagreed = [d for d in disagreed["items"] if d["request_id"] == req["id"]]
        assert len(mine_disagreed) == 1
        assert all(d["request_id"] != req["id"] for d in agreed["items"])


class TestMetrics:
    def test_metrics_shape(self, client):
        r = client.get("/api/metrics")
        assert r.status_code == 200
        m = r.json()
        assert set(m["governance"]) == {
            "escalation_rate",
            "timeout_rate",
            "correction_rate",
            "reviewer_agreement",
            "error_escape_rate",
            "sla_compliance_rate",
        }
        assert set(m["latency"]) == {"human_reviews", "avg_seconds", "p50_seconds", "p95_seconds"}
        assert set(m["risk"]) == {"low", "medium", "high", "critical"}

    def test_metrics_with_since_days(self, client):
        assert client.get("/api/metrics", params={"since_days": 7}).status_code == 200
