# Sphinx — Full Test Report

**Project:** Sphinx · Agent HITL Control Plane (LANDSLIDE)
**Date:** 2026-08-13
**Commit:** `414c71e` (baseline) + fixes applied on top
**Result:** ✅ **107 / 107 automated tests passed** + live end-to-end verification passed

---

## 1. Executive summary

Sphinx was verified against every capability in its spec: the REST control plane, WebSocket live events, the SLA timeout engine, governance metrics, the MCP server, the Python SDK with all three framework adapters (LangGraph / OpenAI / CrewAI), the demo agent, seed data, and the web console build.

- **107 automated tests** — 0 failures, 0 errors, 0 skips.
- **Live end-to-end flows** exercised against real running servers (REST :8001, MCP :8100, Web console dev server :5173 with `/api` and `/mcp` proxy).
- **Web console** compiles clean (`tsc -b && vite build`) and is deployed to a live preview.
- **Bugs found and fixed during verification:** the WebSocket event bus was never published to (REST/MCP/engine mutations were silent), the `deadline` property returned the wrong value, several REST endpoints accepted an optional `None` body, the CrewAI adapter passed an unsupported `framework` kwarg, and policy `on_timeout` was stored as a raw string instead of the enum. All are fixed and covered by regression tests.

---

## 2. Test environment

| item | value |
|------|-------|
| OS | Linux, Python 3.11.2, Node 22.22.0 |
| Backend | FastAPI + SQLAlchemy 2 + SQLite (WAL), MCP Python SDK |
| SDK | `sphinx-sdk` 0.1.0 (REST + MCP transports) |
| Web | React 18 + Vite 5 + TypeScript 5 |
| Test runner | pytest 8 + pytest-asyncio, `backend/tests/` |
| Isolation | per-test in-memory/temp SQLite DB; live integration stack on a dedicated temp DB |

---

## 3. Automated test inventory

| file | tests | coverage |
|------|------:|----------|
| `test_services.py` | 26 | service layer: policy matching, request creation (pending / auto-approve), approve/reject (agreement + delta), escalate, cancel, feedback, SLA timeout actions (auto_approve / auto_reject / escalate / idempotency), overdue detection, seed idempotency |
| `test_api.py` | 31 | full REST surface: health, requests CRUD + approve/reject/escalate/cancel/feedback, filters/search/pagination, 400/404/409/422 errors, policies CRUD + conflict + validation, decisions list + agreement filter, metrics shape + window |
| `test_metrics.py` | 8 | metric math: zero-state, escalation rate + risk breakdown, timeout rate, correction & agreement rates, error escape rate, SLA compliance, since-days window, status mix completeness |
| `test_policy_engine.py` | 3 | background scheduler: idempotent start/stop, live auto-approve firing, live escalate firing |
| `test_delta.py` | 5 | `diff_dicts`: add/replace/remove, nested paths, equality, empty base, `summarize_delta` |
| `test_ws.py` | 6 | WebSocket live events: create→`created`, approve→`decided`, reject/escalate/cancel/feedback topics, policy events, multi-client fan-out, disconnect resilience |
| `test_mcp.py` | 7 | MCP server over real streamable HTTP: list policies, request + status, decision after approve, wait-for-decision, feedback, `sphinx://requests/{id}` resource, full lifecycle via `SphinxClient` |
| `test_sdk.py` | 13 | RestTransport round-trip + timeout, `SphinxClient` flow, LangGraph `HITLGuard` + `hitl_interrupt_node`, OpenAI `ApprovalGate` (dict + JSON string + non-blocking + event callback), CrewAI callback (approved + blocked) |
| `test_demo_agent.py` | 3 | demo agent end-to-end over REST and MCP transports; tickets visible via API with closed feedback loop |
| `test_seed.py` | 5 | default policies, 28 demo rows, idempotency, plausible metrics, agent/framework diversity |
| **Total** | **107** | |

### Full run output

```
........................................................................ [ 67%]
...................................                                      [100%]
107 passed in 58.48s
```

---

## 4. Feature verification matrix (automated)

| # | feature | evidence |
|---|---------|----------|
| 1 | REST health + lifecycle (create/get/approve/reject/escalate/cancel/feedback) | `test_api.py` 31 tests |
| 2 | Policy matching by risk level, explicit policy id, disabled policy exclusion | `test_services.py` |
| 3 | Low-risk instant auto-approval | `test_services`, `test_api::test_low_risk_auto_approves` |
| 4 | SLA timeout engine (escalate / auto-approve / auto-reject, fires once) | `test_services`, `test_policy_engine` |
| 5 | Human↔agent delta recording + agreement flag on amend | `test_services`, `test_api::test_approve_amended_payload_records_delta` |
| 6 | Governance metrics (escalation/timeout/correction/agreement/error-escape/SLA-compliance/latency) | `test_metrics.py` 8 tests |
| 7 | WebSocket live event bus (requests + policies topics) | `test_ws.py` 6 tests |
| 8 | MCP tools + resource over streamable HTTP | `test_mcp.py` 7 tests |
| 9 | SDK transports (REST + MCP) and error semantics | `test_sdk.py` |
| 10 | LangGraph / OpenAI / CrewAI adapters | `test_sdk.py` |
| 11 | Demo agent full lifecycle (REST + MCP) | `test_demo_agent.py` |
| 12 | Seed data realism + idempotency | `test_seed.py` |

