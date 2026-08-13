# Sphinx Python SDK

Package: `sphinx-sdk` · source in `sdk/sphinx_sdk` · installed from `sdk/` (this repository).

## Install

```bash
pip install ./sdk            # REST + MCP transports
pip install "./sdk[mcp-transport]"   # same today; MCP is a hard dep
```

## `SphinxClient` — the high-level facade

```python
from sphinx_sdk import SphinxClient

with SphinxClient(
    transport="rest",        # or "mcp"
    base_url="http://localhost:8001",
    mcp_url="http://localhost:8100/mcp",
    agent_id="refund-agent",
    framework="langgraph",
    session_id="sess-1",
) as sphinx:
    ticket = sphinx.request_approval(
        "Approve refund of $980",
        {"action": "refund", "amount_usd": 980.0},
        description="duplicate charge",
        risk_level="medium",
        metadata={"env": "prod"},
    )
    # ticket.id / ticket.ref / ticket.status

    decision = sphinx.wait_for_decision(ticket.id, timeout_s=600, poll_interval_s=1.0)
    if decision["approved"]:
        execute(decision["decision_payload"])   # possibly human-amended
    else:
        abort(decision.get("reviewer_note"))

    sphinx.submit_feedback(ticket.id, outcome="success", note="done")
```

API: `request_approval`, `check_status`, `get_decision`, `wait_for_decision`, `submit_feedback`, `list_policies`, `close`.

Errors: `SphinxError` for HTTP/transport errors, `SphinxTimeout` when `wait_for_decision` times out.

## Framework adapters

All adapters accept the same keyword options (`base_url`, `transport`, `mcp_url`, …).

### LangGraph

```python
from sphinx_sdk.adapters.langgraph import HITLGuard, hitl_interrupt_node

guard = HITLGuard("refund-agent", base_url="http://localhost:8001")

# blocking guard in a risky node
def risky_node(state):
    decision = guard.guard(
        state["proposed_action"]["title"],
        state["proposed_action"]["payload"],
        risk_level="medium",
    )
    if not decision["approved"]:
        return {"blocked": True, "reason": decision.get("reviewer_note")}
    return {"executed_payload": decision["decision_payload"]}

# or use the node factory
node = hitl_interrupt_node(guard, action_key="proposed_action", result_key="approval")
```

### OpenAI tool-calling

```python
from sphinx_sdk.adapters.openai import ApprovalGate, openai_tool_callback

gate = ApprovalGate("support-agent")

def on_tool_call(tool_call):          # {"name": ..., "arguments": {...}} or JSON string
    decision = gate.check(tool_call, risk_level="medium")
    if not decision["approved"]:
        return {"error": decision.get("reviewer_note", "blocked by human")}
    return run_tool(decision["decision_payload"])

# wiring into a Responses API event stream
cb = openai_tool_callback(gate, risk_level="medium")
# for event in stream:
#     if event.type == "response.function_call_arguments.done":
#         decision = cb(event)
```

`check(tool_call, wait=False)` returns `{"request_id", "status": "pending"}` for async flows.

### CrewAI

```python
from sphinx_sdk.adapters.crewai import sphinx_human_input

crew = Crew(
    tasks=[...],
    process=Process.sequential,
    manager_agent=...,
    human_input=True,
    callbacks=[sphinx_human_input("finance-analyst", base_url="http://localhost:8001")],
)
```

Every `human_input` step becomes a Sphinx approval ticket; the returned value is the human-amended payload (or `{"_blocked": true, "reason": ...}` when rejected).

## Demo agent

`sdk/examples/demo_agent.py` runs the full lifecycle (propose → approve → read payload → feedback) for three scenarios over REST or MCP:

```bash
python sdk/examples/demo_agent.py --transport mcp
python sdk/examples/demo_agent.py --transport rest --no-auto-review
```
