"""Policies, decisions, approvals, agent executions and controlled actions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin
from app.models.base import business_fk, enum_col, uuid_pk
from app.models.enums import (
    ActionState,
    ActionType,
    ApprovalStatus,
    DecisionOutcome,
    ExecutionStatus,
    RiskLevel,
)
from app.models.tenancy import User


class BusinessPolicy(TimestampMixin, Base):
    __tablename__ = "business_policies"
    __table_args__ = (UniqueConstraint("business_id", "key", name="uq_policies_business_key"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    action_type: Mapped[ActionType] = mapped_column(enum_col(ActionType), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    versions: Mapped[list["PolicyVersion"]] = relationship(back_populates="policy", order_by="PolicyVersion.version")


class PolicyVersion(TimestampMixin, Base):
    """Immutable once created. Rules are a JSON list evaluated by app.policies.engine."""

    __tablename__ = "policy_versions"
    __table_args__ = (UniqueConstraint("policy_id", "version", name="uq_policy_versions_policy_version"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("business_policies.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    rules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    default_outcome: Mapped[DecisionOutcome] = mapped_column(enum_col(DecisionOutcome), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_note: Mapped[str | None] = mapped_column(String(500))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))

    policy: Mapped[BusinessPolicy] = relationship(back_populates="versions")


class PolicyDecision(TimestampMixin, Base):
    __tablename__ = "policy_decisions"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    policy_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("business_policies.id", ondelete="SET NULL"), index=True)
    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("policy_versions.id", ondelete="SET NULL"))
    policy_version: Mapped[int | None] = mapped_column(Integer)
    action_type: Mapped[ActionType] = mapped_column(enum_col(ActionType), nullable=False)
    outcome: Mapped[DecisionOutcome] = mapped_column(enum_col(DecisionOutcome), nullable=False, index=True)
    matched_rule_id: Mapped[str | None] = mapped_column(String(80))
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evaluated_conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("orders.id", ondelete="SET NULL"), index=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("payments.id", ondelete="SET NULL"), index=True)
    agent_execution_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("agent_executions.id", ondelete="SET NULL"), index=True)
    risk_level: Mapped[RiskLevel | None] = mapped_column(enum_col(RiskLevel))
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AgentExecution(TimestampMixin, Base):
    __tablename__ = "agent_executions"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    workflow: Mapped[str] = mapped_column(String(60), nullable=False, index=True)  # support | copilot | dashboard
    status: Mapped[ExecutionStatus] = mapped_column(enum_col(ExecutionStatus), nullable=False, index=True)
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), index=True)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("support_tickets.id", ondelete="SET NULL"), index=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("orders.id", ondelete="SET NULL"), index=True)
    intent: Mapped[str | None] = mapped_column(String(40))
    llm_mode: Mapped[str] = mapped_column(String(30), nullable=False)  # e.g. openai:gpt-4o-mini | deterministic
    input_summary: Mapped[str | None] = mapped_column(Text)
    outcome_summary: Mapped[str | None] = mapped_column(Text)
    decision_outcome: Mapped[DecisionOutcome | None] = mapped_column(enum_col(DecisionOutcome))
    resolved_autonomously: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    required_human: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)  # safe trace, no CoT
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    tool_calls: Mapped[list["AgentToolCall"]] = relationship(back_populates="execution", order_by="AgentToolCall.created_at")


class AgentToolCall(TimestampMixin, Base):
    __tablename__ = "agent_tool_calls"
    id: Mapped[uuid.UUID] = uuid_pk()
    execution_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("agent_executions.id", ondelete="CASCADE"), nullable=False, index=True)
    agent: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    tool: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_summary: Mapped[str | None] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    authorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    execution: Mapped[AgentExecution] = relationship(back_populates="tool_calls")


class ExecutionAction(TimestampMixin, Base):
    """A controlled business/financial action driven by the state machine in app.workflows.execution_engine."""

    __tablename__ = "execution_actions"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    action_type: Mapped[ActionType] = mapped_column(enum_col(ActionType), nullable=False, index=True)
    state: Mapped[ActionState] = mapped_column(enum_col(ActionState), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(120), nullable=False)  # agent:<name> | user:<id>
    policy_decision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("policy_decisions.id", ondelete="SET NULL"))
    agent_execution_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("agent_executions.id", ondelete="SET NULL"), index=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("orders.id", ondelete="SET NULL"), index=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("payments.id", ondelete="SET NULL"), index=True)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("support_tickets.id", ondelete="SET NULL"), index=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ApprovalRequest(TimestampMixin, Base):
    __tablename__ = "approval_requests"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    execution_action_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("execution_actions.id", ondelete="CASCADE"), nullable=False, unique=True)
    policy_decision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("policy_decisions.id", ondelete="SET NULL"))
    status: Mapped[ApprovalStatus] = mapped_column(enum_col(ApprovalStatus), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_by: Mapped[str] = mapped_column(String(120), nullable=False)
    risk_level: Mapped[RiskLevel | None] = mapped_column(enum_col(RiskLevel))
    risk_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manager_note: Mapped[str | None] = mapped_column(Text)
    final_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    action: Mapped[ExecutionAction] = relationship()
    decided_by: Mapped[User | None] = relationship()
    decision: Mapped[PolicyDecision | None] = relationship()
    approval_actions: Mapped[list["ApprovalAction"]] = relationship(back_populates="approval", order_by="ApprovalAction.created_at")


class ApprovalAction(TimestampMixin, Base):
    __tablename__ = "approval_actions"
    id: Mapped[uuid.UUID] = uuid_pk()
    approval_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # APPROVE | REJECT
    note: Mapped[str | None] = mapped_column(Text)
    revalidation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    approval: Mapped[ApprovalRequest] = relationship(back_populates="approval_actions")
    user: Mapped[User] = relationship()
