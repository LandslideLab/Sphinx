# Sphinx — Full Test Report

**Project:** Sphinx · Agent HITL Control Plane (LANDSLIDE)
**Date:** 2026-08-13
**Commit:** `414c71e` (baseline) + redesign & frontend upgrade on top
**Result:** ✅ **146 / 146 automated tests passed** (backend 109 + frontend 37) + live end-to-end verification passed

---

## 1. Executive summary

Sphinx was verified against every capability in its spec: the REST control plane, WebSocket live events, the SLA timeout engine, governance metrics, the MCP server, the Python SDK with all three framework adapters (LangGraph / OpenAI / CrewAI), the demo agent, seed data, and the web console.

This session delivered an **Apple HIG + Glassmorphism redesign of the web console**, added `risk` filtering and `q` search to the backend, and stood up a **frontend test suite** (Vitest + jsdom + Testing Library) that did not exist before.

- **109 backend automated tests** — baseline 107 (unchanged) + 2 new (`test_list_risk_filter`, `test_filter_decisions_by_q`). 0 failures, 0 errors, 0 skips.
- **37 frontend automated tests** — 9 files across pages, components, and lib utilities. 0 failures.
- **Live end-to-end flows** exercised against real running servers (REST :8001, MCP :8100, Web console dev server :5173 with `/api` and `/mcp` proxy).
- **Web console** compiles clean (`tsc -b && vite build`) and is deployed to a live preview.
- **Bugs found and fixed during verification:** baseline fixes (dead WebSocket event bus, wrong `deadline`, optional `None` bodies, CrewAI `framework` kwarg, policy `on_timeout` enum) plus this session's fixes: `format.ts` JSX-in-`.ts` parse error, `key++` in JSX expression, unstable `load` callback causing a render churn loop in the Decisions page, and a missing `ws: true` on the `/api` Vite proxy that silently broke live updates. All are covered by tests.

---

## 2. Test environment

| item | value |
|------|-------|
| OS | Linux, Python 3.11.2, Node 22.22.0 |
| Backend | FastAPI + SQLAlchemy 2 + SQLite (WAL), MCP Python SDK |
| SDK | `sphinx-sdk` 0.1.0 (REST + MCP transports) |
| Web | React 18 + Vite 5 + TypeScript 5, Vitest 4 + @testing-library/react + jsdom |
| Backend runner | pytest 8 + pytest-asyncio, `backend/tests/` |
| Frontend runner | `vitest run` (jsdom, setup `src/test/setup.ts` with a MockWebSocket stub), `web/src/**/*.{test,spec}.{ts,tsx}` |
| Isolation | per-test in-memory/temp SQLite DB; live integration stack on a dedicated temp DB; frontend pages mock `lib/api` |

---

## 3. Backend automated test inventory

| file | tests | coverage |
|------|------:|----------|
| `test_services.py` | 26 | service layer: policy matching, request creation (pending / auto-approve), approve/reject (agreement + delta), escalate, cancel, feedback, SLA timeout actions (auto_approve / auto_reject / escalate / idempotency), overdue detection, seed idempotency |
| `test_api.py` | 33 | full REST surface: health, requests CRUD + approve/reject/escalate/cancel/feedback, filters/search/pagination, `risk` filter, decisions list + agreement filter + `q` search, 400/404/409/422 errors, policies CRUD + conflict + validation, metrics shape + window |
| `test_metrics.py` | 8 | metric math: zero-state, escalation rate + risk breakdown, timeout rate, correction & agreement rates, error escape rate, SLA compliance, since-days window, status mix completeness |
| `test_policy_engine.py` | 3 | background scheduler: idempotent start/stop, live auto-approve firing, live escalate firing |
| `test_delta.py` | 5 | `diff_dicts`: add/replace/remove, nested paths, equality, empty base, `summarize_delta` |
| `test_ws.py` | 6 | WebSocket live events: create→`created`, approve→`decided`, reject/escalate/cancel/feedback topics, policy events, multi-client fan-out, disconnect resilience |
| `test_mcp.py` | 7 | MCP server over real streamable HTTP: list policies, request + status, decision after approve, wait-for-decision, feedback, `sphinx://requests/{id}` resource, full lifecycle via `SphinxClient` |
| `test_sdk.py` | 13 | RestTransport round-trip + timeout, `SphinxClient` flow, LangGraph `HITLGuard` + `hitl_interrupt_node`, OpenAI `ApprovalGate` (dict + JSON string + non-blocking + event callback), CrewAI callback (approved + blocked) |
| `test_demo_agent.py` | 3 | demo agent end-to-end over REST and MCP transports; tickets visible via API with closed feedback loop |
| `test_seed.py` | 5 | default policies, 28 demo rows, idempotency, plausible metrics, agent/framework diversity |
| **Total** | **109** | baseline 107 + `risk` filter + decisions `q` search |

