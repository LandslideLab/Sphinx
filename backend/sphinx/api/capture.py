"""Capture API: ingest tool calls / LLM inferences / state changes into the
tamper-evident chain, query them, and verify chain integrity.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from sphinx.core import capture_chain, capture_service
from sphinx.db import get_db
from sphinx.models import CaptureEvent
from sphinx.schemas import CaptureBatchIn

router = APIRouter(prefix="/api/capture", tags=["capture"])


@router.post("")
def ingest_capture(body: CaptureBatchIn, db: Session = Depends(get_db)):
    """Append one or more events to an agent's capture chain."""
    try:
        signing_key = capture_service.get_signing_key(db)
        stored = capture_service.ingest_batch(
            db,
            signing_key=signing_key,
            agent_id=body.agent_id,
            session_id=body.session_id,
            events=[e.model_dump() for e in body.events],
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {
        "received": len(stored),
        "agent_id": body.agent_id,
        "session_id": body.session_id,
        "first": stored[0].to_dict() if stored else None,
        "last": stored[-1].to_dict() if stored else None,
    }


@router.get("")
def list_capture(
    db: Session = Depends(get_db),
    agent_id: str | None = None,
    session_id: str | None = None,
    event_type: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    query = select(CaptureEvent)
    if agent_id:
        query = query.where(CaptureEvent.agent_id == agent_id)
    if session_id:
        query = query.where(CaptureEvent.session_id == session_id)
    if event_type:
        try:
            from sphinx.models import CaptureEventType

            query = query.where(CaptureEvent.event_type == CaptureEventType(event_type))
        except ValueError:
            raise HTTPException(400, f"invalid event_type: {event_type}")
    total = len(db.scalars(query).all())
    rows = (
        db.scalars(
            query.order_by(CaptureEvent.created_at.desc(), CaptureEvent.sequence.desc())
            .offset(offset)
            .limit(limit)
        )
        .all()
    )
    return {"total": total, "items": [r.to_dict() for r in rows]}


@router.get("/verify")
def verify_capture(
    db: Session = Depends(get_db),
    agent_id: str | None = None,
    session_id: str | None = None,
):
    """Recompute the hash chain and verify signatures for all captured events
    (optionally scoped to one agent / session)."""
    query = select(CaptureEvent)
    if agent_id:
        query = query.where(CaptureEvent.agent_id == agent_id)
    if session_id:
        query = query.where(CaptureEvent.session_id == session_id)
    rows = db.scalars(query.order_by(CaptureEvent.agent_id, CaptureEvent.session_id, CaptureEvent.sequence)).all()
    if not rows:
        return {"valid": True, "checked": 0, "errors": [], "chains": 0}
    verify_key = capture_service.get_verify_key(db)
    result = capture_chain.verify_chain([r.to_dict() for r in rows], verify_key)
    chains = len({(r.agent_id, r.session_id) for r in rows})
    return {**result, "chains": chains}
