"""Deterministic fact builder and risk assessment, computed from database records only.

These facts feed the policy engine. Nothing here comes from an LLM.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models import Order, Payment, Refund, Shipment
from app.models.enums import OrderStatus, PaymentStatus, RefundStatus, RiskLevel

ACTIVE_REFUND_STATES = (RefundStatus.PENDING, RefundStatus.COMPLETED, RefundStatus.OUTCOME_UNKNOWN)
OPEN_REFUND_STATES = (RefundStatus.REQUESTED, RefundStatus.AWAITING_APPROVAL, RefundStatus.PENDING, RefundStatus.OUTCOME_UNKNOWN)


@dataclass
class RiskSignal:
    code: str
    description: str
    weight: int
    critical: bool = False


@dataclass
class RiskAssessment:
    level: RiskLevel
    score: int
    signals: list[RiskSignal] = field(default_factory=list)
    recommended_next_step: str = ""
    requires_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "score": self.score,
            "signals": [s.__dict__ for s in self.signals],
            "recommended_next_step": self.recommended_next_step,
            "requires_review": self.requires_review,
        }


def assess_refund_risk(db: Session, *, order: Order, payment: Payment | None, amount: Decimal | None) -> RiskAssessment:
    now = utcnow()
    signals: list[RiskSignal] = []
    cust = order.customer_id
    req_7d = db.scalar(select(func.count(Refund.id)).where(Refund.customer_id == cust, Refund.created_at >= now - timedelta(days=7))) or 0
    refunds_90d = db.scalar(
        select(func.count(Refund.id)).where(Refund.customer_id == cust, Refund.created_at >= now - timedelta(days=90), Refund.status.in_(ACTIVE_REFUND_STATES))
    ) or 0
    if req_7d >= 3:
        signals.append(RiskSignal("REPEATED_REQUESTS", f"{req_7d} refund requests in the last 7 days", 35, critical=True))
    elif req_7d >= 2:
        signals.append(RiskSignal("MULTIPLE_REQUESTS", f"{req_7d} refund requests in the last 7 days", 15))
    if refunds_90d >= 3:
        signals.append(RiskSignal("FREQUENT_REFUNDS", f"{refunds_90d} refunds issued in the last 90 days", 25))
    if payment is not None:
        same_capture = db.scalar(select(func.count(Refund.id)).where(Refund.payment_id == payment.id, Refund.status.in_(OPEN_REFUND_STATES + (RefundStatus.COMPLETED,)))) or 0
        if same_capture >= 1:
            signals.append(RiskSignal("MULTIPLE_REFUNDS_SAME_CAPTURE", f"{same_capture} existing refund(s) on this payment", 20))
        if amount is not None and amount > payment.refundable_amount:
            signals.append(RiskSignal("EXCEEDS_REFUNDABLE", f"Requested {amount} exceeds refundable {payment.refundable_amount}", 50, critical=True))
        failed = db.scalar(
            select(func.count(Payment.id)).where(Payment.customer_id == cust, Payment.status.in_((PaymentStatus.FAILED, PaymentStatus.DECLINED)), Payment.created_at >= now - timedelta(days=30))
        ) or 0
        if failed >= 2:
            signals.append(RiskSignal("REPEATED_FAILED_PAYMENTS", f"{failed} failed payments in 30 days", 15))
    if amount is not None and order.total_amount > 0 and amount / order.total_amount > Decimal("1.0"):
        signals.append(RiskSignal("AMOUNT_ABOVE_ORDER", "Refund amount exceeds order total", 50, critical=True))
    conflict = detect_conflict(order, payment)
    if conflict:
        signals.append(RiskSignal("INCONSISTENT_STATE", conflict, 40, critical=True))
    high_value_threshold = Decimal("5000") if order.currency == "INR" else Decimal("500")
    if amount is not None and amount >= high_value_threshold:
        signals.append(RiskSignal("HIGH_VALUE", f"High-value refund ({order.currency} {amount})", 20))

    score = min(100, sum(s.weight for s in signals))
    critical = any(s.critical for s in signals)
    level = RiskLevel.HIGH if critical or score >= 50 else RiskLevel.MEDIUM if score >= 20 else RiskLevel.LOW
    step = {
        RiskLevel.HIGH: "Manual review by a manager before any financial action.",
        RiskLevel.MEDIUM: "Proceed per policy; monitor customer activity.",
        RiskLevel.LOW: "No risk indicators; proceed per policy.",
    }[level]
    return RiskAssessment(level=level, score=score, signals=signals, recommended_next_step=step, requires_review=level == RiskLevel.HIGH)


def detect_conflict(order: Order, payment: Payment | None) -> str | None:
    if payment is None:
        return None
    if order.status in (OrderStatus.REFUNDED,) and payment.status == PaymentStatus.CAPTURED:
        return "Order marked refunded but payment still fully captured"
    if payment.status in (PaymentStatus.REFUNDED,) and payment.refunded_amount < payment.amount:
        return "Payment marked refunded but refunded amount is below captured amount"
    if payment.amount != order.total_amount and payment.status == PaymentStatus.CAPTURED and payment.refunded_amount == 0:
        return f"Captured amount {payment.amount} differs from order total {order.total_amount}"
    return None


def latest_payment(db: Session, order_id: uuid.UUID) -> Payment | None:
    return db.scalars(
        select(Payment)
        .where(Payment.order_id == order_id, Payment.status.in_((PaymentStatus.CAPTURED, PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED)))
        .order_by(Payment.attempt.desc())
    ).first() or db.scalars(select(Payment).where(Payment.order_id == order_id).order_by(Payment.attempt.desc())).first()


def refund_facts(db: Session, *, order: Order, payment: Payment | None, amount: Decimal | None, risk: RiskAssessment) -> dict[str, Any]:
    now = utcnow()
    shipment = db.scalars(select(Shipment).where(Shipment.order_id == order.id).order_by(Shipment.created_at.desc())).first()
    refund_window = 30
    if order.items:
        refund_window = min(i.product.refundable_days for i in order.items)
    delivered = order.delivered_at
    days_since_order = (now - order.placed_at).days
    days_since_delivery = (now - delivered).days if delivered else None
    reference_days = days_since_delivery if days_since_delivery is not None else days_since_order
    prior_on_payment = False
    if payment is not None:
        prior_on_payment = bool(
            db.scalar(select(func.count(Refund.id)).where(Refund.payment_id == payment.id, Refund.status.in_(ACTIVE_REFUND_STATES)))
        )
    return {
        "refund_amount": amount,
        "order_total": order.total_amount,
        "refund_ratio": (amount / order.total_amount).quantize(Decimal("0.0001")) if amount is not None and order.total_amount else None,
        "refundable_amount": payment.refundable_amount if payment else Decimal("0"),
        "exceeds_refundable": bool(payment is not None and amount is not None and amount > payment.refundable_amount),
        "payment_status": payment.status.value if payment else None,
        "payment_captured": bool(payment and payment.status in (PaymentStatus.CAPTURED, PaymentStatus.PARTIALLY_REFUNDED)),
        "payment_source": payment.source.value if payment else None,
        "order_status": order.status.value,
        "prior_refund_on_payment": prior_on_payment,
        "customer_refunds_90d": db.scalar(
            select(func.count(Refund.id)).where(
                Refund.customer_id == order.customer_id, Refund.created_at >= now - timedelta(days=90), Refund.status.in_(ACTIVE_REFUND_STATES)
            )
        )
        or 0,
        "customer_refund_requests_7d": db.scalar(
            select(func.count(Refund.id)).where(Refund.customer_id == order.customer_id, Refund.created_at >= now - timedelta(days=7))
        )
        or 0,
        "days_since_order": days_since_order,
        "days_since_delivery": days_since_delivery,
        "within_refund_window": reference_days <= refund_window,
        "risk_level": risk.level.value,
        "risk_score": risk.score,
        "conflicting_state": detect_conflict(order, payment) is not None,
        "shipment_status": shipment.status.value if shipment else None,
    }
