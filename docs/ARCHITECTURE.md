# Sphinx Architecture

```
                          ┌────────────────────────────────────────────┐
                          │              Web Console (React/Vite)      │
                          │      Queue · Decisions · Metrics · Policies│
                          └───────────────┬────────────────────────────┘
                                          │ REST + WS  (/api, /api/ws)
                                          ▼
        ┌─────────────────────────────────────────────────────────────────┐
        │                     Control Plane (FastAPI :8001)              │
        │                                                                 │
        │   api/requests ──┐                                              │
        │   api/policies ──┼──► core/services.py ─────► SQLAlchemy ─► SQLite│
        │   api/ws ────────┤        │                    (or Postgres)    │
        │                  │        └──► core/events.py (event bus)      │
        │   core/policy_engine (bg thread) ──► applies SLA timeouts      │
        │   core/metrics ── compute governance KPIs over decision_logs   │
        └─────────────────────────────────────────────────────────────────┘
                          ▲
                 REST      │      MCP (streamable HTTP :8100)
                 ┌─────────┴─────────────┐   ┌───────────────────────────────┐
                 │  Python SDK           │   │   MCP server (sphinx_* tools) │
                 │  SphinxClient         │   │   request_approval            │
                 │   └ RestTransport     │   │   wait_for_decision           │
                 │   └ McpTransport      │   │   get_decision / status       │
                 │  adapters:            │   │   submit_feedback             │
                 │   LangGraph HITLGuard │   │   list_policies               │
                 │   OpenAI ApprovalGate │   └───────────────────────────────┘
                 │   CrewAI callback     │
                 └───────────────────────┘
```

## Components

### 1. Backend (`backend/sphinx`)

| module | responsibility |
|--------|----------------|
| `models.py` | `ApprovalRequest`, `Policy`, `DecisionLog`, `CaptureEvent`, `SigningKey` ORM models + enums |
| `core/services.py` | single source of business logic shared by REST, MCP and the engine: create/resolve/escalate/cancel/feedback/timeout, policy matching, decision-log + delta writing, event publishing |
| `core/policy_engine.py` | background thread that finds overdue pending requests and applies the policy timeout action |
| `core/metrics.py` | computes governance KPIs from requests + decision logs |
| `core/events.py` | async event bus + `publish_sync` bridge so sync threads (REST/MCP/engine) can notify the WS manager |
| `core/delta.py` | recursive `diff_dicts` producing a path-level change list |
| `core/capture_chain.py` | canonical serialization, SHA3-256 content hashing, Ed25519 signing/verification, whole-chain re-verification |
| `core/capture_service.py` | capture ingestion: per-(agent, session) chain linking, sequence assignment, lazy signing-key creation/persistence |
| `api/requests.py` | `/api/requests` CRUD + approve/reject/escalate/cancel/feedback |
| `api/policies.py` | `/api/policies` CRUD, `/api/decisions`, `/api/metrics` |
| `api/capture.py` | `POST /api/capture` (batch ingest), `GET /api/capture` (list/filter), `GET /api/capture/verify` (chain integrity) |
| `api/ws.py` | WebSocket fan-out of `requests` / `decisions` / `policies` / `capture` events |
| `mcp/server.py` | FastMCP server exposing `sphinx_*` tools + a `sphinx://requests/{id}` resource |
| `seed.py` | default policies + 28 realistic demo requests with decision logs + a seeded capture chain |
| `config.py` | `SPHINX_*` env-driven settings |
| `db.py` | SQLAlchemy engine/session, SQLite WAL + FK pragmas |

### 2. Python SDK (`sdk/sphinx_sdk`)

- `client.py` — `SphinxClient` high-level facade over two transports:
  - `RestTransport` (httpx → `/api/*`)
  - `McpTransport` (MCP ClientSession over streamable HTTP, bridged onto a background event loop so the API stays synchronous)
- `capture.py` — `Capture`: decorators (`@cap.tool`, `@cap.llm`, `cap.tools`), `cap.state` context manager, `cap.record`, buffered batching with fail-open transport
- `adapters/langgraph.py` — `HITLGuard` (request/wait/report) + `hitl_interrupt_node` node factory
- `adapters/openai.py` — `ApprovalGate.check(tool_call)` + `openai_tool_callback`
- `adapters/crewai.py` — `sphinx_human_input()` callback factory

### 3. Web console (`web`)

React + Vite + TypeScript SPA. Four pages backed by `src/lib/api.ts`:

- **Queue** — live approval queue with status/risk badges, SLA countdowns, approve/reject/escalate with amend-payload modal.
- **Decisions** — decision log with human↔agent delta view and agreement filter.
- **Metrics** — governance KPI gauges, risk breakdown, status mix, latency.
- **Policies** — SLA policy CRUD.

The dev server proxies `/api` → `:8001` and `/mcp` → `:8100` (`vite.config.ts`); the production nginx image does the same (`docker/nginx.conf`).

## Key flows

### Approval lifecycle

```
agent ──request_approval──► create_request ──policy matching──► PENDING
                                                                  │
   human ──approve/reject──┘      │  agent ──cancel──┘            │ SLA fires
                                  ▼                               ▼
                       decided (approved/rejected)      escalate | auto_approve | auto_reject
                                  │
   agent ──submit_feedback──► outcome (success/failure/partial) ──► error_escape_rate
```

### Event flow

Mutations in `core/services.py` call `publish_sync(topic, payload)`, which schedules `bus.publish` on the FastAPI event loop (captured at startup via `set_event_loop`). Every connected WebSocket client receives `{topic, data}`. The policy engine thread and MCP server use the same sync bridge.

### Metric flow

`/api/metrics` → `compute_metrics` scans requests + `decision_logs`. The decision log is the calibration data for HITL: `correction_rate` and `reviewer_agreement` tell you whether the humans are actually disagreeing with the agent (and whether thresholds should tighten), while `error_escape_rate` measures whether approved actions end up failing in the real world.

### Capture flow

Agent steps are intercepted by the SDK `Capture` layer (tool decorators / LLM
decorators / state context managers), buffered and POSTed to `/api/capture` in
batches. `capture_service` assigns a per-`(agent_id, session_id)` sequence,
computes the SHA3-256 content hash over the canonical event, links it to the
previous event's hash (`prev_hash`) and signs `prev_hash + content_hash` with
the org Ed25519 key (created lazily and persisted in `signing_keys`).
`GET /api/capture/verify` replays the whole chain — recomputing hashes, checking
linkage and signatures — so any tamper (edited payload, reordered/removed event,
forged signature) is detected. Capture is fail-open by design: if the control
plane is unreachable the SDK logs and drops, never blocking the agent.
