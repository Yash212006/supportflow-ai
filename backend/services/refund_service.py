from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.customer import Customer
from backend.models.order import Order
from backend.models.refund import Refund
from backend.models.ticket import Ticket
from backend.rules.business_rules import get_business_rules
from backend.services.order_service import delay_days

ACTIVE_REFUND_STATUSES = {"PENDING_APPROVAL", "APPROVED", "PROCESSED"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def next_refund_id(db: Session) -> str:
    max_id = db.scalar(select(func.max(Refund.id))) or 0
    candidate = 2000 + max_id + 1
    while db.scalar(select(Refund.id).where(Refund.refund_id == f"RFD{candidate}")):
        candidate += 1
    return f"RFD{candidate}"


def get_refund_by_id_str(db: Session, refund_id: str) -> Refund | None:
    return db.scalar(select(Refund).where(Refund.refund_id == refund_id))


def list_refunds(
    db: Session,
    customer_id: int | None = None,
    order_id: int | None = None,
    status: str | None = None,
    limit: int = 300,
) -> list[Refund]:
    stmt = select(Refund).order_by(Refund.id.desc())
    if customer_id:
        stmt = stmt.where(Refund.customer_id == customer_id)
    if order_id:
        stmt = stmt.where(Refund.order_id == order_id)
    if status:
        stmt = stmt.where(Refund.status == status)
    return list(db.scalars(stmt.limit(limit)))


def has_duplicate_refund(db: Session, order_id: int) -> bool:
    existing = db.scalar(
        select(Refund).where(
            Refund.order_id == order_id,
            Refund.status.in_(ACTIVE_REFUND_STATUSES),
        )
    )
    return existing is not None


def evaluate_refund_eligibility(db: Session, order: Order) -> dict:
    rules = get_business_rules()
    delay = delay_days(order)
    duplicate = has_duplicate_refund(db, order.id)
    high_value = order.amount >= rules.high_value_threshold
    above_auto = order.amount > rules.auto_refund_limit

    eligible = False
    reasons: list[str] = []
    blockers: list[str] = []

    is_already_refunded = (
        order.status == "REFUNDED"
        or order.payment_status == "REFUNDED"
        or any(r.status in {"APPROVED", "PROCESSED"} for r in (order.refunds or []))
    )

    if is_already_refunded:
        blockers.append("Order has already been refunded.")
    elif order.status == "CANCELLED":
        blockers.append("Order is cancelled.")
    elif order.payment_status not in {"PAID", "CAPTURED"}:
        blockers.append(f"Payment status is {order.payment_status}.")
    elif duplicate and rules.duplicate_refund_block:
        blockers.append("An active or pending refund already exists for this order.")
    elif delay is None:
        blockers.append("Delivery delay cannot be determined from available data.")
    elif delay >= rules.delivery_delay_refund_days:
        eligible = True
        reasons.append(
            f"Order is delayed by {delay} day(s); policy threshold is "
            f"{rules.delivery_delay_refund_days} day(s)."
        )
    elif order.status == "DELIVERED" and delay >= rules.delivery_delay_refund_days:
        eligible = True
        reasons.append("Delivered late beyond the refund delay threshold.")
    else:
        blockers.append(
            f"Delay of {delay} day(s) is below the {rules.delivery_delay_refund_days}-day threshold."
        )

    if high_value:
        blockers.append(
            f"Order amount ₹{order.amount:,.0f} exceeds the high-value threshold "
            f"₹{rules.high_value_threshold:,.0f} and must be escalated."
        )
        eligible = False

    return {
        "eligible": eligible and not blockers,
        "requires_escalation": high_value or (eligible and above_auto and order.amount > rules.auto_refund_limit),
        "requires_human_approval": True,
        "high_value": high_value,
        "above_auto_limit": above_auto,
        "delay_days": delay,
        "threshold_days": rules.delivery_delay_refund_days,
        "auto_refund_limit": rules.auto_refund_limit,
        "amount": order.amount,
        "reasons": reasons,
        "blockers": blockers,
        "duplicate": duplicate,
        "is_already_refunded": is_already_refunded,
    }


def create_refund_request(
    db: Session,
    *,
    order: Order,
    customer: Customer,
    reason: str,
    amount: float | None = None,
    ticket: Ticket | None = None,
) -> tuple[Refund | None, str | None]:
    is_already_refunded = (
        order.status == "REFUNDED"
        or order.payment_status == "REFUNDED"
        or any(r.status in {"APPROVED", "PROCESSED"} for r in (order.refunds or []))
    )
    if is_already_refunded:
        return None, "Order has already been refunded."
    if has_duplicate_refund(db, order.id):
        return None, "Duplicate refund request: an active refund already exists for this order."
    refund = Refund(
        refund_id=next_refund_id(db),
        order_id=order.id,
        customer_id=customer.id,
        ticket_id=ticket.id if ticket else None,
        amount=amount if amount is not None else order.amount,
        reason=reason,
        status="PENDING_APPROVAL",
    )
    db.add(refund)
    db.commit()
    db.refresh(refund)
    return refund, None


def refund_to_dict(r: Refund) -> dict:
    return {
        "id": r.id,
        "refund_id": r.refund_id,
        "order_id": r.order_id,
        "customer_id": r.customer_id,
        "ticket_id": r.ticket_id,
        "amount": r.amount,
        "reason": r.reason,
        "status": r.status,
        "requested_at": r.requested_at.isoformat() if r.requested_at else None,
        "approved_at": r.approved_at.isoformat() if r.approved_at else None,
        "processed_at": r.processed_at.isoformat() if r.processed_at else None,
        "rejected_reason": r.rejected_reason,
    }
