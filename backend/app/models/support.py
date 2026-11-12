from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin
from app.models.base import business_fk, enum_col, uuid_pk
from app.models.enums import (
    IssueCategory,
    MessageRole,
    NotificationType,
    TicketPriority,
    TicketStatus,
)
from app.models.tenancy import Customer, User


class SupportTicket(TimestampMixin, Base):
    __tablename__ = "support_tickets"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    ticket_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("orders.id", ondelete="SET NULL"), index=True)
    subject: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TicketStatus] = mapped_column(enum_col(TicketStatus), nullable=False, index=True)
    priority: Mapped[TicketPriority] = mapped_column(enum_col(TicketPriority), nullable=False, index=True)
    category: Mapped[IssueCategory | None] = mapped_column(enum_col(IssueCategory), index=True)
    ai_classification_confidence: Mapped[float | None] = mapped_column()
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    resolved_by: Mapped[str | None] = mapped_column(String(20))  # AI | HUMAN
    resolution_summary: Mapped[str | None] = mapped_column(Text)
    satisfaction_score: Mapped[int | None] = mapped_column(Integer)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopened_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    customer: Mapped[Customer] = relationship()
    assigned_to: Mapped[User | None] = relationship()
    events: Mapped[list["TicketEvent"]] = relationship(back_populates="ticket", order_by="TicketEvent.created_at")


class TicketEvent(TimestampMixin, Base):
    __tablename__ = "ticket_events"
    id: Mapped[uuid.UUID] = uuid_pk()
    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    event: Mapped[str] = mapped_column(String(60), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)

    ticket: Mapped[SupportTicket] = relationship(back_populates="events")


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="support")  # support | copilot
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("support_tickets.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="New conversation")
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", order_by="Message.created_at")


class Message(TimestampMixin, Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[MessageRole] = mapped_column(enum_col(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    agent_execution_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("agent_executions.id", ondelete="SET NULL"))
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)  # citations, actions, cards

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[NotificationType] = mapped_column(enum_col(NotificationType), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str | None] = mapped_column(String(300))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
