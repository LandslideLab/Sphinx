from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from sphinx.core.events import TOPIC_REQUESTS, bus
from sphinx.core.services import (
    cancel_request,
    create_request,
    escalate_request,
    resolve_request,
    submit_feedback,
)
from sphinx.db import get_db
from sphinx.models import ApprovalRequest, RequestStatus, RiskLevel
from sphinx.schemas import DecideRequest, EscalateRequest, FeedbackRequest, RequestCreate

router = APIRouter(prefix="/api/requests", tags=["requests"])


@router.get("")
def list_requests(
    db: Session = Depends(get_db),
    status: str | None = None,
    framework: str | None = None,
    agent_id: str | None = None,
    escalated: bool | None = None,
    risk: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    query = select(ApprovalRequest)
    if status:
        try:
            query = query.where(ApprovalRequest.status == RequestStatus(status))
        except ValueError:
            raise HTTPException(400, f"invalid status: {status}")
    if framework:
        query = query.where(ApprovalRequest.framework == framework)
    if agent_id:
        query = query.where(ApprovalRequest.agent_id == agent_id)
    if escalated is not None:
        query = query.where(ApprovalRequest.escalated.is_(escalated))
    if risk:
        try:
            query = query.where(ApprovalRequest.risk_level == RiskLevel(risk))
        except ValueError:
            raise HTTPException(400, f"invalid risk: {risk}")
    if q:
        like = f"%{q}%"
        query = query.where(
            or_(
                ApprovalRequest.title.ilike(like),
                ApprovalRequest.ref.ilike(like),
                ApprovalRequest.agent_id.ilike(like),
            )
        )
    total = len(db.scalars(query).all())
    query = query.order_by(ApprovalRequest.created_at.desc()).offset(offset).limit(limit)
    rows = db.scalars(query).all()
    return {"total": total, "items": [r.to_dict() for r in rows]}


@router.post("", status_code=201)
def create(db: Session = Depends(get_db), body: RequestCreate = Body(...)):
    req = create_request(
        db,
        agent_id=body.agent_id,
        title=body.title,
        action_payload=body.action_payload,
        description=body.description,
        session_id=body.session_id,
        framework=body.framework,
        risk_level=body.risk_level,
        priority=body.priority,
        policy_id=body.policy_id,
        requester=body.requester,
        metadata_=body.metadata,
    )
    db.commit()
    return req.to_dict()


@router.get("/{request_id}")
def get(db: Session = Depends(get_db), request_id: str = None):
    req = _find(db, request_id)
    return req.to_dict()


@router.post("/{request_id}/approve")
def approve(db: Session = Depends(get_db), request_id: str = None, body: DecideRequest = Body(...)):
    req = _find(db, request_id)
    try:
        resolve_request(
            db,
            req,
            approved=True,
            reviewer_id=body.reviewer_id,
            note=body.note,
            decision_payload=body.decision_payload,
            amend=body.amend,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    db.commit()
    return req.to_dict()


@router.post("/{request_id}/reject")
def reject(db: Session = Depends(get_db), request_id: str = None, body: DecideRequest = Body(...)):
    req = _find(db, request_id)
    try:
        resolve_request(db, req, approved=False, reviewer_id=body.reviewer_id, note=body.note)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    db.commit()
    return req.to_dict()


@router.post("/{request_id}/escalate")
def escalate(db: Session = Depends(get_db), request_id: str = None, body: EscalateRequest = Body(...)):
    req = _find(db, request_id)
    try:
        escalate_request(db, req, reviewer_id=body.reviewer_id, note=body.note)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    db.commit()
    return req.to_dict()


@router.post("/{request_id}/cancel")
def cancel(db: Session = Depends(get_db), request_id: str = None):
    req = _find(db, request_id)
    try:
        cancel_request(db, req)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    db.commit()
    return req.to_dict()


@router.post("/{request_id}/feedback")
def feedback(db: Session = Depends(get_db), request_id: str = None, body: FeedbackRequest = Body(...)):
    req = _find(db, request_id)
    try:
        submit_feedback(db, req, outcome=body.outcome, note=body.note, agent_id=body.agent_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    db.commit()
    return req.to_dict()


def _find(db: Session, request_id: str) -> ApprovalRequest:
    req = db.get(ApprovalRequest, request_id)
    if not req:
        req = db.scalars(select(ApprovalRequest).where(ApprovalRequest.ref == request_id.upper())).first()
    if not req:
        raise HTTPException(404, "approval request not found")
    return req
