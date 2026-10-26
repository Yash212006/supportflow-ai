from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.connection import Base


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    refund_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="PENDING_APPROVAL", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    order = relationship("Order", back_populates="refunds")
    customer = relationship("Customer", back_populates="refunds")
    ticket = relationship("Ticket", back_populates="refunds")
