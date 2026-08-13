"""Sphinx MCP server.

Exposes the HITL control plane to any MCP-capable agent framework
(LangGraph / OpenAI SDK / CrewAI / ...) via standard MCP tools.

Run standalone:
    python -m sphinx.mcp.server              # stdio
    python -m sphinx.mcp.server --http       # streamable HTTP on :8100

Mount into FastAPI:
    from sphinx.mcp.server import mcp
    app.mount("/mcp", mcp.streamable_http_app())
"""
from __future__ import annotations

import argparse
import logging
import time
from typing import Any

from mcp.server.mcpserver import MCPServer
from sqlalchemy import select

from sphinx.config import settings
from sphinx.core.services import create_request, resolve_request, submit_feedback
from sphinx.db import SessionLocal
from sphinx.models import ApprovalRequest, Policy, RequestStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("sphinx.mcp")

INSTRUCTIONS = (
    "Sphinx is a framework-agnostic human-in-the-loop approval control plane for agent "
    "workflows. Agents request approval for risky actions, wait for a human (or policy) "
    "decision, then read the final decision payload before executing. Every decision is "
    "logged and used to compute governance metrics. Tool names are prefixed with sphinx_."
)

mcp = MCPServer(
    "sphinx",
    version="0.1.0",
    instructions=INSTRUCTIONS,
    title="Sphinx HITL Control Plane",
)


def _find(db, request_id: str) -> ApprovalRequest:
    r = db.get(ApprovalRequest, request_id)
    if not r:
        r = db.scalars(select(ApprovalRequest).where(ApprovalRequest.ref == request_id.upper())).first()
    if not r:
        raise ValueError(f"approval request not found: {request_id}")
    return r


@mcp.tool()
def sphinx_request_approval(
    agent_id: str,
    title: str,
    action_payload: dict[str, Any],
    description: str = "",
    session_id: str = "",
    framework: str = "generic",
    risk_level: str = "medium",
    priority: int = 1,
    policy_id: str = "",
) -> dict[str, Any]:
    """Request human approval for an agent action. Returns the ticket id/ref and status."""
    with SessionLocal() as db:
        req = create_request(
            db,
            agent_id=agent_id,
            title=title,
            action_payload=action_payload,
            description=description,
            session_id=session_id,
            framework=framework,
            risk_level=risk_level,
            priority=priority,
            policy_id=policy_id or None,
        )
        db.commit()
        return {"id": req.id, "ref": req.ref, "status": req.status.value}


@mcp.tool()
def sphinx_get_status(request_id: str) -> dict[str, Any]:
    """Check the current status of an approval request by id or ref."""
    with SessionLocal() as db:
        req = _find(db, request_id)
        return {"id": req.id, "ref": req.ref, "status": req.status.value, "escalated": req.escalated}


@mcp.tool()
def sphinx_wait_for_decision(
    request_id: str, timeout_s: int = 300, poll_interval_s: float = 2.0
) -> dict[str, Any]:
    """Block until the approval request is decided, or timeout_s elapses.

    Returns the final status and decision payload so the agent can proceed/abort.
    """
    deadline = time.time() + timeout_s
    with SessionLocal() as db:
        req = _find(db, request_id)
        while req.status == RequestStatus.PENDING:
            if time.time() > deadline:
                break
            db.commit()
            db.expire_all()
            req = _find(db, request_id)
            time.sleep(max(0.2, min(poll_interval_s, 5.0)))
        return {
            "id": req.id,
            "ref": req.ref,
            "status": req.status.value,
            "approved": req.status in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED),
            "decision_payload": req.decision_payload,
            "reviewer_id": req.reviewer_id,
            "reviewer_note": req.reviewer_note,
            "escalated": req.escalated,
        }


@mcp.tool()
def sphinx_get_decision(request_id: str) -> dict[str, Any]:
    """Get the final decision and payload for an approved/rejected request."""
    with SessionLocal() as db:
        req = _find(db, request_id)
        return {
            "id": req.id,
            "ref": req.ref,
            "status": req.status.value,
            "approved": req.status in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED),
            "decision_payload": req.decision_payload,
            "reviewer_id": req.reviewer_id,
            "reviewer_note": req.reviewer_note,
            "resolved_by": req.resolved_by,
            "decided_at": req.decided_at.isoformat() if req.decided_at else None,
        }


@mcp.tool()
def sphinx_submit_feedback(
    request_id: str, outcome: str, note: str = "", agent_id: str = ""
) -> dict[str, Any]:
    """Report the real-world outcome of a decided action (success|failure|partial).

    This closes the feedback loop and feeds error_escape_rate metrics.
    """
    with SessionLocal() as db:
        req = _find(db, request_id)
        submit_feedback(db, req, outcome=outcome, note=note, agent_id=agent_id)
        db.commit()
        return {"id": req.id, "ref": req.ref, "outcome": req.outcome.value}


@mcp.tool()
def sphinx_list_policies() -> dict[str, Any]:
    """List available SLA / timeout policies for approval requests."""
    with SessionLocal() as db:
        rows = db.scalars(select(Policy)).all()
        return {"items": [p.to_dict() for p in rows]}


@mcp.resource("sphinx://requests/{request_id}")
def resource_request(request_id: str) -> str:
    with SessionLocal() as db:
        req = _find(db, request_id)
        return str(req.to_dict())


def main() -> None:
    parser = argparse.ArgumentParser(description="Sphinx MCP server")
    parser.add_argument("--http", action="store_true", help="run over streamable HTTP")
    parser.add_argument("--port", type=int, default=settings.mcp_port)
    args = parser.parse_args()

    if args.http:
        logger.info("Sphinx MCP over streamable HTTP on :%s", args.port)
        mcp.run(transport="streamable-http", host="0.0.0.0", port=args.port)
    else:
        logger.info("Sphinx MCP over stdio")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
