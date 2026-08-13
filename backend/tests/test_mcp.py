"""MCP server integration tests against a live Sphinx MCP server."""
from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from sphinx_sdk.client import McpTransport, SphinxClient


@pytest.fixture()
def mcp_client(live):
    client = McpTransport(url=live.mcp_url)
    yield client
    client.close()


def _approve(live, request_id: str):
    r = httpx.post(f"{live.api_url}/api/requests/{request_id}/approve", json={"reviewer_id": "mcp-test", "note": "ok"}, timeout=5)
    assert r.status_code == 200


class TestMcpTransport:
    def test_list_policies(self, mcp_client):
        policies = mcp_client.list_policies()
        assert len(policies) >= 4
        names = {p["name"] for p in policies}
        assert {"standard-review", "low-risk-auto", "high-risk-gate", "release-sla"} <= names

    def test_request_and_get_status(self, mcp_client):
        ticket = mcp_client.request_approval(
            agent_id="mcp-agent",
            title="MCP deploy to staging",
            action_payload={"action": "deploy", "env": "staging"},
            risk_level="medium",
            framework="langgraph",
        )
        assert ticket.ref.startswith("SPH-")
        assert ticket.status == "pending"

        status = mcp_client.get_status(ticket.id)
        assert status["status"] == "pending"
        assert status["escalated"] is False

    def test_get_decision_after_approve(self, mcp_client, live):
        ticket = mcp_client.request_approval(
            agent_id="mcp-agent",
            title="MCP release",
            action_payload={"action": "release", "version": "v2.4.0"},
            risk_level="high",
        )
        _approve(live, ticket.id)
        decision = mcp_client.get_decision(ticket.id)
        assert decision["approved"] is True
        assert decision["decision_payload"]["version"] == "v2.4.0"
        assert decision["resolved_by"] == "human"

    def test_wait_for_decision_returns_after_human(self, mcp_client, live):
        ticket = mcp_client.request_approval(
            agent_id="mcp-agent",
            title="MCP wait flow",
            action_payload={"action": "config"},
            risk_level="medium",
        )
        _approve(live, ticket.id)
        result = mcp_client.wait_for_decision(ticket.id, timeout_s=30, poll_interval_s=0.5)
        assert result["approved"] is True
        assert result["status"] == "approved"

    def test_submit_feedback(self, mcp_client, live):
        ticket = mcp_client.request_approval(
            agent_id="mcp-agent",
            title="MCP feedback flow",
            action_payload={"action": "migrate"},
            risk_level="medium",
        )
        _approve(live, ticket.id)
        result = mcp_client.submit_feedback(ticket.id, outcome="success", note="went fine", agent_id="mcp-agent")
        assert result["outcome"] == "success"
        assert result["ref"].startswith("SPH-")

    def test_resource_readable(self, mcp_client):
        ticket = mcp_client.request_approval(agent_id="mcp-agent", title="resource", action_payload={"a": 1}, risk_level="medium")
        loop = mcp_client._loop
        fut = asyncio.run_coroutine_threadsafe(_read_resource(mcp_client, ticket.id), loop)
        text = fut.result(timeout=30)
        assert ticket.ref in text


async def _read_resource(client, request_id):
    from mcp import ClientSession

    session = client._session
    if isinstance(session, ClientSession):
        result = await session.read_resource(f"sphinx://requests/{request_id}")
        return result.contents[0].text if result.contents else ""
    return ""


class TestEndToEndViaClient:
    def test_full_lifecycle_mcp(self, live):
        with SphinxClient(transport="mcp", mcp_url=live.mcp_url, agent_id="e2e-agent", framework="openai") as client:
            ticket = client.request_approval(
                "E2E refund",
                {"action": "refund", "amount": 500},
                description="e2e",
                risk_level="medium",
            )
            _approve(live, ticket.id)
            decision = client.wait_for_decision(ticket.id, timeout_s=30, poll_interval_s=0.5)
            assert decision["approved"] is True
            assert decision["decision_payload"]["amount"] == 500
            fb = client.submit_feedback(ticket.id, "success", note="e2e done")
            assert fb["outcome"] == "success"
