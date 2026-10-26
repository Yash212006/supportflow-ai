from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.connection import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticket_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    subject: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(32), default="MEDIUM", index=True)
    status: Mapped[str] = mapped_column(String(32), default="OPEN", index=True)
    category: Mapped[str] = mapped_column(String(64), default="GENERAL", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    assigned_to: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    investigation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    customer = relationship("Customer", back_populates="tickets")
    order = relationship("Order", back_populates="tickets")
    refunds = relationship("Refund", back_populates="ticket")
    audit_logs = relationship("AuditLog", back_populates="ticket")
    pending_actions = relationship("PendingAction", back_populates="ticket")
