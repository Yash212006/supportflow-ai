from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.connection import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    order_date: Mapped[date] = mapped_column(Date)
    expected_delivery: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_delivery: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[float] = mapped_column(Float)
    payment_status: Mapped[str] = mapped_column(String(32), default="PAID")
    shipping_address: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    product_name: Mapped[str] = mapped_column(String(160), default="SupportFlow Item")

    customer = relationship("Customer", back_populates="orders")
    tickets = relationship("Ticket", back_populates="order")
    refunds = relationship("Refund", back_populates="order")
