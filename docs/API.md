# Sphinx REST API

Base URL: `http://localhost:8001` · JSON in/out · OpenAPI at `/docs`.

## Health

`GET /api/health` → `{"service":"sphinx","status":"ok"}`

## Approval requests

| method | path | description |
|--------|------|-------------|
| `GET` | `/api/requests` | list (filters below) |
| `POST` | `/api/requests` | create an approval request |
| `GET` | `/api/requests/{id\|ref}` | fetch one (id or `SPH-…` ref) |
| `POST` | `/api/requests/{id}/approve` | approve (optionally amend payload) |
| `POST` | `/api/requests/{id}/reject` | reject |
| `POST` | `/api/requests/{id}/escalate` | escalate |
| `POST` | `/api/requests/{id}/cancel` | cancel |
| `POST` | `/api/requests/{id}/feedback` | report real-world outcome |

### `POST /api/requests`

```json
{
  "agent_id": "refund-agent",
  "title": "Approve refund of $980 for order ORD-77241",
  "action_payload": {"action": "refund", "order_id": "ORD-77241", "amount_usd": 980.0},
  "description": "Customer reported duplicate charge",
  "session_id": "sess-1",
  "framework": "langgraph",
  "risk_level": "medium",
  "priority": 1,
  "policy_id": null,
  "requester": "agent",
  "metadata": {"origin": "production"}
}
```

A low-risk request under an `auto_approve_below_risk` policy is returned immediately as `auto_approved`.

### `POST /api/requests/{id}/approve`

```json
{ "reviewer_id": "alice@landslide.io", "note": "lowered the amount",
  "decision_payload": {"action": "refund", "amount_usd": 800.0}, "amend": true }
```

- omit `decision_payload` to confirm the agent's payload unchanged (records `agreement=true`)
- `amend: true` + `decision_payload` records the human↔agent delta

### List filters

`status`, `framework`, `agent_id`, `escalated`, `q` (search title/ref/agent), `limit` (≤500), `offset`.

## Policies

| method | path | description |
|--------|------|-------------|
| `GET` | `/api/policies` | list policies |
| `POST` | `/api/policies` | create (409 if name exists) |
| `PUT` | `/api/policies/{id}` | update (PATCH semantics via `exclude_unset`) |

```json
{ "name": "high-risk-gate", "description": "…", "risk_levels": ["high","critical"],
  "timeout_seconds": 900, "on_timeout": "auto_reject",
  "auto_approve_below_risk": false, "min_reviewers": 1, "enabled": true }
```

`on_timeout` ∈ `auto_approve` | `auto_reject` | `escalate`.

## Decision log

`GET /api/decisions?source=&agreement=&limit=&offset=` returns `decision_logs` with `agent_decision`, `human_decision`, `delta`, `agreement`, `source`, `reviewer_id`, `note`.

`source` ∈ `human_review` | `policy_timeout` | `auto_policy` | `agent_feedback`.

## Metrics

`GET /api/metrics?since_days=` returns the governance KPIs:

```json
{
  "window": {"since_days": null, "generated_at": "…"},
  "totals": {"requests": 28, "by_status": {"pending": 5, "approved": 11, "…": 0}, "escalated": 4, "pending": 5},
  "governance": {
    "escalation_rate": 14.3, "timeout_rate": 13.6, "correction_rate": 25.0,
    "reviewer_agreement": 75.0, "error_escape_rate": 23.1, "sla_compliance_rate": 86.4
  },
  "latency": {"human_reviews": 12, "avg_seconds": 321.4, "p50_seconds": 210.0, "p95_seconds": 900.0},
  "risk": {"low": {"created": 0, "escalated": 0}, "…": "…"},
  "feedback": {"approved_with_feedback": 13, "negative_outcomes": 3}
}
```

## WebSocket live events

`GET /api/ws` (upgrade) pushes `{"topic": "...", "data": {...}}`:

| topic | events | payload |
|-------|--------|---------|
| `requests` | `created`, `decided`, `escalated`, `cancelled`, `feedback` | full request dict |
| `policies` | `created`, `updated` | policy dict |
| `capture` | `ingested` | `{event_id, agent_id, event_type}` |

## Decision capture

Every agent step — tool call, LLM inference, state change — can be streamed into a
**tamper-evident capture trail**: events are chained per `(agent_id, session_id)`
with a SHA3-256 content hash, linked via `prev_hash`, and signed with the org's
Ed25519 key. The chain can be independently re-verified at any time.

### `POST /api/capture` — ingest events

```json
{
  "agent_id": "refund-agent",
  "session_id": "sess-1",
  "events": [
    {
      "event_type": "tool_call",
      "event_name": "lookup_order",
      "input_payload": {"order_id": "ORD-1"},
      "output_payload": {"order": {"id": "ORD-1"}},
      "metadata": {"duration_ms": 41},
      "status": "ok"
    }
  ]
}
```

`event_type` ∈ `tool_call` | `llm_inference` | `state_change`; `status` ∈ `ok` | `error`.
Returns `{received, agent_id, session_id, first, last}` where `first`/`last` include
the server-assigned `sequence`, `content_hash`, `prev_hash` and `signature`.

### `GET /api/capture?agent_id=&session_id=&event_type=&limit=&offset=`

Lists capture events (newest first). Each item is a full event dict with chain fields.

### `GET /api/capture/verify?agent_id=&session_id=`

Recomputes every content hash, checks `prev_hash` linkage and Ed25519 signatures.
Returns `{valid, checked, chains, errors}` — any tamper (edited payload, broken
link, forged signature) makes `valid: false` with per-event error strings.

## Error conventions

- `422` — validation error (missing/ invalid body fields)
- `400` — invalid query value (e.g. bad status filter)
- `404` — unknown request/policy
- `409` — state conflict (acting on a non-pending request, duplicate policy name, feedback before decision)
