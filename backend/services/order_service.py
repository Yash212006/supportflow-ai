from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.order import Order


def get_order_by_number(db: Session, order_number: str) -> Order | None:
    return db.scalar(select(Order).where(Order.order_number == order_number))


def get_order_by_id(db: Session, order_id: int) -> Order | None:
    return db.get(Order, order_id)


def list_orders(
    db: Session,
    customer_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 300,
) -> list[Order]:
    sync_order_statuses(db)
    stmt = select(Order).order_by(Order.id.desc())
    if customer_id:
        stmt = stmt.where(Order.customer_id == customer_id)
    if status:
        stmt = stmt.where(Order.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Order.order_number.ilike(like)) | (Order.product_name.ilike(like)))
    return list(db.scalars(stmt.limit(limit)))


def delay_days(order: Order, today: date | None = None) -> int | None:
    today = today or date.today()
    if order.status in {"REFUNDED", "CANCELLED"}:
        return 0
    if getattr(order, "refunds", None) and any(
        r.status in {"APPROVED", "PROCESSED"} for r in order.refunds
    ):
        return 0
    if order.status == "DELIVERED":
        if order.expected_delivery and order.actual_delivery:
            return max(0, (order.actual_delivery - order.expected_delivery).days)
        return 0
    if order.expected_delivery and order.status in {
        "SHIPPED",
        "OUT_FOR_DELIVERY",
        "PROCESSING",
        "PLACED",
        "DELAYED",
    }:
        return max(0, (today - order.expected_delivery).days)
    return None


def order_to_dict(o: Order) -> dict:
    refunds = getattr(o, "refunds", None) or []
    latest_refund = None
    refund_status = None
    has_active_refund = False
    is_refund_processed = False

    if refunds:
        sorted_refunds = sorted(refunds, key=lambda r: getattr(r, "id", 0) or 0, reverse=True)
        latest = sorted_refunds[0]
        latest_refund = {
            "refund_id": latest.refund_id,
            "status": latest.status,
            "amount": latest.amount,
            "reason": latest.reason,
        }
        refund_status = latest.status
        has_active_refund = any(
            r.status in {"PENDING_APPROVAL", "APPROVED", "PROCESSED"} for r in refunds
        )
        is_refund_processed = any(r.status in {"APPROVED", "PROCESSED"} for r in refunds)

    is_refunded = (
        o.status == "REFUNDED"
        or o.payment_status == "REFUNDED"
        or is_refund_processed
    )
    effective_status = "REFUNDED" if is_refunded else o.status
    effective_payment_status = "REFUNDED" if is_refunded else o.payment_status

    today_val = date.today()
    if (
        effective_status in {"PLACED", "PROCESSING", "SHIPPED", "OUT_FOR_DELIVERY"}
        and o.expected_delivery
        and o.expected_delivery < today_val
        and o.actual_delivery is None
    ):
        effective_status = "DELAYED"

    d = 0 if effective_status in {"REFUNDED", "CANCELLED"} else delay_days(o)

    tickets = getattr(o, "tickets", None) or []
    open_tickets = [t for t in tickets if t.status not in {"RESOLVED", "CLOSED"}]
    sorted_tickets = sorted(tickets, key=lambda t: getattr(t, "id", 0) or 0, reverse=True)
    latest_ticket = sorted_tickets[0] if sorted_tickets else None

    return {
        "id": o.id,
        "order_number": o.order_number,
        "customer_id": o.customer_id,
        "order_date": o.order_date.isoformat() if o.order_date else None,
        "expected_delivery": o.expected_delivery.isoformat() if o.expected_delivery else None,
        "actual_delivery": o.actual_delivery.isoformat() if o.actual_delivery else None,
        "status": effective_status,
        "amount": o.amount,
        "payment_status": effective_payment_status,
        "shipping_address": o.shipping_address,
        "product_name": o.product_name,
        "delay_days": d,
        "refund_status": refund_status,
        "latest_refund": latest_refund,
        "is_refunded": is_refunded,
        "has_active_refund": has_active_refund,
        "open_ticket_count": len(open_tickets),
        "latest_ticket": {
            "ticket_number": latest_ticket.ticket_number,
            "status": latest_ticket.status,
            "subject": latest_ticket.subject,
        } if latest_ticket else None,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


def sync_order_statuses(db: Session) -> int:
    """Synchronize order and ticket statuses with approved/processed refunds and overdue fulfillment states."""
    from backend.models.refund import Refund
    from backend.models.ticket import Ticket

    today_val = date.today()
    updated_count = 0
    orders = db.query(Order).all()
    for o in orders:
        changed = False
        refunds = o.refunds or []
        is_processed = any(r.status in {"APPROVED", "PROCESSED"} for r in refunds)
        if is_processed:
            if o.status != "REFUNDED":
                o.status = "REFUNDED"
                changed = True
            if o.payment_status != "REFUNDED":
                o.payment_status = "REFUNDED"
                changed = True
            for t in (o.tickets or []):
                if t.status in {"OPEN", "IN_PROGRESS", "WAITING_FOR_CUSTOMER", "ESCALATED"}:
                    t.status = "RESOLVED"
                    t.resolution = "Refund processed and approved."
                    changed = True
        elif o.actual_delivery is not None and o.status != "DELIVERED":
            o.status = "DELIVERED"
            changed = True
        elif (
            o.status in {"PLACED", "PROCESSING", "SHIPPED", "OUT_FOR_DELIVERY"}
            and o.expected_delivery is not None
            and o.expected_delivery < today_val
            and o.actual_delivery is None
        ):
            o.status = "DELAYED"
            changed = True

        if changed:
            updated_count += 1

    if updated_count > 0:
        db.commit()
    return updated_count
