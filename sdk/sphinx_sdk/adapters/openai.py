"""OpenAI SDK adapter: gate tool calls through Sphinx before execution.

Pattern (Responses API / needs_approval style):
    from sphinx.adapters.openai import ApprovalGate

    gate = ApprovalGate("support-agent")

    def execute_refund(tool_call):            # a tool the model wants to run
        decision = gate.check(tool_call)      # payload = the tool call args
        if not decision["approved"]:
            return {"error": decision.get("reviewer_note", "blocked by human")}
        return run_refund(decision["decision_payload"])
"""
from __future__ import annotations

from typing import Any

from sphinx_sdk.adapters.langgraph import HITLGuard


class ApprovalGate(HITLGuard):
    """HITL guard shaped for OpenAI tool-calling flows."""

    def check(
        self,
        tool_call: dict[str, Any] | str,
        *,
        title: str | None = None,
        risk_level: str = "medium",
        session_id: str = "",
        wait: bool = True,
        wait_timeout_s: float = 600,
    ) -> dict:
        """Validate a tool call against a human reviewer.

        tool_call: {"name": "...", "arguments": {...}} or a JSON string.
        """
        if isinstance(tool_call, str):
            import json

            tool_call = json.loads(tool_call)
        name = tool_call.get("name", tool_call.get("type", "tool"))
        args = tool_call.get("arguments", tool_call)
        ticket = self.request(
            title=title or f"OpenAI tool call: {name}",
            action_payload={"tool": name, "arguments": args},
            risk_level=risk_level,
            framework="openai",
            session_id=session_id,
        )
        if not wait:
            return {"request_id": ticket["id"], "status": "pending"}
        return self.wait(ticket, timeout_s=wait_timeout_s)


def openai_tool_callback(gate: ApprovalGate, risk_level: str = "medium"):
    """Returns a callable for OpenAI's tool-call event stream:

        stream = client.responses.create(...)
        for event in stream:
            if event.type == "response.function_call_arguments.done":
                decision = callback(event)
    """

    def callback(event: Any) -> dict:
        return gate.check(
            {"name": getattr(event, "name", "tool"), "arguments": getattr(event, "arguments", {})},
            risk_level=risk_level,
        )

    return callback
