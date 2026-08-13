"""Unit tests for the shared service layer (sphinx.core.services)."""
from __future__ import annotations

import pytest

from sphinx.core.services import (
    apply_timeout,
    cancel_request,
    create_request,
    escalate_request,
    find_pending_overdue,
    pick_policy,
    resolve_request,
    submit_feedback,
)
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
from sphinx.seed import seed_policies


def _make_policy(
    db,
    name="p-test",
    risk_levels=("medium", "high", "critical"),
    timeout_seconds=600,
    on_timeout=TimeoutAction.ESCALATE,
    auto_approve_below_risk=False,
) -> Policy:
    pol = Policy(
        name=name,
        description="test policy",
        risk_levels=list(risk_levels),
        timeout_seconds=timeout_seconds,
        on_timeout=on_timeout,
        auto_approve_below_risk=auto_approve_below_risk,
    )
    db.add(pol)
    db.commit()
    return pol


class TestPickPolicy:
    def test_selects_policy_matching_risk(self, db):
        _make_policy(db, name="for-medium", risk_levels=["medium"])
        _make_policy(db, name="for-low", risk_levels=["low"])
        pol = pick_policy(db, RiskLevel.MEDIUM, None)
        assert pol.name == "for-medium"

    def test_explicit_policy_id_wins(self, db):
        low = _make_policy(db, name="low", risk_levels=["low"])
        _make_policy(db, name="med", risk_levels=["medium", "high"])
        pol = pick_policy(db, RiskLevel.MEDIUM, low.id)
        assert pol.name == "low"

    def test_disabled_policy_not_picked(self, db):
        _make_policy(db, name="enabled", risk_levels=["high"])
        disabled = Policy(
            name="disabled",
            risk_levels=["high"],
            timeout_seconds=60,
            enabled=False,
        )
        db.add(disabled)
        db.commit()
        pol = pick_policy(db, RiskLevel.HIGH, disabled.id)
        assert pol.name == "enabled"

    def test_no_policies_returns_none(self, db):
        assert pick_policy(db, RiskLevel.HIGH, None) is None


class TestCreateRequest:
    def test_medium_risk_pending_with_policy(self, db):
        pol = _make_policy(db, name="standard", timeout_seconds=123)
        req = create_request(
            db,
            agent_id="agent-1",
            title="Refund $100",
            action_payload={"action": "refund", "amount": 100},
            risk_level="medium",
        )
        assert req.status == RequestStatus.PENDING
        assert req.policy_name == "standard"
        assert req.timeout_seconds == 123
        assert req.risk_level == RiskLevel.MEDIUM
        assert req.agent_id == "agent-1"
        assert req.framework == "generic"
        assert req.ref.startswith("SPH-")

    def test_low_risk_auto_approved(self, db):
        _make_policy(
            db,
            name="auto",
            risk_levels=["low"],
            on_timeout=TimeoutAction.AUTO_APPROVE,
            auto_approve_below_risk=True,
        )
        req = create_request(
            db,
            agent_id="agent-1",
            title="Auto ticket",
            action_payload={"action": "create_ticket"},
            risk_level="low",
        )
        assert req.status == RequestStatus.AUTO_APPROVED
        assert req.resolved_by == "policy"
        decisions = db.query(DecisionLog).filter_by(request_id=req.id).all()
        assert len(decisions) == 1
        assert decisions[0].source == DecisionSource.AUTO_POLICY

    def test_explicit_policy_low_risk_no_auto(self, db):
        _make_policy(db, name="manual-low", risk_levels=["low"], auto_approve_below_risk=False)
        req = create_request(db, agent_id="a", title="t", action_payload={}, risk_level="low")
        assert req.status == RequestStatus.PENDING


class TestResolve:
    def _pending(self, db, risk="medium", payload=None):
        _make_policy(db, name="standard", timeout_seconds=600)
        return create_request(
            db,
            agent_id="agent",
            title="Approve refund",
            action_payload=payload or {"action": "refund", "amount": 100},
            risk_level=risk,
        )

    def test_approve_unchanged_records_agreement(self, db):
        req = self._pending(db)
        resolve_request(db, req, approved=True, reviewer_id="alice", note="ok")
        db.commit()
        assert req.status == RequestStatus.APPROVED
        assert req.decision_payload == req.action_payload
        assert req.resolved_by == "human"
        d = db.query(DecisionLog).filter_by(request_id=req.id).one()
        assert d.agreement is True
        assert d.delta is None
        assert d.reviewer_id == "alice"

    def test_approve_amended_records_delta(self, db):
        payload = {"action": "refund", "amount": 100}
        req = self._pending(db, payload=payload)
        resolve_request(db, req, approved=True, reviewer_id="bob", note="lowered amount", decision_payload={"action": "refund", "amount": 50}, amend=True)
        db.commit()
        d = db.query(DecisionLog).filter_by(request_id=req.id).one()
        assert d.agreement is False
        assert d.delta is not None
        assert any(c["path"] == "amount" and c["op"] == "replace" for c in d.delta)

    def test_reject_records_decision(self, db):
        req = self._pending(db)
        resolve_request(db, req, approved=False, reviewer_id="carol", note="blocked")
        db.commit()
        assert req.status == RequestStatus.REJECTED
        assert req.decision_payload is None
        d = db.query(DecisionLog).filter_by(request_id=req.id).one()
        assert d.human_decision is None

    def test_resolve_non_pending_raises(self, db):
        req = self._pending(db)
        resolve_request(db, req, approved=True, reviewer_id="x", note="")
        with pytest.raises(ValueError):
            resolve_request(db, req, approved=True, reviewer_id="x", note="")


