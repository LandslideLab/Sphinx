"""Seed data tests: demo data should produce realistic governance metrics."""
from __future__ import annotations

from sphinx.core.metrics import compute_metrics
from sphinx.models import ApprovalRequest, RequestStatus
from sphinx.seed import seed_demo, seed_policies


class TestSeed:
    def test_seed_policies_creates_four(self, db):
        seed_policies(db)
        assert db.query(ApprovalRequest).count() == 0
        names = {p.name for p in seed_policies(db)}
        assert {"standard-review", "low-risk-auto", "high-risk-gate", "release-sla"} == names

    def test_seed_demo_produces_requests_and_decisions(self, db):
        seed_demo(db)
        total = db.query(ApprovalRequest).count()
        assert total == 28
        pending = db.query(ApprovalRequest).filter(ApprovalRequest.status == RequestStatus.PENDING).count()
        assert 0 < pending < total

    def test_seed_demo_is_idempotent(self, db):
        seed_demo(db)
        seed_demo(db)
        assert db.query(ApprovalRequest).count() == 28

    def test_seed_demo_metrics_are_plausible(self, db):
        seed_demo(db)
        m = compute_metrics(db)
        assert m["totals"]["requests"] == 28
        g = m["governance"]
        for key in ("escalation_rate", "timeout_rate", "correction_rate", "reviewer_agreement", "error_escape_rate", "sla_compliance_rate"):
            assert 0.0 <= g[key] <= 100.0, key
        assert m["latency"]["human_reviews"] > 0
        assert m["latency"]["avg_seconds"] > 0
        # pending count matches the seed distribution (approx 18-25% pending)
        assert m["totals"]["pending"] >= 1

    def test_seed_demo_agents_and_frameworks(self, db):
        seed_demo(db)
        frameworks = {r.framework for r in db.query(ApprovalRequest).all()}
        assert frameworks <= {"langgraph", "openai", "crewai", "generic"}
        assert len(frameworks) > 1
