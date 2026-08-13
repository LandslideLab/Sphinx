"""Tests for the SLA timeout scheduler (sphinx.core.policy_engine)."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from sphinx.core import policy_engine
from sphinx.core.services import create_request
from sphinx.models import Policy, RequestStatus, TimeoutAction


@pytest.fixture(autouse=True)
def _engine_cleanup():
    yield
    policy_engine.stop()


def test_start_is_idempotent_and_stops():
    t1 = policy_engine.start()
    t2 = policy_engine.start()
    assert t1 is t2
    assert t1.is_alive()
    policy_engine.stop()
    assert not t1.is_alive()
    policy_engine.stop()  # double stop is safe


def test_engine_auto_approves_overdue(db):
    pol = Policy(
        name="short-approve",
        risk_levels=["medium"],
        timeout_seconds=2,
        on_timeout=TimeoutAction.AUTO_APPROVE,
    )
    db.add(pol)
    db.commit()

    req = create_request(db, agent_id="a", title="t", action_payload={"x": 1}, risk_level="medium")
    db.commit()
    # backdate so it is immediately overdue
    req.created_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    db.commit()

    policy_engine.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        db.expire_all()
        fresh = db.get(type(req), req.id)
        if fresh.status != RequestStatus.PENDING:
            break
        time.sleep(0.2)
    assert fresh.status == RequestStatus.AUTO_APPROVED
    assert fresh.decision_payload == {"x": 1}
    assert fresh.timeout_fired is True


def test_engine_escalates_overdue(db):
    pol = Policy(
        name="short-escalate",
        risk_levels=["high"],
        timeout_seconds=2,
        on_timeout=TimeoutAction.ESCALATE,
    )
    db.add(pol)
    db.commit()

    req = create_request(db, agent_id="a", title="t", action_payload={}, risk_level="high")
    db.commit()
    req.created_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    db.commit()

    policy_engine.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        db.expire_all()
        fresh = db.get(type(req), req.id)
        if fresh.escalated:
            break
        time.sleep(0.2)
    assert fresh.escalated is True
    assert fresh.status == RequestStatus.PENDING
