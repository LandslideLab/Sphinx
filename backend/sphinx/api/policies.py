from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from sphinx.core.events import TOPIC_POLICIES, publish_sync
from sphinx.core.metrics import compute_metrics
from sphinx.db import get_db
from sphinx.models import DecisionLog, Policy, TimeoutAction
from sphinx.schemas import PolicyCreate, PolicyUpdate

router = APIRouter(tags=["policies", "decisions", "metrics"])


def _publish_policy(event: str, pol: Policy) -> None:
    publish_sync(TOPIC_POLICIES, {"type": event, "policy": pol.to_dict()})


@router.get("/api/policies")
def list_policies(db: Session = Depends(get_db)):
    rows = db.scalars(select(Policy).order_by(Policy.created_at)).all()
    return {"items": [p.to_dict() for p in rows]}


@router.post("/api/policies", status_code=201)
def create_policy(db: Session = Depends(get_db), body: PolicyCreate = Body(...)):
    existing = db.scalars(select(Policy).where(Policy.name == body.name)).first()
    if existing:
        raise HTTPException(409, f"policy name already exists: {body.name}")
    pol = Policy(
        name=body.name,
        description=body.description,
        risk_levels=body.risk_levels,
        timeout_seconds=body.timeout_seconds,
        on_timeout=TimeoutAction(body.on_timeout),
        auto_approve_below_risk=body.auto_approve_below_risk,
        min_reviewers=body.min_reviewers,
        enabled=body.enabled,
    )
    db.add(pol)
    db.commit()
    _publish_policy("created", pol)
    return pol.to_dict()


@router.put("/api/policies/{policy_id}")
def update_policy(db: Session = Depends(get_db), policy_id: str = None, body: PolicyUpdate = Body(...)):
    pol = db.get(Policy, policy_id)
    if not pol:
        raise HTTPException(404, "policy not found")
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key == "on_timeout":
            value = TimeoutAction(value)
        setattr(pol, key, value)
    db.commit()
    _publish_policy("updated", pol)
    return pol.to_dict()


@router.get("/api/decisions")
def list_decisions(
    db: Session = Depends(get_db),
    source: str | None = None,
    agreement: bool | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    query = select(DecisionLog)
    if source:
        query = query.where(DecisionLog.source == source)
    if agreement is not None:
        query = query.where(DecisionLog.agreement.is_(agreement))
    total = len(db.scalars(query).all())
    query = query.order_by(DecisionLog.created_at.desc()).offset(offset).limit(limit)
    rows = db.scalars(query).all()
    return {"total": total, "items": [d.to_dict() for d in rows]}


@router.get("/api/metrics")
def metrics(db: Session = Depends(get_db), since_days: int | None = None):
    return compute_metrics(db, since_days=since_days)