---

## 5. Live end-to-end verification

Performed against running servers seeded with demo data.

### 5.1 Stack health

| check | result |
|-------|--------|
| `GET /api/health` | `{"service":"sphinx","status":"ok"}` ✅ |
| `POST /mcp` initialize | MCP capabilities + instructions returned ✅ |
| Web dev server `:5173` + `/api` proxy + `/mcp` proxy | HTTP 200 for all ✅ |
| Seeded metrics | 28 requests, 9 pending, realistic KPI values ✅ |

### 5.2 Demo agent — full HITL lifecycle

Ran `sdk/examples/demo_agent.py` over **MCP** and **REST** transports. In both runs:

- **step 1** medium-risk refund → `pending` → human approved (`reviewer_note="Reviewed by demo human (simulated)."`) → agent read payload → `feedback outcome=success`
- **step 2** high-risk flag → `pending` → human approved → feedback ✅
- **step 3** low-risk ticket → `auto_approved` instantly by policy (no human involved) ✅

### 5.3 SLA auto-degradation (live)

Created policy `e2e-auto-reject` (critical, `timeout_seconds=3`, `on_timeout=auto_reject`) and submitted a critical request. After ~6 s:

```
"status": "auto_rejected",
"decision_payload": null,
"resolved_by": "policy"
```
✅ The background engine degraded the request deterministically within the SLA.

### 5.4 WebSocket live events (live)

A real WS client received, in order: `hello`, then `requests created pending` on ticket creation, then `requests decided approved` on human approval. ✅

### 5.5 Web console preview

Built with `tsc -b && vite build` (0 errors) and served at:
`https://5173-d49acfcddf7cbb19.monkeycode-ai.live`

Page, `/api/health` and `/api/requests` all return 200 through the preview proxy; fresh pending tickets are visible in the queue. ✅

---

## 6. Bugs found & fixed (now regression-tested)

| bug | fix | regression test |
|-----|-----|-----------------|
| WebSocket event bus never published (dead channel) | `publish_sync()` bridge + publish from services, policies API and policy engine | `test_ws.py` (6) |
| `ApprovalRequest.deadline` returned `created_at` instead of `created_at + timeout` | corrected with timezone-safe arithmetic | `test_services` (via `seconds_pending`/overdue) |
| REST `POST` bodies defaulted to `None` (crashed instead of 422) | required `Body(...)` | `test_api::test_create_missing_body_422` |
| CrewAI adapter passed unsupported `framework` kwarg to `HITLGuard` | pop before construction, forward to request call | `test_sdk` crewai tests |
| Policy `on_timeout` stored as string, crashing `to_dict` | coerce to `TimeoutAction` enum on create/update | `test_api` policy tests |
| Test isolation: API-test data leaked into unit tests | `db` fixture wipes tables at setup | full suite green |

---

## 7. Known limitations / notes

- **SQLite concurrency:** the compose stack shares one SQLite file (WAL) between API and MCP processes — correct for single-node/self-hosted use; for multi-node production switch `SPHINX_DATABASE_URL` to Postgres (SQLAlchemy URL swap only).
- **Docker images were not built** in this environment (no Docker daemon); `docker-compose.yml`, `docker/Dockerfile.api`, `docker/Dockerfile.web` and `docker/nginx.conf` are standard and follow the verified local topology (API :8001, MCP :8100, web proxy :8080).
- The SLA engine is a single-threaded in-process scheduler; horizontal scaling would move it to a distributed job (e.g., `apscheduler` + Postgres) — out of scope for v0.1.
- AuthN/Z for the console and API is deliberately out of scope for v0.1 (internal control plane).

---

## 8. How to reproduce

```bash
# 1. install
python3 -m venv .venv
.venv/bin/pip install -e "backend[dev]" -e sdk

# 2. run the full suite
cd backend && ../.venv/bin/python -m pytest -q        # → 107 passed

# 3. run the demo agent against a live stack
SPHINX_SEED_DEMO_DATA=1 ../.venv/bin/sphinx-api &     # API :8001
../.venv/bin/python -m sphinx.mcp.server --http &     # MCP :8100
../.venv/bin/python ../sdk/examples/demo_agent.py --transport mcp
```
