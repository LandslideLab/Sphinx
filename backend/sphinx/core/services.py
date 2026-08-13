"""Business logic shared by the REST API, MCP server and the policy engine."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from sphinx.core.delta import diff_dicts
from sphinx.core.events import TOPIC_REQUESTS, bus, publish_sync
from sphinx.models import (
    ApprovalRequest,
    DecisionLog,
    DecisionSource,
    Outcome,
    Policy,
    RequestStatus,
    RiskLevel,
    TimeoutAction,
    utcnow,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _publish_request(event: str, req: ApprovalRequest) -> None:
    publish_sync(TOPIC_REQUESTS, {"type": event, "request": req.to_dict()})


def pick_policy(db: Session, risk_level: str | RiskLevel, policy_id: str | None) -> Policy | None:
    risk = RiskLevel(risk_level) if isinstance(risk_level, str) else risk_level
    if policy_id:
        pol = db.get(Policy, policy_id)
        if pol and pol.enabled:
            return pol
    q = select(Policy).where(Policy.enabled.is_(True))
    policies = db.scalars(q).all()
    candidates = [p for p in policies if risk.value in p.risk_levels]
    return candidates[0] if candidates else (policies[0] if policies else None)


def create_request(
    db: Session,
    *,
    agent_id: str,
    title: str,
    action_payload: dict,
    description: str = "",
    session_id: str = "",
    framework: str = "generic",
    risk_level: str | RiskLevel = RiskLevel.MEDIUM,
    priority: int = 1,
    policy_id: str | None = None,
    requester: str = "agent",
    metadata_: dict | None = None,
) -> ApprovalRequest:
    risk = risk_level if isinstance(risk_level, RiskLevel) else RiskLevel(risk_level)
    policy = pick_policy(db, risk, policy_id)

    req = ApprovalRequest(
        session_id=session_id,
        agent_id=agent_id,
        framework=framework,
        title=title,
        description=description,
        action_payload=action_payload or {},
        risk_level=risk,
        priority=priority,
        requester=requester,
        metadata_=metadata_ or {},
        policy_id=policy.id if policy else None,
        policy_name=policy.name if policy else None,
        timeout_seconds=policy.timeout_seconds if policy else None,
        status=RequestStatus.PENDING,
    )
    db.add(req)

    # Low-risk instant auto-approval path (SLA policy).
    if (
        policy
        and policy.auto_approve_below_risk
        and risk == RiskLevel.LOW
        and policy.on_timeout == TimeoutAction.AUTO_APPROVE
    ):
        db.flush()
        _resolve(
            db,
            req,
            approved=True,
            decision_payload=req.action_payload,
            source=DecisionSource.AUTO_POLICY,
            reviewer_id="sphinx",
            note="Auto-approved: below risk threshold (low-risk policy).",
        )
        db.flush()
        return req

    db.flush()
    _publish_request("created", req)
    return req


def resolve_request(
    db: Session,
    req: ApprovalRequest,
    *,
    approved: bool,
    reviewer_id: str,
    note: str = "",
    decision_payload: dict | None = None,
    amend: bool = False,
    source: DecisionSource = DecisionSource.HUMAN_REVIEW,
    record_decision: bool = True,
) -> ApprovalRequest:
    if req.status != RequestStatus.PENDING:
        raise ValueError(f"request {req.ref} is not pending (current={req.status.value})")
    _resolve(
        db,
        req,
        approved=approved,
        decision_payload=decision_payload,
        source=source,
        reviewer_id=reviewer_id,
        note=note,
        amend=amend,
        record_decision=record_decision,
    )
    return req


def _resolve(
    db: Session,
    req: ApprovalRequest,
    *,
    approved: bool,
    decision_payload: dict | None,
    source: DecisionSource,
    reviewer_id: str,
    note: str,
    amend: bool = False,
    record_decision: bool = True,
) -> None:
    if approved:
        req.status = (
            RequestStatus.AUTO_APPROVED
            if source == DecisionSource.AUTO_POLICY or source == DecisionSource.POLICY_TIMEOUT
            else RequestStatus.APPROVED
        )
        final_payload = decision_payload if decision_payload is not None else req.action_payload
    else:
        req.status = (
            RequestStatus.AUTO_REJECTED
            if source == DecisionSource.POLICY_TIMEOUT
            else RequestStatus.REJECTED
        )
        final_payload = None

    req.decision_payload = final_payload
    req.reviewer_id = reviewer_id
    req.reviewer_note = note
    req.resolved_by = "human" if source == DecisionSource.HUMAN_REVIEW else "policy"
    req.decided_at = _now()

    if record_decision:
        human_decision = decision_payload if amend or decision_payload is not None else req.action_payload
        human_decision = human_decision if approved else None
        if approved and human_decision is not None:
            delta = diff_dicts(req.action_payload, human_decision)
            agreement = (not delta) if source == DecisionSource.HUMAN_REVIEW else None
        else:
            delta, agreement = None, None
        db.add(
            DecisionLog(
                request_id=req.id,
                agent_decision=req.action_payload,
                human_decision=human_decision,
                delta=delta or None,
                agreement=agreement,
                source=source,
                reviewer_id=reviewer_id if source == DecisionSource.HUMAN_REVIEW else None,
                note=note,
            )
        )
    _publish_request("decided", req)


def escalate_request(db: Session, req: ApprovalRequest, reviewer_id: str, note: str = "") -> ApprovalRequest:
    if req.status != RequestStatus.PENDING:
        raise ValueError(f"request {req.ref} is not pending (current={req.status.value})")
    req.escalated = True
    req.escalated_at = _now()
    req.escalation_note = note
    _publish_request("escalated", req)
    return req


def cancel_request(db: Session, req: ApprovalRequest, agent_id: str = "agent") -> ApprovalRequest:
    if req.status != RequestStatus.PENDING:
        raise ValueError(f"request {req.ref} is not pending (current={req.status.value})")
    req.status = RequestStatus.CANCELLED
    req.resolved_by = "agent"
    req.reviewer_id = agent_id
    _publish_request("cancelled", req)
    return req


def submit_feedback(
    db: Session, req: ApprovalRequest, outcome: str | Outcome, note: str = "", agent_id: str = ""
) -> ApprovalRequest:
    if req.status not in (
        RequestStatus.APPROVED,
        RequestStatus.AUTO_APPROVED,
        RequestStatus.REJECTED,
        RequestStatus.AUTO_REJECTED,
    ):
        raise ValueError(f"request {req.ref} has no decision to give feedback on")
    req.outcome = outcome if isinstance(outcome, Outcome) else Outcome(outcome)
    req.outcome_note = note
    db.add(
        DecisionLog(
            request_id=req.id,
            agent_decision=req.action_payload,
            human_decision=req.decision_payload,
            delta=None,
            agreement=None,
            source=DecisionSource.AGENT_FEEDBACK,
            reviewer_id=agent_id or req.agent_id,
            note=f"[feedback outcome={req.outcome.value}] {note}".strip(),
        )
    )
    _publish_request("feedback", req)
    return req


def apply_timeout(db: Session, req: ApprovalRequest) -> ApprovalRequest:
    """Timeout SLA fired: degrade per policy. Default escalate."""
    if req.status != RequestStatus.PENDING or not req.timeout_seconds or req.timeout_fired:
        return req
    if not req.policy_id:
        return req

    req.timeout_fired = True

    policy = db.get(Policy, req.policy_id)
    if not policy or not policy.enabled:
        action = TimeoutAction.ESCALATE
    else:
        action = policy.on_timeout

    if action == TimeoutAction.AUTO_APPROVE:
        _resolve(
            db,
            req,
            approved=True,
            decision_payload=req.action_payload,
            source=DecisionSource.POLICY_TIMEOUT,
            reviewer_id="policy",
            note="SLA timeout exceeded; auto-approved by policy.",
        )
    elif action == TimeoutAction.AUTO_REJECT:
        _resolve(
            db,
            req,
            approved=False,
            decision_payload=None,
            source=DecisionSource.POLICY_TIMEOUT,
            reviewer_id="policy",
            note="SLA timeout exceeded; auto-rejected by policy.",
        )
    else:
        req.escalated = True
        req.escalated_at = req.escalated_at or _now()
        req.escalation_note = req.escalation_note or "SLA timeout exceeded; escalated for review."
        _publish_request("escalated", req)
    return req


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def find_pending_overdue(db: Session, now: datetime | None = None) -> list[ApprovalRequest]:
    now = _utc(now or _now())
    rows = db.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.status == RequestStatus.PENDING,
            ApprovalRequest.timeout_fired.is_(False),
        )
    ).all()
    overdue = []
    for r in rows:
        created = _utc(r.created_at)
        if r.timeout_seconds and created and (created.timestamp() + r.timeout_seconds) <= now.timestamp():
            overdue.append(r)
    return overdue