### Full run output

```
........................................................................ [ 66%]
.....................................                                    [100%]
109 passed in 42.64s
```

---

## 4. Frontend automated test inventory

New in this session: Vitest 4 + jsdom + Testing Library, `web/src/test/setup.ts` (jest-dom matchers + `MockWebSocket` stub so `useLive` can open a socket in jsdom), and 37 tests across 9 files.

| file | tests | coverage |
|------|------:|----------|
| `src/pages/Queue.test.tsx` | 7 | renders pending tickets + total, empty state, risk filter passed to api, approve modal → `api.approve`, reject with reviewer note, detail panel expansion, escalated badge |
| `src/pages/Decisions.test.tsx` | 4 | renders decision rows with deltas, agreement badge on human confirm, empty state, source filter |
| `src/pages/Metrics.test.tsx` | 4 | four headline stats, all governance gauges, risk breakdown, window switching |
| `src/pages/Policies.test.tsx` | 4 | renders policies with SLA details, disabled mark, toggle via `updatePolicy`, create via modal |
| `src/components/Toast.test.tsx` | 3 | success/error/info kinds, auto-dismiss after ~4.2s, info default |
| `src/components/Countdown.test.tsx` | 4 | remaining-time formatting, danger below 30 s, ticking, `fmtRemaining` |
| `src/components/DeltaView.test.tsx` | 2 | no-delta confirmation, add/remove/replace operations |
| `src/lib/format.test.ts` | 6 | `timeAgo`, `fmtClock`, `fmtDuration`, status labels, risk colors, `frameworkLabel` |
| `src/lib/jsonTokens.test.tsx` | 3 | highlight tokens, escaped strings, exact round-trip |
| **Total** | **37** | |

### Full run output (stable across repeated runs)

```
Test Files  9 passed (9)
     Tests  37 passed (37)
```

---

## 5. Feature verification matrix (automated)

| # | feature | evidence |
|---|---------|----------|
| 1 | REST health + lifecycle (create/get/approve/reject/escalate/cancel/feedback) | `test_api.py` 33 tests |
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
| 13 | **Queue page**: risk/framework/status filters, detail expand, approve/reject/escalate modals, skeleton loading | `Queue.test.tsx` (7) |
| 14 | **Decisions page**: delta diff view, agreement badge, source filter, paginated load-more | `Decisions.test.tsx` (4) |
| 15 | **Metrics page**: headline KPIs, governance gauges, risk breakdown, time window | `Metrics.test.tsx` (4) |
| 16 | **Policies page**: SLA display, disable toggle, edit/create modal | `Policies.test.tsx` (4) |
| 17 | UI primitives: toast queue + auto-dismiss, SLA countdown, delta view, JSON tokenizer, format helpers | components/lib tests (18) |

---

## 6. Live end-to-end verification

Performed against running servers seeded with demo data (`SPHINX_SEED_DEMO_DATA=true`).

### 6.1 Stack health

| check | result |
|-------|--------|
| `GET /api/health` | `{"service":"sphinx","status":"ok"}` ✅ |
| `POST /mcp` initialize | MCP capabilities + instructions returned ✅ |
| Web dev server `:5173` + `/api` proxy + `/mcp` proxy | HTTP 200 for all ✅ |
| Seeded metrics | 28 requests, 9 pending, realistic KPI values ✅ |
| Seeded decisions | 25 rows, `q=SPH-4F` → 2 matches ✅ |

### 6.2 New backend filters (live)

| check | result |
|-------|--------|
| `GET /api/requests?risk=high` | 9 results (filter honored) ✅ |
| `GET /api/requests?risk=critical` | 11 results ✅ |
| `GET /api/requests?risk=low\|medium\|high\|critical` | frontend options match `RiskLevel` enum exactly ✅ |
| `GET /api/decisions?q=<ref>` | substring match across `request_ref` via JOIN ✅ |

### 6.3 Full HITL loop (live)

