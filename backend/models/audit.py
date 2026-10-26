from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.connection import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    action_id: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(64), index=True)
    requested_by: Mapped[str] = mapped_column(String(120), default="support_agent")
    agent_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parameters: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_status: Mapped[str] = mapped_column(String(32), default="N/A")
    executed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ticket = relationship("Ticket", back_populates="audit_logs")


class PendingAction(Base):
    __tablename__ = "pending_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    action_id: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    refund_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action_type: Mapped[str] = mapped_column(String(64), index=True)
    requested_by: Mapped[str] = mapped_column(String(120), default="support_agent")
    agent_reason: Mapped[str] = mapped_column(Text)
    policy_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING_APPROVAL", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    ticket = relationship("Ticket", back_populates="pending_actions")
    customer = relationship("Customer")
    order = relationship("Order")
