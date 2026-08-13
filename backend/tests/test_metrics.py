"""Unit tests for governance metrics (sphinx.core.metrics)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sphinx.core.metrics import compute_metrics
from sphinx.core.services import (
    apply_timeout,
    create_request,
    escalate_request,
    resolve_request,
    submit_feedback,
)
from sphinx.models import (
    ApprovalRequest,
    DecisionLog,
    Outcome,
    Policy,
    RequestStatus,
    TimeoutAction,
)


def _policy(db, name="standard", timeout=600, on_timeout=TimeoutAction.ESCALATE, risk=("low", "medium", "high", "critical")):
    pol = Policy(name=name, risk_levels=list(risk), timeout_seconds=timeout, on_timeout=on_timeout)
    db.add(pol)
    db.commit()
    return pol


def test_empty_db_metrics_are_zero(db):
    m = compute_metrics(db)
    assert m["totals"]["requests"] == 0
    assert m["governance"]["escalation_rate"] == 0.0
    assert m["governance"]["error_escape_rate"] == 0.0


def test_escalation_rate_and_risk_breakdown(db):
    _policy(db)
    a = create_request(db, agent_id="a", title="t1", action_payload={}, risk_level="medium")
    escalate_request(db, a, reviewer_id="alice", note="suspicious")
    create_request(db, agent_id="a", title="t2", action_payload={}, risk_level="medium")
    db.commit()

    m = compute_metrics(db)
    assert m["totals"]["requests"] == 2
    assert m["governance"]["escalation_rate"] == 50.0
    assert m["risk"]["medium"]["created"] == 2
    assert m["risk"]["medium"]["escalated"] == 1


def test_timeout_rate_counts_auto_decisions(db):
    _policy(db, name="auto-reject", on_timeout=TimeoutAction.AUTO_REJECT)
    req = create_request(db, agent_id="a", title="t", action_payload={}, risk_level="high")
    apply_timeout(db, req)
    db.commit()

    m = compute_metrics(db)
    assert m["totals"]["by_status"]["auto_rejected"] == 1
    assert m["governance"]["timeout_rate"] == 100.0


def test_correction_and_agreement_rates(db):
    _policy(db)
    p1 = {"action": "refund", "amount": 100}
    r1 = create_request(db, agent_id="a", title="t1", action_payload=p1, risk_level="medium")
    resolve_request(db, r1, approved=True, reviewer_id="alice", note="ok")
    r2 = create_request(db, agent_id="a", title="t2", action_payload=p1, risk_level="medium")
    resolve_request(
        db, r2, approved=True, reviewer_id="bob", note="changed", decision_payload={"action": "refund", "amount": 80}, amend=True
    )
    db.commit()

    m = compute_metrics(db)
    assert m["governance"]["reviewer_agreement"] == 50.0
    assert m["governance"]["correction_rate"] == 50.0
    assert m["latency"]["human_reviews"] == 2


def test_error_escape_rate(db):
    _policy(db)
    r1 = create_request(db, agent_id="a", title="t1", action_payload={}, risk_level="medium")
    resolve_request(db, r1, approved=True, reviewer_id="alice", note="ok")
    submit_feedback(db, r1, Outcome.FAILURE, note="bad", agent_id="a")
    r2 = create_request(db, agent_id="a", title="t2", action_payload={}, risk_level="medium")
    resolve_request(db, r2, approved=True, reviewer_id="bob", note="ok")
    submit_feedback(db, r2, Outcome.SUCCESS, note="good", agent_id="a")
    r3 = create_request(db, agent_id="a", title="t3", action_payload={}, risk_level="medium")
    resolve_request(db, r3, approved=True, reviewer_id="carol", note="ok")
    # r3: approved but NO feedback submitted
    db.commit()

    m = compute_metrics(db)
    assert m["feedback"]["approved_with_feedback"] == 2
    assert m["feedback"]["negative_outcomes"] == 1
    assert m["governance"]["error_escape_rate"] == 50.0


def test_sla_compliance_rate(db):
    _policy(db, name="sla", timeout=600)
    r1 = create_request(db, agent_id="a", title="t1", action_payload={}, risk_level="medium")
    r1.created_at = datetime.now(timezone.utc) - timedelta(seconds=100)
    resolve_request(db, r1, approved=True, reviewer_id="alice", note="quick")
    r2 = create_request(db, agent_id="a", title="t2", action_payload={}, risk_level="medium")
    r2.created_at = datetime.now(timezone.utc) - timedelta(seconds=1000)
    resolve_request(db, r2, approved=True, reviewer_id="bob", note="slow")
    db.commit()

    m = compute_metrics(db)
    assert m["governance"]["sla_compliance_rate"] == 50.0


def test_since_days_window(db):
    _policy(db)
    r = create_request(db, agent_id="a", title="old", action_payload={}, risk_level="medium")
    r.created_at = datetime.now(timezone.utc) - timedelta(days=60)
    db.commit()

    all_time = compute_metrics(db, since_days=None)
    recent = compute_metrics(db, since_days=7)
    assert all_time["totals"]["requests"] == 1
    assert recent["totals"]["requests"] == 0


def test_by_status_contains_all_statuses(db):
    _policy(db)
    for risk in ("medium", "high", "critical"):
        create_request(db, agent_id="a", title="t", action_payload={}, risk_level=risk)
    db.commit()
    m = compute_metrics(db)
    assert m["totals"]["by_status"]["pending"] == 3
    for s in ("pending", "approved", "rejected", "cancelled", "auto_approved", "auto_rejected"):
        assert s in m["totals"]["by_status"]