- **create** → `POST /api/requests` (high risk) → `201` with `SPH-*` ref ✅
- **pending count** moved 9 → 10 ✅
- **approve** → `POST /api/requests/{id}/approve` (reviewer + note) → returns resolved request ✅
- **decision landed** → `GET /api/decisions?q=E2E` → 1 decision row ✅

### 6.4 WebSocket live events (live)

A real WS client through the Vite proxy completed the HTTP `101 Switching Protocols` upgrade on `GET /api/ws`; `useLive` consumes `hello` + `requests decided` events on the console. ✅

### 6.5 Web console preview

Built with `tsc -b && vite build` (0 errors) and served at:
`https://5173-8489303537fedee7.monkeycode-ai.online`

Index title, JS/CSS assets, and `/api/metrics` all return 200 through the preview proxy. ✅

---

## 7. Bugs found & fixed (now regression-tested)

| bug | fix | regression test |
|-----|-----|-----------------|
| WebSocket event bus never published (dead channel) | `publish_sync()` bridge + publish from services, policies API and policy engine | `test_ws.py` (6) |
| `ApprovalRequest.deadline` returned `created_at` instead of `created_at + timeout` | corrected with timezone-safe arithmetic | `test_services` (via `seconds_pending`/overdue) |
| REST `POST` bodies defaulted to `None` (crashed instead of 422) | required `Body(...)` | `test_api::test_create_missing_body_422` |
| CrewAI adapter passed unsupported `framework` kwarg to `HITLGuard` | pop before construction, forward to request call | `test_sdk` crewai tests |
| Policy `on_timeout` stored as string, crashing `to_dict` | coerce to `TimeoutAction` enum on create/update | `test_api` policy tests |
| Test isolation: API-test data leaked into unit tests | `db` fixture wipes tables at setup | full suite green |
| `format.ts` contained JSX (oxc parser: `[PARSE_ERROR] Expected >`) | moved highlight logic into `src/lib/jsonTokens.tsx` | `jsonTokens.test.tsx` |
| `key++` inside a JSX attribute expression failed to parse | evaluate then increment (`const k = key++;`) | `jsonTokens.test.tsx` |
| Decisions page render churn: `load` recreated on every `offset` change → double fetch + skeleton flicker (flaky test) | `offset` moved to a ref; `load` is stable per filter set | `Decisions.test.tsx` (4) |
| Vite `/api` proxy lacked `ws: true` → live WS updates never reached the console | added `ws: true` to the proxy | live 6.4 |
| Preview host was blocked by `allowedHosts` | added `.monkeycode-ai.online` | live 6.5 |

---

## 8. Known limitations / notes

- **SQLite concurrency:** the compose stack shares one SQLite file (WAL) between API and MCP processes — correct for single-node/self-hosted use; for multi-node production switch `SPHINX_DATABASE_URL` to Postgres (SQLAlchemy URL swap only).
- **Docker images were not built** in this environment (no Docker daemon); `docker-compose.yml`, `docker/Dockerfile.api`, `docker/Dockerfile.web` and `docker/nginx.conf` are standard and follow the verified local topology (API :8001, MCP :8100, web proxy :8080).
- The SLA engine is a single-threaded in-process scheduler; horizontal scaling would move it to a distributed job (e.g., `apscheduler` + Postgres) — out of scope for v0.1.
- AuthN/Z for the console and API is deliberately out of scope for v0.1 (internal control plane).
- Frontend tests mock `lib/api`; the WebSocket layer is covered by unit tests plus the live WS check, not by an in-browser harness.

---

## 9. How to reproduce

```bash
# 1. install
python3 -m venv .venv
.venv/bin/pip install -e "backend[dev]" -e sdk
cd web && npm install

# 2. run the full backend suite
cd backend && ../.venv/bin/python -m pytest -q        # → 109 passed

# 3. run the full frontend suite
cd web && npx vitest run                                # → 37 passed

# 4. production build
cd web && npm run build                                 # → tsc -b && vite build, 0 errors

# 5. run the demo agent against a live stack
SPHINX_SEED_DEMO_DATA=1 ../.venv/bin/sphinx-api &     # API :8001
../.venv/bin/python -m sphinx.mcp.server --http &     # MCP :8100
cd web && npm run dev &                                # web :5173
../.venv/bin/python ../sdk/examples/demo_agent.py --transport mcp
```
