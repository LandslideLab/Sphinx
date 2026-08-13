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

## Error conventions

- `422` — validation error (missing/ invalid body fields)
- `400` — invalid query value (e.g. bad status filter)
- `404` — unknown request/policy
- `409` — state conflict (acting on a non-pending request, duplicate policy name, feedback before decision)
