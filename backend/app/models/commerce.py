from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin
from app.models.base import business_fk, enum_col, uuid_pk
from app.models.enums import (
    OrderStatus,
    PaymentSource,
    PaymentStatus,
    RefundStatus,
    ShipmentStatus,
)
from app.models.tenancy import Customer

Money = Numeric(12, 2)


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    sku: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500))
    refundable_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    __table_args__ = (
        UniqueConstraint("business_id", "sku", name="uq_products_business_sku"),
        CheckConstraint("price >= 0", name="price_non_negative"),
    )


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("business_id", "order_number", name="uq_orders_business_number"),
        CheckConstraint("total_amount >= 0", name="total_non_negative"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    order_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[OrderStatus] = mapped_column(enum_col(OrderStatus), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    is_sample: Mapped[bool] = mapped_column(default=False, nullable=False)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    customer: Mapped[Customer] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    shipments: Mapped[list["Shipment"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Money, nullable=False)

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class Shipment(TimestampMixin, Base):
    __tablename__ = "shipments"
    id: Mapped[uuid.UUID] = uuid_pk()
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    carrier: Mapped[str] = mapped_column(String(80), nullable=False)
    tracking_number: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[ShipmentStatus] = mapped_column(enum_col(ShipmentStatus), nullable=False)
    estimated_delivery: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event: Mapped[str | None] = mapped_column(String(300))

    order: Mapped[Order] = relationship(back_populates="shipments")


class Payment(TimestampMixin, Base):
    """A payment attempt for an order. For PAYPAL_SANDBOX rows every status comes from a PayPal
    API response or a verified webhook, never from an agent's say-so."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("order_id", "attempt", name="uq_payments_order_attempt"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("refunded_amount >= 0 AND refunded_amount <= amount", name="refunded_within_amount"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    source: Mapped[PaymentSource] = mapped_column(enum_col(PaymentSource), nullable=False)
    method: Mapped[str] = mapped_column(String(40), default="paypal", nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(enum_col(PaymentStatus), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    refunded_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    paypal_order_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    paypal_capture_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    approve_url: Mapped[str | None] = mapped_column(String(500))
    payer_email: Mapped[str | None] = mapped_column(String(255))
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    capture_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    order: Mapped[Order] = relationship(back_populates="payments")
    customer: Mapped[Customer] = relationship()
    refunds: Mapped[list["Refund"]] = relationship(back_populates="payment")

    @property
    def refundable_amount(self) -> Decimal:
        return (self.amount - self.refunded_amount).quantize(Decimal("0.01"))


class PayPalTransaction(Base):
    """Append-only log of every PayPal API exchange (sanitised: no tokens, no secrets)."""

    __tablename__ = "paypal_transactions"
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    payment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("payments.id", ondelete="SET NULL"), index=True)
    refund_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("refunds.id", ondelete="SET NULL"), index=True)
    operation: Mapped[str] = mapped_column(String(60), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(100))
    http_status: Mapped[int | None] = mapped_column(Integer)
    paypal_debug_id: Mapped[str | None] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(64), index=True)
    resource_status: Mapped[str | None] = mapped_column(String(40))
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)  # success | rejected | unknown | not_sent
    response_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class Refund(TimestampMixin, Base):
    __tablename__ = "refunds"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    payment_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False, index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("support_tickets.id", ondelete="SET NULL"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[RefundStatus] = mapped_column(enum_col(RefundStatus), nullable=False, index=True)
    is_sample: Mapped[bool] = mapped_column(default=False, nullable=False)
    paypal_refund_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    paypal_status: Mapped[str | None] = mapped_column(String(40))
    paypal_status_reason: Mapped[str | None] = mapped_column(String(200))
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    policy_decision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("policy_decisions.id", ondelete="SET NULL"))
    execution_action_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("execution_actions.id", ondelete="SET NULL"))
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    payment: Mapped[Payment] = relationship(back_populates="refunds")
    order: Mapped[Order] = relationship()
    customer: Mapped[Customer] = relationship()
