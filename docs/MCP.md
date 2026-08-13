# Sphinx MCP server

Sphinx exposes its full control plane over the Model Context Protocol (MCP) so any MCP-capable agent — LangGraph, OpenAI, Claude Desktop, cursor-style agents, custom runtimes — can request approvals without writing SDK code.

## Running

```bash
# stdio (for MCP hosts that spawn a process)
python -m sphinx.mcp.server

# streamable HTTP (default endpoint: http://localhost:8100/mcp)
python -m sphinx.mcp.server --http --port 8100
```

## Configuration snippet (MCP host)

```jsonc
{
  "mcpServers": {
    "sphinx": { "url": "http://localhost:8100/mcp" }
  }
}
```

## Tools

All tools are prefixed `sphinx_`.

### `sphinx_request_approval`
Submit an approval request. Returns the ticket `id`, `ref` and `status`.

```
agent_id, title, action_payload
description? = "", session_id? = "", framework? = "generic",
risk_level? = "medium", priority? = 1, policy_id? = ""
```

### `sphinx_get_status`
Check status / escalation flag by `id` or `ref`.

### `sphinx_wait_for_decision`
Block until the request is decided (or `timeout_s` elapses). This is the "gate" an agent blocks on.

```
request_id, timeout_s = 300, poll_interval_s = 2.0
```
Returns `{status, approved, decision_payload, reviewer_id, reviewer_note, escalated}` so the agent can proceed with the human-amended payload or abort.

### `sphinx_get_decision`
Read the final decision and payload for an already-decided request.

### `sphinx_submit_feedback`
Report the real-world outcome (`success` | `failure` | `partial`) to close the feedback loop and feed `error_escape_rate`.

### `sphinx_list_policies`
List available SLA/timeout policies.

## Resource

`sphinx://requests/{request_id}` — JSON representation of a request.

## From the Python SDK

```python
from sphinx_sdk import SphinxClient

with SphinxClient(transport="mcp", mcp_url="http://localhost:8100/mcp", agent_id="my-agent") as s:
    ticket = s.request_approval("Deploy to prod", {"env": "prod"}, risk_level="high")
    decision = s.wait_for_decision(ticket.id, timeout_s=600)
    if decision["approved"]:
        deploy(decision["decision_payload"])
```

`McpTransport` bridges the async MCP SDK onto a background event loop, so the public API stays synchronous and drop-in identical to `RestTransport`.

## Mounting into FastAPI

The MCP app can also be mounted inside the Sphinx API process:

```python
from sphinx.mcp.server import mcp

app.mount("/mcp", mcp.streamable_http_app())
```
