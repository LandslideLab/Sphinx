"""SDK integration tests: RestTransport, high-level client and framework adapters."""
from __future__ import annotations

import threading
from contextlib import contextmanager

import httpx
import pytest

from sphinx_sdk.adapters.crewai import sphinx_human_input
from sphinx_sdk.adapters.langgraph import HITLGuard, hitl_interrupt_node
from sphinx_sdk.adapters.openai import ApprovalGate, openai_tool_callback
from sphinx_sdk.client import SphinxClient


def _approve(live, request_id: str):
    r = httpx.post(f"{live.api_url}/api/requests/{request_id}/approve", json={"reviewer_id": "sdk-test", "note": "ok"}, timeout=5)
    assert r.status_code == 200, r.text


@contextmanager
def _auto_decider(live, approve: bool = True, interval_s: float = 0.3):
    """Decides every new pending ticket in the background (simulated human)."""
    stop = threading.Event()
    seen: set[str] = set()

    def run():
        while not stop.is_set():
            try:
                r = httpx.get(f"{live.api_url}/api/requests?status=pending&limit=100", timeout=5)
                for item in r.json()["items"]:
                    if item["id"] in seen:
                        continue
                    seen.add(item["id"])
                    verb = "approve" if approve else "reject"
                    note = "auto-approved" if approve else "auto-rejected"
                    httpx.post(f"{live.api_url}/api/requests/{item['id']}/{verb}", json={"reviewer_id": "auto", "note": note}, timeout=5)
            except Exception:
                pass
            stop.wait(interval_s)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        t.join(timeout=3)


class TestRestTransport:
    def test_roundtrip(self, live):
        from sphinx_sdk.client import RestTransport

        t = RestTransport(base_url=live.api_url)
        ticket = t.request_approval(
            agent_id="rest-agent",
            title="Rest roundtrip",
            action_payload={"action": "run"},
            risk_level="medium",
        )
        assert ticket.status == "pending"
        status = t.get_status(ticket.id)
        assert status["status"] == "pending"

        _approve(live, ticket.id)
        decision = t.get_decision(ticket.id)
        assert decision["approved"] is True

        wait = t.wait_for_decision(ticket.id, timeout_s=30, poll_interval_s=0.5)
        assert wait["approved"] is True

        fb = t.submit_feedback(ticket.id, "failure", note="broke", agent_id="rest-agent")
        assert fb["outcome"] == "failure"

        policies = t.list_policies()
        assert len(policies) >= 4

    def test_wait_for_decision_times_out(self, live):
        from sphinx_sdk.client import RestTransport, SphinxTimeout

        t = RestTransport(base_url=live.api_url)
        ticket = t.request_approval(
            agent_id="rest-agent",
            title="Never decided",
            action_payload={},
            risk_level="high",
        )
        with pytest.raises(SphinxTimeout):
            t.wait_for_decision(ticket.id, timeout_s=1, poll_interval_s=0.2)


class TestSphinxClient:
    def test_high_level_flow(self, live):
        with SphinxClient(base_url=live.api_url, agent_id="hl-agent", framework="crewai", session_id="sess-hl") as client:
            ticket = client.request_approval(
                "High level refund",
                {"action": "refund", "amount": 42},
                description="from SDK",
                risk_level="medium",
                metadata={"origin": "test"},
            )
            _approve(live, ticket.id)
            decision = client.wait_for_decision(ticket.id, timeout_s=30, poll_interval_s=0.5)
            assert decision["approved"] is True
            assert decision["decision_payload"]["amount"] == 42
            fb = client.submit_feedback(ticket.id, "success", note="ok")
            assert fb["outcome"] == "success"

    def test_request_errors_surface(self, live):
        with SphinxClient(base_url=live.api_url) as client:
            with pytest.raises(Exception):
                client.request_approval("", {}, risk_level="medium")


class TestLangGraphAdapter:
    def test_guard_flow(self, live):
        guard = HITLGuard("lg-agent", base_url=live.api_url, transport="rest")
        ticket = guard.request("LG refund", {"action": "refund", "amount": 10}, risk_level="medium")
        _approve(live, ticket["id"])
        decision = guard.wait(ticket)
        assert decision["approved"] is True
        assert decision["decision_payload"]["amount"] == 10

    def test_guard_single_call(self, live):
        guard = HITLGuard("lg-agent", base_url=live.api_url, transport="rest")
        with _auto_decider(live):
            decision = guard.guard("guard one", {"action": "x"}, risk_level="medium")
            assert decision["approved"] is True

    def test_hitl_interrupt_node(self, live):
        guard = HITLGuard("lg-agent", base_url=live.api_url, transport="rest")
        node = hitl_interrupt_node(guard, action_key="proposed_action", result_key="approval")
        # no proposed action -> skipped
        out = node({"session_id": "s1"})
        assert out["approval"]["skipped"] is True

        with _auto_decider(live):
            out = node({"session_id": "s1", "proposed_action": {"title": "node action", "payload": {"action": "deploy"}, "risk_level": "medium"}})
            assert out["approval"]["approved"] is True


class TestOpenAIAdapter:
    def test_approval_gate_check(self, live):
        gate = ApprovalGate("oa-agent", base_url=live.api_url, transport="rest")
        with _auto_decider(live):
            decision = gate.check(
                {"name": "execute_refund", "arguments": {"amount": 33}},
                risk_level="medium",
            )
            assert decision["approved"] is True
            assert decision["decision_payload"]["tool"] == "execute_refund"

    def test_check_with_json_string(self, live):
        gate = ApprovalGate("oa-agent", base_url=live.api_url, transport="rest")
        import json

        with _auto_decider(live):
            decision = gate.check(json.dumps({"name": "x", "arguments": {}}), risk_level="medium")
            assert decision["approved"] is True

    def test_check_nonblocking(self, live):
        gate = ApprovalGate("oa-agent", base_url=live.api_url, transport="rest")
        result = gate.check({"name": "slow_tool", "arguments": {}}, risk_level="medium", wait=False)
        assert result["status"] == "pending"

    def test_openai_tool_callback(self, live):
        gate = ApprovalGate("oa-agent", base_url=live.api_url, transport="rest")
        cb = openai_tool_callback(gate, risk_level="medium")

        class _FakeEvent:
            name = "send_email"
            arguments = '{"to": "a@b.c"}'

        with _auto_decider(live):
            decision = cb(_FakeEvent())
            assert decision["approved"] is True


class TestCrewAIAdapter:
    def test_crewai_callback(self, live):
        cb = sphinx_human_input("crew-agent", base_url=live.api_url, transport="rest")
        with _auto_decider(live):
            result = cb(object(), "approve_payment", prompt="Pay the vendor", amount=500)
            assert "_blocked" not in result
            assert result["step"] == "approve_payment"

    def test_crewai_callback_blocked(self, live):
        cb = sphinx_human_input("crew-agent", base_url=live.api_url, transport="rest")
        with _auto_decider(live, approve=False):
            result = cb(object(), "risky", prompt="Do the risky thing")
            assert result["_blocked"] is True
