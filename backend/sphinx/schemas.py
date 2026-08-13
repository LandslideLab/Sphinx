from datetime import datetime

from pydantic import BaseModel, Field


class RequestCreate(BaseModel):
    agent_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    action_payload: dict
    description: str = ""
    session_id: str = ""
    framework: str = "generic"
    risk_level: str = "medium"
    priority: int = Field(default=1, ge=0, le=5)
    policy_id: str | None = None
    requester: str = "agent"
    metadata: dict | None = None


class DecideRequest(BaseModel):
    note: str = ""
    reviewer_id: str = "console"
    decision_payload: dict | None = None
    amend: bool = False


class EscalateRequest(BaseModel):
    note: str = ""
    reviewer_id: str = "console"


class FeedbackRequest(BaseModel):
    outcome: str = Field(pattern="^(success|failure|partial)$")
    note: str = ""
    agent_id: str = ""


class PolicyCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    risk_levels: list[str] = ["medium", "high", "critical"]
    timeout_seconds: int = Field(default=3600, ge=1)
    on_timeout: str = Field(default="escalate", pattern="^(auto_approve|auto_reject|escalate)$")
    auto_approve_below_risk: bool = True
    min_reviewers: int = Field(default=1, ge=1, le=10)
    enabled: bool = True


class PolicyUpdate(BaseModel):
    description: str | None = None
    risk_levels: list[str] | None = None
    timeout_seconds: int | None = Field(default=None, ge=1)
    on_timeout: str | None = Field(default=None, pattern="^(auto_approve|auto_reject|escalate)$")
    auto_approve_below_risk: bool | None = None
    min_reviewers: int | None = Field(default=None, ge=1, le=10)
    enabled: bool | None = None


class RequestListParams(BaseModel):
    status: str | None = None
    framework: str | None = None
    agent_id: str | None = None
    escalated: bool | None = None
    q: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
