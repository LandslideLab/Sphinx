"""Seed default policies and realistic demo data for the console dashboard."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sphinx.db import SessionLocal, init_db
from sphinx.models import (
    ApprovalRequest,
    DecisionLog,
    DecisionSource,
    Outcome,
    Policy,
    RequestStatus,
    RiskLevel,
    TimeoutAction,
)

FRAMEWORKS = ["langgraph", "openai", "crewai", "generic"]
AGENTS = {
    "refund-agent": "Refund Ops Agent",
    "sre-oncall": "SRE Oncall Agent",
    "data-pipeline": "Data Pipeline Agent",
    "contract-review": "Contract Review Agent",
    "release-bot": "Release Bot",
}
TITLES = {
    "refund-agent": [
        ("Approve refund of $1,240 for order ORD-88231", "Customer requested refund after duplicate charge. Flags: medium trust."),
        ("Approve refund of $380 for order ORD-88114", "Self-serve refund under threshold, no escalation needed."),
        ("Deny refund of $4,900 for order ORD-88001", "Chargeback history flagged; high risk customer."),
    ],
    "sre-oncall": [
        ("Restart production database cluster (db-prod-3)", "Latency p99 > 5s for 20 minutes. Restart required."),
        ("Rollback deploy v2.14.3 to v2.14.2", "Error rate 3.8% after deploy, above SLO 1%."),
        ("Scale-out worker pool 12->20 nodes", "Queue depth at 8k, projected drain 4h."),
    ],
    "data-pipeline": [
        ("Delete PII rows from staging.warehouse.users", "GDPR erasure request ref GR-2210. 41 rows affected."),
        ("Backfill clickstream partitions for 2026-07", "Missing 6 partitions, ~1.2TB, window 2026-07-01..06."),
        ("Grant read access to analytics-readonly role", "New dashboard consumer onboarding."),
    ],
    "contract-review": [
        ("Sign NDA with Acme Corp (template v3)", "Standard template, no redlines."),
        ("Approve vendor renewal: DataHaven ($48k/yr)", "Renewal at +6% vs last year; finance approved."),
        ("Counter-offer: CloudFlare BGP ($112k)", "Negotiated 12% below list, CFO needs sign-off."),
    ],
    "release-bot": [
        ("Publish release v2.14.4 to production", "CVE-2026-3124 fix; staged + smoke-tested."),
        ("Promote canary 25% -> 100%", "Canary green 72h, error rate 0.2%."),
    ],
}


def _payload_for(title: str) -> dict:
    import re

    m = re.search(r"\$([\d,]+)", title)
    return {
        "action": title.split(" ")[0].lower(),
        "summary": title,
        "amount_usd": float(m.group(1).replace(",", "")) if m else None,
        "dry_run": True,
    }


def seed_policies(db) -> list[Policy]:
    if db.query(Policy).count() > 0:
        return db.query(Policy).all()
    default_policies = [
        Policy(
            name="standard-review",
            description="Default review queue for medium+ risk actions. Escalates on SLA timeout.",
            risk_levels=["medium", "high", "critical"],
            timeout_seconds=600,
            on_timeout=TimeoutAction.ESCALATE,
            auto_approve_below_risk=False,
            min_reviewers=1,
        ),
        Policy(
            name="low-risk-auto",
            description="Low-risk mechanical actions auto-approve instantly.",
            risk_levels=["low"],
            timeout_seconds=300,
            on_timeout=TimeoutAction.AUTO_APPROVE,
            auto_approve_below_risk=True,
            min_reviewers=1,
        ),
        Policy(
            name="high-risk-gate",
            description="High/critical risk requires human sign-off; rejects on timeout.",
            risk_levels=["high", "critical"],
            timeout_seconds=900,
            on_timeout=TimeoutAction.AUTO_REJECT,
            auto_approve_below_risk=False,
            min_reviewers=1,
        ),
        Policy(
            name="release-sla",
            description="Release/billing actions: 5 minute SLA, escalate to on-call on timeout.",
            risk_levels=["medium", "high"],
            timeout_seconds=300,
            on_timeout=TimeoutAction.ESCALATE,
            auto_approve_below_risk=False,
            min_reviewers=1,
        ),
    ]
    db.add_all(default_policies)
    db.commit()
    return default_policies


def seed_demo(db) -> None:
    if db.query(ApprovalRequest).count() > 0:
        return
    policies = seed_policies(db)
    by_name = {p.name: p for p in policies}
    random.seed(42)

    now = datetime.now(timezone.utc)
    reviewers = ["alice@landslide.io", "bob@landslide.io", "carol@landslide.io", "dave@landslide.io"]
    statuses: list[RequestStatus] = []
    for _ in range(28):
        r = random.random()
        if r < 0.18:
            statuses.append(RequestStatus.PENDING)
        elif r < 0.55:
            statuses.append(RequestStatus.APPROVED)
        elif r < 0.65:
            statuses.append(RequestStatus.REJECTED)
        elif r < 0.75:
            statuses.append(RequestStatus.AUTO_APPROVED)
        elif r < 0.82:
            statuses.append(RequestStatus.AUTO_REJECTED)
        elif r < 0.9:
            statuses.append(RequestStatus.CANCELLED)
        else:
            statuses.append(RequestStatus.PENDING)

    for i, status in enumerate(statuses):
        agent = random.choice(list(AGENTS))
        title, desc = random.choice(TITLES[agent])
        risk = random.choice([r for r in RiskLevel if r != RiskLevel.LOW])
        pol = random.choice([by_name["standard-review"], by_name["high-risk-gate"], by_name["release-sla"]])
        if status == RequestStatus.PENDING:
            created = now - timedelta(minutes=random.randint(0, 4))
        else:
            created = now - timedelta(minutes=random.randint(2, 60 * 26))
        req = ApprovalRequest(
            session_id=f"sess-{random.randint(1000, 9999)}",
            agent_id=agent,
            framework=random.choice(FRAMEWORKS),
            title=title,
            description=desc,
            action_payload=_payload_for(title),
            risk_level=risk,
            priority=random.choice([1, 1, 2, 3]),
            requester=random.choice(["agent", "scheduler", "oncall"]),
            policy_id=pol.id,
            policy_name=pol.name,
            timeout_seconds=pol.timeout_seconds,
            status=status,
            created_at=created,
            updated_at=created,
        )
        db.add(req)
        db.flush()

        if status == RequestStatus.PENDING:
            continue

        decided = created + timedelta(seconds=random.randint(30, max(61, pol.timeout_seconds - 60)))
        req.decided_at = decided
        req.updated_at = decided

        if status == RequestStatus.APPROVED:
            reviewer = random.choice(reviewers)
            req.reviewer_id = reviewer
            amend = random.random() < 0.3
            if amend:
                payload = dict(req.action_payload)
                amount = payload.get("amount_usd")
                if amount:
                    payload["amount_usd"] = round(amount * random.uniform(0.8, 1.2), 2)
                payload["approved_by_human"] = True
                req.decision_payload = payload
                req.reviewer_note = "Adjusted amount after review."
            else:
                req.decision_payload = req.action_payload
                req.reviewer_note = "Looks good."
            req.resolved_by = "human"
            from sphinx.core.delta import diff_dicts

            delta = diff_dicts(req.action_payload, req.decision_payload)
            db.add(
                DecisionLog(
                    request_id=req.id,
                    agent_decision=req.action_payload,
                    human_decision=req.decision_payload,
                    delta=delta or None,
                    agreement=not bool(delta),
                    source=DecisionSource.HUMAN_REVIEW,
                    reviewer_id=reviewer,
                    note=req.reviewer_note,
                    created_at=decided,
                )
            )
        elif status == RequestStatus.REJECTED:
            req.reviewer_id = random.choice(reviewers)
            req.reviewer_note = random.choice(
                ["Blocked: policy says no.", "Too risky, needs exec sign-off.", "Duplicate of ORD-88901, closing."]
            )
            req.resolved_by = "human"
            db.add(
                DecisionLog(
                    request_id=req.id,
                    agent_decision=req.action_payload,
                    human_decision=None,
                    delta=None,
                    agreement=False,
                    source=DecisionSource.HUMAN_REVIEW,
                    reviewer_id=req.reviewer_id,
                    note=req.reviewer_note,
                    created_at=decided,
                )
            )
        elif status in (RequestStatus.AUTO_APPROVED, RequestStatus.AUTO_REJECTED):
            approved = status == RequestStatus.AUTO_APPROVED
            req.resolved_by = "policy"
            req.decision_payload = req.action_payload if approved else None
            db.add(
                DecisionLog(
                    request_id=req.id,
                    agent_decision=req.action_payload,
                    human_decision=req.action_payload if approved else None,
                    delta=None,
                    agreement=None,
                    source=DecisionSource.POLICY_TIMEOUT,
                    reviewer_id="policy",
                    note="SLA timeout exceeded; policy auto-decision.",
                    created_at=decided,
                )
            )
        elif status == RequestStatus.CANCELLED:
            req.resolved_by = "agent"

        # feedback loop for a subset of decided requests
        if status in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED) and random.random() < 0.6:
            outcome = random.choices(
                [Outcome.SUCCESS, Outcome.FAILURE, Outcome.PARTIAL], weights=[0.72, 0.18, 0.10]
            )[0]
            req.outcome = outcome
            req.outcome_note = "Executed without incident." if outcome == Outcome.SUCCESS else "Customer still dissatisfied; follow-up required."
            db.add(
                DecisionLog(
                    request_id=req.id,
                    agent_decision=req.action_payload,
                    human_decision=req.decision_payload,
                    delta=None,
                    agreement=None,
                    source=DecisionSource.AGENT_FEEDBACK,
                    reviewer_id=req.agent_id,
                    note=f"[feedback outcome={outcome.value}] {req.outcome_note}",
                    created_at=now - timedelta(minutes=random.randint(1, 60)),
                )
            )

    db.commit()


def seed_capture(db) -> None:
    """Seed one realistic capture chain so the capture trail is populated."""
    from sphinx.core import capture_service
    from sphinx.models import CaptureEvent

    if db.query(CaptureEvent).count() > 0:
        return
    signing_key = capture_service.get_signing_key(db)
    agent = "refund-agent"
    session = "sess-capture-8801"
    events = [
        {
            "event_type": "llm_inference",
            "event_name": "classify_intent",
            "input_payload": {"messages": [{"role": "user", "content": "Customer ORD-88231 wants a refund."}]},
            "output_payload": {"intent": "refund_request", "confidence": 0.94, "model": "gpt-4.1"},
            "metadata": {"model": "gpt-4.1", "tokens_in": 312, "tokens_out": 48, "duration_ms": 620},
        },
        {
            "event_type": "tool_call",
            "event_name": "lookup_order",
            "input_payload": {"order_id": "ORD-88231"},
            "output_payload": {"order": {"id": "ORD-88231", "amount_usd": 1240.0, "status": "delivered"}},
            "metadata": {"tool": "order_db", "duration_ms": 41},
        },
        {
            "event_type": "llm_inference",
            "event_name": "assess_risk",
            "input_payload": {"order": {"id": "ORD-88231", "amount_usd": 1240.0}, "customer": {"trust": "medium"}},
            "output_payload": {"risk_level": "medium", "reason": "duplicate charge history"},
            "metadata": {"model": "gpt-4.1", "tokens_in": 540, "tokens_out": 32, "duration_ms": 510},
        },
        {
            "event_type": "state_change",
            "event_name": "request_created",
            "input_payload": {"ref": None},
            "output_payload": {"ref": "SPH-E126A0", "status": "pending"},
            "metadata": {"reason": "risk_level=medium requires review"},
        },
        {
            "event_type": "tool_call",
            "event_name": "request_approval",
            "input_payload": {"action": "refund", "order_id": "ORD-88231", "amount_usd": 1240.0},
            "output_payload": {"accepted": True, "ticket": "SPH-E126A0"},
            "metadata": {"tool": "sphinx_control_plane", "duration_ms": 88},
        },
    ]
    capture_service.ingest_batch(
        db,
        signing_key=signing_key,
        agent_id=agent,
        session_id=session,
        events=events,
    )


def main() -> None:
    init_db()
    with SessionLocal() as db:
        seed_policies(db)
        seed_demo(db)
        seed_capture(db)
    print("Seeded sphinx demo data.")


if __name__ == "__main__":
    main()