class TestEscalateCancel:
    def test_escalate(self, db):
        req = create_request(db, agent_id="a", title="t", action_payload={})
        escalate_request(db, req, reviewer_id="alice", note="needs attention")
        assert req.escalated is True
        assert req.escalated_at is not None
        assert req.escalation_note == "needs attention"

    def test_escalate_non_pending_raises(self, db):
        req = create_request(db, agent_id="a", title="t", action_payload={})
        resolve_request(db, req, approved=True, reviewer_id="x", note="")
        with pytest.raises(ValueError):
            escalate_request(db, req, reviewer_id="x")

    def test_cancel(self, db):
        req = create_request(db, agent_id="a", title="t", action_payload={})
        cancel_request(db, req)
        assert req.status == RequestStatus.CANCELLED
        assert req.resolved_by == "agent"

    def test_cancel_non_pending_raises(self, db):
        req = create_request(db, agent_id="a", title="t", action_payload={})
        resolve_request(db, req, approved=True, reviewer_id="x", note="")
        with pytest.raises(ValueError):
            cancel_request(db, req)


class TestFeedback:
    def test_feedback_success(self, db):
        _make_policy(db, name="standard", timeout_seconds=600)
        req = create_request(db, agent_id="agent", title="t", action_payload={})
        resolve_request(db, req, approved=True, reviewer_id="alice", note="ok")
        submit_feedback(db, req, Outcome.SUCCESS, note="worked", agent_id="agent")
        db.commit()
        assert req.outcome == Outcome.SUCCESS
        d = db.query(DecisionLog).filter_by(request_id=req.id).all()
        assert len(d) == 2
        fb = d[1]
        assert fb.source == DecisionSource.AGENT_FEEDBACK

    def test_feedback_before_decision_raises(self, db):
        req = create_request(db, agent_id="a", title="t", action_payload={})
        with pytest.raises(ValueError):
            submit_feedback(db, req, Outcome.SUCCESS)

    def test_feedback_invalid_outcome_raises(self, db):
        req = create_request(db, agent_id="a", title="t", action_payload={})
        with pytest.raises(ValueError):
            submit_feedback(db, req, "bogus")  # type: ignore[arg-type]


class TestTimeout:
    def _pending_with(self, db, on_timeout, timeout_seconds=600):
        _make_policy(db, name="pol", timeout_seconds=timeout_seconds, on_timeout=on_timeout)
        return create_request(db, agent_id="a", title="t", action_payload={"x": 1})

    def test_auto_approve(self, db):
        req = self._pending_with(db, TimeoutAction.AUTO_APPROVE)
        apply_timeout(db, req)
        assert req.status == RequestStatus.AUTO_APPROVED
        assert req.timeout_fired is True
        assert req.resolved_by == "policy"
        assert req.decision_payload == {"x": 1}

    def test_auto_reject(self, db):
        req = self._pending_with(db, TimeoutAction.AUTO_REJECT)
        apply_timeout(db, req)
        assert req.status == RequestStatus.AUTO_REJECTED
        assert req.decision_payload is None

    def test_escalate(self, db):
        req = self._pending_with(db, TimeoutAction.ESCALATE)
        apply_timeout(db, req)
        assert req.status == RequestStatus.PENDING
        assert req.escalated is True
        assert "timeout" in req.escalation_note.lower()

    def test_already_decided_noop(self, db):
        req = self._pending_with(db, TimeoutAction.AUTO_APPROVE)
        resolve_request(db, req, approved=True, reviewer_id="alice", note="human first")
        apply_timeout(db, req)
        assert req.status == RequestStatus.APPROVED  # human decision wins

    def test_timeout_fired_only_once(self, db):
        req = self._pending_with(db, TimeoutAction.AUTO_REJECT)
        apply_timeout(db, req)
        apply_timeout(db, req)
        db.commit()
        decisions = db.query(DecisionLog).filter_by(request_id=req.id).all()
        assert len(decisions) == 1


class TestFindPendingOverdue:
    def test_finds_only_overdue(self, db):
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        _make_policy(db, name="pol", timeout_seconds=600)
        fresh = create_request(db, agent_id="a", title="fresh", action_payload={})
        fresh.created_at = now
        old = create_request(db, agent_id="b", title="old", action_payload={})
        old.created_at = now - timedelta(seconds=1000)
        db.commit()

        overdue = find_pending_overdue(db, now=now)
        ids = {r.id for r in overdue}
        assert old.id in ids
        assert fresh.id not in ids

    def test_no_deadline_requests_never_overdue(self, db):
        req = ApprovalRequest(agent_id="a", title="no policy", action_payload={}, timeout_seconds=None)
        db.add(req)
        db.commit()
        assert find_pending_overdue(db) == []


class TestSeedPolicies:
    def test_idempotent(self, db):
        seed_policies(db)
        seed_policies(db)
        count = db.query(Policy).count()
        assert count == 4
