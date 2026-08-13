"""Capture ingestion service: links events into a tamper-evident chain and
persists them. Shared by the REST API and seed data so every path builds the
same hash chain + signature structure.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from sphinx import models
from sphinx.core import capture_chain
from sphinx.core.events import TOPIC_CAPTURE, publish_sync
from sphinx.models import CaptureEvent, CaptureEventType


def _chain_tail(db: Session, agent_id: str, session_id: str) -> str | None:
    """Content hash of the most recent event in the (agent, session) chain."""
    last = (
        db.query(CaptureEvent)
        .filter(CaptureEvent.agent_id == agent_id, CaptureEvent.session_id == session_id)
        .order_by(CaptureEvent.sequence.desc(), CaptureEvent.created_at.desc())
        .first()
    )
    return last.content_hash if last else None


def _next_sequence(db: Session, agent_id: str, session_id: str) -> int:
    tail = (
        db.query(CaptureEvent)
        .filter(CaptureEvent.agent_id == agent_id, CaptureEvent.session_id == session_id)
        .order_by(CaptureEvent.sequence.desc())
        .first()
    )
    return (tail.sequence + 1) if tail else 1


def ingest_event(
    db: Session,
    *,
    signing_key,
    agent_id: str,
    event_type: str,
    event_name: str = "",
    input_payload: dict | None = None,
    output_payload: dict | None = None,
    metadata: dict | None = None,
    status: str = "ok",
    session_id: str = "",
    sequence: int | None = None,
) -> CaptureEvent:
    """Append one event to its chain and persist it. Returns the stored event."""
    try:
        parsed_type = CaptureEventType(event_type)
    except ValueError:
        raise ValueError(f"invalid event_type: {event_type!r}")

    if sequence is None:
        sequence = _next_sequence(db, agent_id, session_id)
    if sequence < 1:
        raise ValueError("sequence must be >= 1")

    content = capture_chain.content_of(
        event_type=parsed_type.value,
        event_name=event_name,
        sequence=sequence,
        input_payload=input_payload or {},
        output_payload=output_payload or {},
        metadata=metadata or {},
        status=status,
    )
    content_hash = capture_chain.hash_content(content)
    prev_hash = _chain_tail(db, agent_id, session_id)
    signature = capture_chain.sign_message(signing_key, prev_hash, content_hash)

    event = CaptureEvent(
        id=str(uuid.uuid4()),
        session_id=session_id,
        agent_id=agent_id,
        event_type=parsed_type,
        event_name=event_name,
        sequence=sequence,
        input_payload=input_payload or {},
        output_payload=output_payload or {},
        metadata_=metadata or {},
        status=status,
        content_hash=content_hash,
        prev_hash=prev_hash,
        signature=signature,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    publish_sync(TOPIC_CAPTURE, {"event_id": event.id, "agent_id": agent_id, "event_type": parsed_type.value})
    return event


def ingest_batch(
    db: Session,
    *,
    signing_key,
    agent_id: str,
    events: list[dict],
    session_id: str = "",
) -> list[CaptureEvent]:
    """Ingest multiple events for one agent in arrival order, chaining them."""
    stored: list[CaptureEvent] = []
    for ev in events:
        if not isinstance(ev, dict):
            raise ValueError("each event must be an object")
        stored.append(
            ingest_event(
                db,
                signing_key=signing_key,
                agent_id=agent_id,
                session_id=session_id,
                event_type=ev.get("event_type", ""),
                event_name=ev.get("event_name", ""),
                input_payload=ev.get("input_payload"),
                output_payload=ev.get("output_payload"),
                metadata=ev.get("metadata"),
                status=ev.get("status", "ok"),
            )
        )
    return stored


def get_signing_key(db: Session):
    """Load the org signing key from the DB (created on first use)."""
    row = db.query(models.SigningKey).first()
    if row is None:
        key = capture_chain.SigningKey.generate()
        db.add(models.SigningKey(seed_b64=capture_chain.seed_to_b64(key)))
        db.commit()
        return key
    return capture_chain.load_signing_key(row.seed_b64)


def get_verify_key(db: Session):
    return get_signing_key(db).verify_key


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
