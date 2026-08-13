# Sphinx — User Guide

The complete operating manual for the **Sphinx Agent HITL Control Plane**: installation, running, using the web console, connecting agents, configuration, production deployment and troubleshooting.

---

## Table of contents

1. [Introduction](#1-introduction)
2. [System requirements](#2-system-requirements)
3. [Installation](#3-installation)
4. [Running the system](#4-running-the-system)
5. [Using the web console](#5-using-the-web-console)
6. [Connecting agents](#6-connecting-agents)
7. [REST API quick reference](#7-rest-api-quick-reference)
8. [Configuration reference](#8-configuration-reference)
9. [Production deployment](#9-production-deployment)
10. [Troubleshooting & FAQ](#10-troubleshooting--faq)
11. [Glossary](#11-glossary)

---

## 1. Introduction

Sphinx is a framework-agnostic, self-hosted **human-in-the-loop (HITL) approval control plane** for agent workflows. It sits between agent frameworks (LangGraph, OpenAI SDK, CrewAI, or any MCP-capable runtime) and the humans who must supervise them.

It solves the problems that agent frameworks leave open:

| Problem | Sphinx solution |
|---------|-----------------|
| Every framework ships its own approval UI | One unified web console + one approval queue for all frameworks |
| "Human-in-the-loop" decays into blind clicking | SLA policies auto-degrade tickets (escalate / auto-approve / auto-reject) when nobody reviews them in time |
| No feedback data to calibrate thresholds | Decision log records the delta between what the agent proposed and what a human decided, and derives governance metrics |
| HITL is a raw `interrupt()` / `needs_approval` callback | A complete control plane: queue, SLA, audit trail, metrics, MCP tooling |

The four components of the system:

- **Control plane** — FastAPI service exposing the REST API, WebSocket live events, the SLA timeout engine, and governance metrics.
- **MCP server** — exposes the control plane as MCP tools (`sphinx_request_approval`, `sphinx_wait_for_decision`, …) over stdio or streamable HTTP.
- **Python SDK** — `SphinxClient` over REST or MCP transports, plus drop-in adapters for LangGraph, OpenAI tool-calling and CrewAI.
- **Web console** — React/TypeScript SPA with four pages: **Approval Queue**, **Decision Log**, **Governance Metrics**, **SLA Policies**.

---

## 2. System requirements

| component | requirement |
|-----------|-------------|
| Python | 3.11+ |
| Node.js (web console / SDK examples) | 18+ (tested with 22) |
| OS | Linux / macOS / Windows (WSL recommended for Docker) |
| Database | SQLite (default, zero-config) or PostgreSQL (production) |
| Docker | optional, for the one-command compose stack |
| Network | only the ports you expose (default 8001 API, 8100 MCP, 5173 dev / 8080 compose web) |

---

## 3. Installation

### 3.1 From source

```bash
# 1. clone / copy the repository
cd sphinx

# 2. create a virtual environment and install everything
python3 -m venv .venv
.venv/bin/pip install -e "backend[dev]" -e sdk

# 3. install the web console dependencies
cd web && npm install && cd ..
```

> The `backend[dev]` extra installs pytest for running the test suite; it is not needed for production.

### 3.2 With Docker Compose

```bash
docker compose up --build
```

This builds three images (API, MCP, web+nginx) and starts the full stack. See [section 4.2](#42-docker-compose-stack).

### 3.3 Sanity check

```bash
.venv/bin/python -c "from sphinx_sdk import SphinxClient; print('SDK OK')"
```

---

## 4. Running the system

### 4.1 Local development

Terminal 1 — the control plane (REST + WebSocket, port 8001). Seed demo data so every console page has content:

```bash
SPHINX_SEED_DEMO_DATA=1 .venv/bin/python -m uvicorn sphinx.main:app --host 0.0.0.0 --port 8001
```

Terminal 2 — the MCP server (streamable HTTP, port 8100):

```bash
.venv/bin/python -m sphinx.mcp.server --http --port 8100
```

Terminal 3 — the web console dev server (port 5173, proxies `/api` → :8001 and `/mcp` → :8100):

```bash
cd web && npm run dev
```

Open http://localhost:5173.

> Tip: the included `Makefile` wraps all of these — `make api`, `make mcp`, `make web`, `make demo`, `make test`.

### 4.2 Docker Compose stack

```bash
docker compose up --build
```

| Service | Address | Purpose |
|---------|---------|---------|
| `web` | http://localhost:8080 | nginx serving the console; reverse-proxies `/api`, `/api/ws` and `/mcp` |
| `api` | http://localhost:8001 | REST API + WebSocket |
| `mcp` | http://localhost:8100 | MCP streamable HTTP endpoint |
| data | `sphinx-data` volume | shared SQLite database |

The stack boots with the 4 default policies and 28 rows of demo data. To start with a clean database, remove the `sphinx-data` volume (`docker compose down -v`) and bring the stack up again.

### 4.3 Health checks

```bash
curl http://localhost:8001/api/health
# {"service":"sphinx","status":"ok"}

curl -s http://localhost:8001/api/metrics | python3 -m json.tool   # full KPI snapshot
```

### 4.4 Running the demo agent

The demo simulates a refund-ops agent: propose three actions → a simulated human (or the SLA policy) decides → read the payload → report the outcome.

```bash
# agent over MCP transport (default) — needs API + MCP running
.venv/bin/python sdk/examples/demo_agent.py --transport mcp

# agent over REST transport
.venv/bin/python sdk/examples/demo_agent.py --transport rest

# rely on the SLA policy instead of a simulated human
.venv/bin/python sdk/examples/demo_agent.py --no-auto-review
```

Expected output (MCP):

```
[step 1] proposing: Approve refund of $980 for order ORD-77241
  -> ticket SPH-DA1C9F status=pending
  -> decision status=approved approved=True
     payload={'action': 'refund', 'order_id': 'ORD-77241', 'amount_usd': 980.0, ...}
     reviewer_note=Reviewed by demo human (simulated).
  -> feedback outcome=success
...
[step 3] proposing: Auto-fill support ticket from chat transcript
  -> ticket SPH-A56EFF status=auto_approved      # low risk, instant auto-approve
  -> decision status=auto_approved approved=True
```

---

## 5. Using the web console

The console has four pages, reachable from the left sidebar. The queue badge shows the live pending count.

### 5.1 Approval Queue (`/`)

The operational surface reviewers work from every day.

- **Filtering** — the filter bar offers *status*, *framework* and free-text search (matches title / ref / agent id).
- **Reading a ticket** — each card shows status and risk badges, the reference (`SPH-XXXXXX`), title, description, the full JSON action payload, the matched policy, and a **live SLA countdown** for pending tickets (amber under 90 s, red under 30 s).
- **Deciding a ticket** — use **Approve** / **Reject** / **Escalate**:
  - *Approve* opens a modal. Tick **"Amend decision payload"** to edit the payload a human actually wants executed — this records the human↔agent delta in the decision log (the calibration data for HITL thresholds). Unticked, it records `agreement: true`.
  - *Reject* records the denial with an optional reviewer note.
  - *Escalate* flags the ticket for senior review without resolving it; it stays in the queue with an **▲ escalated** badge.
  - Every action writes to the audit trail and is announced over the WebSocket, so all connected consoles update live.
- **SLA behavior** — tickets nobody decides before their deadline are degraded by their policy (`escalate` by default, or `auto_approve` / `auto_reject`), then leave or stay in the queue accordingly.

### 5.2 Decision Log (`/decisions`)

The audit trail and feedback data.

- Each row shows the request ref, source (`human_review` / `policy_timeout` / `auto_policy` / `agent_feedback`), the **delta** between the agent decision and the human decision, the agreement verdict, the reviewer, and the note.
- **Delta view** renders path-level changes: `+ path = value` (added), `− path (was …)` (removed), `~ path: from → to` (replaced). `✓ no delta — human confirmed agent decision` means the human approved unchanged.
- **Agreement filter** — *Agreed (no delta)* vs *Disagreed (delta)*.

### 5.3 Governance Metrics (`/metrics`)

Control-plane KPIs recomputed on every poll (8 s), optionally for *last 7 / 30 days*:

| KPI | Meaning | Good when |
|-----|---------|-----------|
| Escalation rate | escalated requests / created | low |
| Timeout rate | SLA auto-decisions / decided | low |
| Human correction rate | reviews where the human changed the payload | high |
| Reviewer agreement | reviews confirming the agent unchanged | high |
| Error escape rate | approved actions with a negative outcome / approved with feedback | low |
| SLA compliance | decisions reached before the deadline / decided | high |

Plus review latency (avg / p50 / p95), the risk breakdown (escalated vs created per risk level) and the status mix. Use these to decide, e.g., whether the auto-approve threshold for low-risk actions should be raised (high agreement + low error escape) or tightened.

### 5.4 SLA Policies (`/policies`)

Manage the auto-degradation rules that prevent approval fatigue.

- **Create** — *+ New policy*, then set:
  - *Name* (unique) and description
  - *Applies to risk levels* (`low` / `medium` / `high` / `critical`)
  - *SLA timeout* in seconds
  - *On timeout*: `auto_approve` / `auto_reject` / `escalate`
  - *Auto-approve below-risk instantly*: when enabled, low-risk actions matching this policy are approved immediately without a human
  - *Min reviewers*
- **Edit / toggle** — update fields or enable/disable a policy. Disabled policies are not matched to new requests and their pending tickets degrade to `escalate`.
- Policies are applied to requests at creation time (snapshot of `timeout_seconds` and `policy_name`), so editing a policy does not retroactively change open tickets.

---

## 6. Connecting agents

### 6.1 Via MCP (any framework)

Add to your MCP-capable host's config:

```jsonc
{
  "mcpServers": {
    "sphinx": { "url": "http://localhost:8100/mcp" }
  }
}
```

Tools exposed (see `docs/MCP.md`): `sphinx_request_approval`, `sphinx_get_status`, `sphinx_wait_for_decision`, `sphinx_get_decision`, `sphinx_submit_feedback`, `sphinx_list_policies`.

Minimal agent flow:

```
sphinx_request_approval(agent_id, title, action_payload, risk_level) -> {id, ref}
sphinx_wait_for_decision(request_id, timeout_s) -> {status, approved, decision_payload, reviewer_note}
   if approved: execute(decision_payload)      # possibly human-amended
sphinx_submit_feedback(request_id, "success")   # close the loop
```

### 6.2 Via the Python SDK

```python
from sphinx_sdk import SphinxClient

with SphinxClient(
    transport="mcp",                # or "rest"
    base_url="http://localhost:8001",
    mcp_url="http://localhost:8100/mcp",
    agent_id="refund-agent",
    framework="langgraph",
) as sphinx:
    ticket = sphinx.request_approval(
        "Approve refund of $980 for order ORD-77241",
        {"action": "refund", "amount_usd": 980.0},
        risk_level="medium",
    )
    decision = sphinx.wait_for_decision(ticket.id, timeout_s=600)
    if decision["approved"]:
        run_refund(decision["decision_payload"])
    sphinx.submit_feedback(ticket.id, outcome="success", note="done")
```

### 6.3 Framework adapters

- **LangGraph** — `HITLGuard.guard(title, payload)` blocks a node until a human (or policy) decides; `hitl_interrupt_node(guard)` returns a ready-made node function.
- **OpenAI** — `ApprovalGate.check(tool_call)` validates a tool call before execution; supports dict or JSON-string tool calls and a `wait=False` async mode.
- **CrewAI** — `sphinx_human_input(agent_id)` builds the `human_input` callback; each stop becomes an approval ticket.

Worked examples in `docs/SDK.md`.

---

## 7. REST API quick reference

Full details and JSON examples in `docs/API.md`. Interactive docs: http://localhost:8001/docs.

| method | path | purpose |
|--------|------|---------|
| `GET` | `/api/health` | liveness probe |
| `POST` | `/api/requests` | create an approval request |
| `GET` | `/api/requests` | list (filters: `status`, `framework`, `agent_id`, `escalated`, `q`, `limit`, `offset`) |
| `GET` | `/api/requests/{id\|ref}` | fetch one |
| `POST` | `/api/requests/{id}/approve` | approve (optional amended payload) |
| `POST` | `/api/requests/{id}/reject` | reject |
| `POST` | `/api/requests/{id}/escalate` | escalate |
| `POST` | `/api/requests/{id}/cancel` | cancel (agent aborts) |
| `POST` | `/api/requests/{id}/feedback` | report outcome: `success` / `failure` / `partial` |
| `GET` | `/api/policies` | list policies |
| `POST` | `/api/policies` | create policy |
| `PUT` | `/api/policies/{id}` | update policy (partial) |
| `GET` | `/api/decisions` | list decision log (`source`, `agreement`, `limit`, `offset`) |
| `GET` | `/api/metrics` | governance KPIs (`since_days`) |
| `GET` | `/api/ws` | WebSocket live event stream |

Error conventions: `422` validation, `400` bad query value, `404` unknown id, `409` state conflict (acting on a non-pending request, duplicate policy name, feedback before a decision).

---

## 8. Configuration reference

All settings come from `SPHINX_*` environment variables (defaults in `backend/sphinx/config.py`).

| variable | default | description |
|----------|---------|-------------|
| `SPHINX_DATABASE_URL` | `sqlite:///./sphinx.db` | SQLAlchemy database URL (SQLite or Postgres) |
| `SPHINX_API_PORT` | `8001` | REST + WebSocket port |
| `SPHINX_MCP_PORT` | `8100` | MCP streamable HTTP port |
| `SPHINX_SCHEDULER_INTERVAL_SECONDS` | `1.0` | SLA engine scan interval |
| `SPHINX_DEFAULT_POLICY_SEED` | `true` | create the 4 default policies at startup |
| `SPHINX_SEED_DEMO_DATA` | `false` | seed 28 demo requests at startup |
| `SPHINX_CORS_ORIGINS` | `["*"]` | CORS allow-list (JSON array) |
| `SPHINX_LOG_LEVEL` | `info` | log level |

Example:

```bash
SPHINX_DATABASE_URL=postgresql+psycopg://sphinx:sphinx@localhost:5432/sphinx \
SPHINX_SEED_DEMO_DATA=false \
SPHINX_CORS_ORIGINS='["https://console.example.com"]' \
.venv/bin/sphinx-api
```

> The `sphinx-api` console script is equivalent to `python -m uvicorn sphinx.main:app`.

---

## 9. Production deployment

1. **Database** — switch from SQLite to PostgreSQL (single-node SQLite is fine for small self-hosted deployments; Postgres gives you concurrent writers and horizontal scaling). The SQLAlchemy URL swap is the only change; run a migration tool of your choice against the three tables (`approval_requests`, `policies`, `decision_logs`).
2. **Static web build** — serve the built SPA (`cd web && npm run build` → `dist/`) behind nginx using `docker/nginx.conf` as a template (SPA fallback + `/api`, `/api/ws`, `/mcp` reverse proxies).
3. **TLS** — terminate TLS at your reverse proxy/load balancer; the WebSocket and MCP streams both work behind it (see `X-Forwarded-Proto` headers in `docker/nginx.conf`).
4. **Authentication** — Sphinx v0.1 has no built-in auth; protect the API and console with an SSO/IDP reverse proxy (e.g. OIDC-aware gateway) before exposing outside your network.
5. **Scalability** — the REST/API layer is stateless (scale horizontally); the SLA engine currently runs as one in-process scheduler inside each API worker, so for multi-worker deployments keep the API worker count at one per replica set or move the scheduler to a dedicated process/queue.

---

## 10. Troubleshooting & FAQ

### The console shows "No approval requests match the current filters."
The queue is filtered to *Pending* by default. Clear the status filter to see decided tickets, or submit a new request (`curl` / demo agent / SDK).

### A pending ticket never gets decided.
Check the ticket's SLA countdown. If it has no `timeout_seconds`/policy, nobody will auto-decide it — set a policy (create one in the console) or decide it manually.

### The WebSocket isn't updating live.
Confirm the console is reached through the proxy that forwards `/api/ws` (vite dev server and the docker nginx both do). The console also polls every 3–8 s as a fallback, so it still works without WS.

### I edited a policy but an open ticket still shows the old SLA.
Policies are snapshotted onto a request at creation time. Edit/disable the policy for *future* requests only.

### The MCP server won't start.
Make sure the control plane's database is reachable and initialized: `SPHINX_DATABASE_URL` must point at the same database the API uses (both processes share it in the compose stack via the volume).

### `docker compose up` fails on the first run.
`Dockerfile.web` runs `npm ci`; if `package-lock.json` is out of sync with `package.json`, run `npm install` in `web/`, commit the lockfile, and rebuild.

### How do I reset the demo database?
Remove the compose volume (`docker compose down -v`) or, locally, start against a fresh `SPHINX_DATABASE_URL` path. SQLite files (`*.db`) are git-ignored.

### Where do the governance numbers come from?
`compute_metrics` scans `approval_requests` + `decision_logs` (`backend/sphinx/core/metrics.py`). Definitions are in `docs/API.md` and on the Metrics page itself.

---

## 11. Glossary

| term | meaning |
|------|---------|
| HITL | Human-in-the-loop — a human reviews/supervises agent actions |
| Approval request | a ticket asking a human to approve/reject one agent action |
| SLA | the timeout budget before a pending request is auto-degraded |
| Auto-degradation | the policy action on SLA timeout: `escalate` / `auto_approve` / `auto_reject` |
| Delta | path-level difference between the agent's proposed payload and the human's final payload |
| Agreement | `true` when the human approved the agent's payload unchanged |
| Error escape rate | share of approved actions that were later reported `failure`/`partial` |
| MCP | Model Context Protocol — the tool protocol Sphinx exposes |
| Control plane | the API + engine + metrics layer (vs. the data plane that executes actions) |
