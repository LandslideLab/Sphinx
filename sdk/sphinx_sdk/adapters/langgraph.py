"""LangGraph adapter: wrap critical nodes with a HITL guard.

Pattern:
    from langgraph.graph import StateGraph
    from sphinx.adapters.langgraph import HITLGuard

    guard = HITLGuard("refund-agent")

    def risky_node(state):
        decision = guard.wait(state["proposed_action"])
        if not decision["approved"]:
            return {"blocked": True, "reason": decision.get("reviewer_note")}
        return {"executed_payload": decision["decision_payload"]}

    graph.add_node("risky", risky_node)

Requires: sphinx-sdk (langgraph itself is optional; the guard only calls Sphinx).
"""
from __future__ import annotations

import uuid
from typing import Any

from sphinx_sdk.client import SphinxClient, SphinxTimeout


class HITLGuard:
    """Requests approval for an agent action and blocks until a human (or policy) decides."""

    def __init__(
        self,
        agent_id: str,
        *,
        base_url: str = "http://localhost:8001",
        mcp_url: str = "http://localhost:8100/mcp",
        transport: str = "rest",
        default_wait_timeout_s: float = 600,
        default_poll_interval_s: float = 1.0,
    ):
        self.agent_id = agent_id
        self.client = SphinxClient(agent_id=agent_id, transport=transport, base_url=base_url, mcp_url=mcp_url)
        self.default_wait_timeout_s = default_wait_timeout_s
        self.default_poll_interval_s = default_poll_interval_s

    def request(
        self,
        title: str,
        action_payload: dict,
        *,
        description: str = "",
        risk_level: str = "medium",
        session_id: str = "",
        framework: str = "langgraph",
        priority: int = 1,
        metadata: dict | None = None,
    ) -> dict:
        """Register the approval request; returns the ticket. Non-blocking."""
        ticket = self.client.request_approval(
            title=title,
            action_payload=action_payload,
            description=description,
            risk_level=risk_level,
            session_id=session_id,
            framework=framework,
            priority=priority,
            metadata=metadata,
        )
        return ticket.to_dict()

    def wait(
        self,
        ticket: dict | str,
        timeout_s: float | None = None,
    ) -> dict:
        """Block until decided. Returns {approved, decision_payload, reviewer_note, status}."""
        request_id = ticket.get("id") if isinstance(ticket, dict) else ticket
        try:
            return self.client.wait_for_decision(
                request_id,
                timeout_s=timeout_s or self.default_wait_timeout_s,
                poll_interval_s=self.default_poll_interval_s,
            )
        except SphinxTimeout as exc:
            return {"approved": False, "decision_payload": None, "status": "timeout", "error": str(exc)}

    def guard(self, title, action_payload, **kw) -> dict:
        """request + wait in one call (the usual LangGraph node pattern)."""
        return self.wait(self.request(title, action_payload, **kw))

    def report(self, request_id: str, outcome: str, note: str = "") -> dict:
        return self.client.submit_feedback(request_id, outcome, note=note)

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def hitl_interrupt_node(guard: HITLGuard, action_key: str = "proposed_action", result_key: str = "approval"):
    """Returns a LangGraph node function that guards `state[action_key]`.

    If the state has `approved_action` (from a prior decision) it skips re-review
    and applies the human-amended payload.
    """

    def node(state: dict) -> dict:
        proposed = state.get(action_key)
        if proposed is None:
            return {result_key: {"skipped": True, "reason": "no proposed action"}}
        decision = guard.guard(
            proposed.get("title", "Agent action requires approval"),
            proposed.get("payload", proposed),
            description=proposed.get("description", ""),
            risk_level=proposed.get("risk_level", "medium"),
            session_id=state.get("session_id", ""),
        )
        return {result_key: decision}

    return node
