import enum
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sphinx.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_ref() -> str:
    return f"SPH-{secrets.token_hex(3).upper()}"


class RequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    AUTO_APPROVED = "auto_approved"
    AUTO_REJECTED = "auto_rejected"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TimeoutAction(str, enum.Enum):
    AUTO_APPROVE = "auto_approve"
    AUTO_REJECT = "auto_reject"
    ESCALATE = "escalate"


class DecisionSource(str, enum.Enum):
    HUMAN_REVIEW = "human_review"
    POLICY_TIMEOUT = "policy_timeout"
    AUTO_POLICY = "auto_policy"
    AGENT_FEEDBACK = "agent_feedback"


class Outcome(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ref: Mapped[str] = mapped_column(String(16), unique=True, index=True, default=new_ref)
    session_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    framework: Mapped[str] = mapped_column(String(64), index=True, default="generic")
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text, default="")
    action_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), default=RiskLevel.MEDIUM)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus), default=RequestStatus.PENDING, index=True
    )
    requester: Mapped[str] = mapped_column(String(128), default="agent")
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    policy_id: Mapped[str | None] = mapped_column(ForeignKey("policies.id"), nullable=True)
    policy_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    escalation_note: Mapped[str] = mapped_column(Text, default="")
    timeout_fired: Mapped[bool] = mapped_column(Boolean, default=False)

    reviewer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewer_note: Mapped[str] = mapped_column(Text, default="")
    decision_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(32), nullable=True)

    outcome: Mapped[Outcome | None] = mapped_column(Enum(Outcome), nullable=True)
    outcome_note: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    decisions: Mapped[list["DecisionLog"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )

    @property
    def seconds_pending(self) -> float:
        if not self.created_at:
            return 0.0

        def _utc(dt: datetime) -> datetime:
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

        anchor = self.decided_at or utcnow()
        return max(0.0, (_utc(anchor) - _utc(self.created_at)).total_seconds())

    @property
    def deadline(self) -> datetime | None:
        if self.status != RequestStatus.PENDING or not self.timeout_seconds or not self.created_at:
            return None
        created = self.created_at.replace(tzinfo=timezone.utc) if self.created_at.tzinfo is None else self.created_at
        return created + timedelta(seconds=self.timeout_seconds)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ref": self.ref,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "framework": self.framework,
            "title": self.title,
            "description": self.description,
            "action_payload": self.action_payload,
            "risk_level": self.risk_level.value,
            "priority": self.priority,
            "status": self.status.value,
            "requester": self.requester,
            "metadata": self.metadata_,
            "policy_id": self.policy_id,
            "policy_name": self.policy_name,
            "timeout_seconds": self.timeout_seconds,
            "escalated": self.escalated,
            "escalated_at": self.escalated_at.isoformat() if self.escalated_at else None,
            "escalation_note": self.escalation_note,
            "reviewer_id": self.reviewer_id,
            "reviewer_note": self.reviewer_note,
            "decision_payload": self.decision_payload,
            "resolved_by": self.resolved_by,
            "outcome": self.outcome.value if self.outcome else None,
            "outcome_note": self.outcome_note,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "seconds_pending": round(self.seconds_pending, 1),
        }


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    risk_levels: Mapped[list] = mapped_column(JSON, default=list)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    on_timeout: Mapped[TimeoutAction] = mapped_column(Enum(TimeoutAction), default=TimeoutAction.ESCALATE)
    auto_approve_below_risk: Mapped[bool] = mapped_column(Boolean, default=True)
    min_reviewers: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "risk_levels": self.risk_levels,
            "timeout_seconds": self.timeout_seconds,
            "on_timeout": self.on_timeout.value,
            "auto_approve_below_risk": self.auto_approve_below_risk,
            "min_reviewers": self.min_reviewers,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class DecisionLog(Base):
    __tablename__ = "decision_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    request_id: Mapped[str] = mapped_column(ForeignKey("approval_requests.id"), index=True)
    request: Mapped[ApprovalRequest] = relationship(back_populates="decisions")

    agent_decision: Mapped[dict] = mapped_column(JSON, default=dict)
    human_decision: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    delta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    agreement: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    source: Mapped[DecisionSource] = mapped_column(
        Enum(DecisionSource), default=DecisionSource.HUMAN_REVIEW
    )
    reviewer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "request_id": self.request_id,
            "request_ref": self.request.ref if self.request else None,
            "agent_decision": self.agent_decision,
            "human_decision": self.human_decision,
            "delta": self.delta,
            "agreement": self.agreement,
            "source": self.source.value,
            "reviewer_id": self.reviewer_id,
            "note": self.note,
            "created_at": self.created_at.isoformat(),
        }
