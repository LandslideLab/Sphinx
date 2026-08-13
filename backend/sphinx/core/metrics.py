"""Governance metrics computed over the decision log."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from sphinx.models import ApprovalRequest, DecisionLog, DecisionSource, RequestStatus

TERMINAL = {
    RequestStatus.APPROVED,
    RequestStatus.REJECTED,
    RequestStatus.AUTO_APPROVED,
    RequestStatus.AUTO_REJECTED,
    RequestStatus.CANCELLED,
}


def _pct(numer: float, denom: float) -> float:
    return round(100.0 * numer / denom, 1) if denom else 0.0


def compute_metrics(db: Session, since_days: int | None = None) -> dict:
    """Compute control-plane governance metrics.

    Definitions:
      escalation_rate     — requests ever escalated / total created
      timeout_rate        — requests auto-decided by SLA timeout / total decided
      correction_rate     — human reviews whose final payload differs from the agent payload
      reviewer_agreement  — human reviews where the human confirmed the agent decision unchanged
      error_escape_rate   — approved requests reported with a negative outcome / approved with feedback
      sla_compliance_rate — decisions reached before the SLA deadline / decided
      avg/p50/p95 decision latency for human reviews
    """
    q = select(ApprovalRequest)
    if since_days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
        q = q.where(ApprovalRequest.created_at >= cutoff)
    requests = db.scalars(q).all()

    total = len(requests)
    by_status = {s.value: 0 for s in RequestStatus}
    escalated = 0
    human_reviews = []
    decided_at = []
    approved = []
    approved_with_feedback = 0
    negative_outcomes = 0
    timeout_decisions = 0
    decided_count = 0
    sla_ok = 0

    for r in requests:
        by_status[r.status.value] += 1
        if r.escalated:
            escalated += 1
        if r.status in (RequestStatus.APPROVED, RequestStatus.REJECTED):
            human_reviews.append(r)
            if r.decided_at:
                decided_at.append(
                    (r.decided_at.replace(tzinfo=timezone.utc) if r.decided_at.tzinfo is None else r.decided_at)
                    - (r.created_at.replace(tzinfo=timezone.utc) if r.created_at.tzinfo is None else r.created_at)
                )
                if r.timeout_seconds:
                    lat = (
                        r.decided_at.replace(tzinfo=timezone.utc)
                        if r.decided_at.tzinfo is None
                        else r.decided_at
                    ) - (r.created_at.replace(tzinfo=timezone.utc) if r.created_at.tzinfo is None else r.created_at)
                    sla_ok += 1 if lat.total_seconds() <= r.timeout_seconds else 0
        if r.status in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED):
            approved.append(r)
            if r.outcome is not None:
                approved_with_feedback += 1
                if r.outcome.value in ("failure", "partial"):
                    negative_outcomes += 1
        if r.status in (RequestStatus.AUTO_APPROVED, RequestStatus.AUTO_REJECTED):
            timeout_decisions += 1

    decided_count = sum(by_status[s.value] for s in TERMINAL)

    decisions = db.scalars(
        select(DecisionLog).where(DecisionLog.source == DecisionSource.HUMAN_REVIEW)
    ).all()
    corrected = sum(1 for d in decisions if d.delta)
    agreed = sum(1 for d in decisions if d.agreement)

    latency_seconds = [lat.total_seconds() for lat in decided_at] or [0.0]

    def percentile(p: float) -> float:
        if not latency_seconds:
            return 0.0
        ordered = sorted(latency_seconds)
        idx = max(0, min(len(ordered) - 1, int(p / 100 * len(ordered))))
        return round(ordered[idx], 1)

    risk = {rl: {"created": 0, "escalated": 0} for rl in ("low", "medium", "high", "critical")}
    for r in requests:
        key = r.risk_level.value
        if key in risk:
            risk[key]["created"] += 1
            if r.escalated:
                risk[key]["escalated"] += 1

    return {
        "window": {"since_days": since_days, "generated_at": datetime.now(timezone.utc).isoformat()},
        "totals": {
            "requests": total,
            "by_status": by_status,
            "escalated": escalated,
            "pending": by_status[RequestStatus.PENDING.value],
        },
        "governance": {
            "escalation_rate": _pct(escalated, total),
            "timeout_rate": _pct(timeout_decisions, decided_count),
            "correction_rate": _pct(corrected, len(decisions)),
            "reviewer_agreement": _pct(agreed, len(decisions)),
            "error_escape_rate": _pct(negative_outcomes, approved_with_feedback),
            "sla_compliance_rate": _pct(sla_ok, decided_count),
        },
        "latency": {
            "human_reviews": len(decisions),
            "avg_seconds": round(sum(latency_seconds) / len(latency_seconds), 1) if latency_seconds else 0.0,
            "p50_seconds": percentile(50),
            "p95_seconds": percentile(95),
        },
        "risk": risk,
        "feedback": {"approved_with_feedback": approved_with_feedback, "negative_outcomes": negative_outcomes},
    }
