"""Customer portal API. Every query is scoped to principal.customer_id."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.serializers import (
    message_out,
    notification_out,
    order_out,
    payment_out,
    product_out,
    refund_out,
    ticket_out,
)
from app.core.database import get_db, utcnow
from app.core.deps import Principal, require_customer
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.models import (
    Conversation,
    Message,
    Notification,
    Order,
    OrderItem,
    Payment,
    Product,
    Refund,
    SupportTicket,
)
from app.models.enums import (
    IssueCategory,
    MessageRole,
    OrderStatus,
    RefundStatus,
    TicketPriority,
    TicketStatus,
)
from app.services import payments as payment_service
from app.services.audit import audit
from app.services.tickets import add_event, create_ticket, get_ticket, set_status
from app.workflows.execution_engine import ExecutionEngine

router = APIRouter(prefix="/api/customer", tags=["customer"])


def _order(db: Session, p: Principal, order_id: uuid.UUID) -> Order:
    o = db.get(Order, order_id)
    if o is None or o.business_id != p.business_id or o.customer_id != p.customer_id:
        raise NotFound("Order not found")
    return o


@router.get("/dashboard")
def dashboard(p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> dict[str, object]:
    orders = db.scalars(select(Order).where(Order.customer_id == p.customer_id).order_by(Order.placed_at.desc()).limit(5)).all()
    tickets = db.scalars(
        select(SupportTicket).where(SupportTicket.customer_id == p.customer_id, SupportTicket.status.notin_((TicketStatus.RESOLVED, TicketStatus.CLOSED))).order_by(SupportTicket.created_at.desc())
    ).all()
    refunds = db.scalars(select(Refund).where(Refund.customer_id == p.customer_id).order_by(Refund.created_at.desc()).limit(5)).all()
    convs = db.scalars(select(Conversation).where(Conversation.user_id == p.user_id, Conversation.channel == "support").order_by(Conversation.updated_at.desc()).limit(5)).all()
    notes = db.scalars(select(Notification).where(Notification.user_id == p.user_id).order_by(Notification.created_at.desc()).limit(8)).all()
    unread = db.scalar(select(func.count(Notification.id)).where(Notification.user_id == p.user_id, Notification.read_at.is_(None))) or 0
    total_orders = db.scalar(select(func.count(Order.id)).where(Order.customer_id == p.customer_id)) or 0
    return {
        "recent_orders": [order_out(o) for o in orders],
        "open_tickets": [ticket_out(t) for t in tickets],
        "recent_refunds": [refund_out(r) for r in refunds],
        "recent_conversations": [{"id": str(c.id), "title": c.title, "updated_at": c.updated_at.isoformat()} for c in convs],
        "notifications": [notification_out(n) for n in notes],
        "stats": {"total_orders": total_orders, "open_tickets": len(tickets), "unread_notifications": unread},
    }


@router.get("/products")
def products(p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return [product_out(x) for x in db.scalars(select(Product).where(Product.business_id == p.business_id).order_by(Product.category, Product.name))]


@router.get("/orders")
def orders(p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> list[dict[str, object]]:
    q = select(Order).where(Order.customer_id == p.customer_id).options(selectinload(Order.items), selectinload(Order.payments), selectinload(Order.shipments)).order_by(Order.placed_at.desc())
    return [order_out(o) for o in db.scalars(q)]


@router.get("/orders/{order_id}")
def order_detail(order_id: uuid.UUID, p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> dict[str, object]:
    o = _order(db, p, order_id)
    data = order_out(o, detail=True)
    data["refunds"] = [refund_out(r) for r in db.scalars(select(Refund).where(Refund.order_id == o.id).order_by(Refund.created_at.desc()))]
    return data


class OrderItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1, le=20)


class CreateOrderIn(BaseModel):
    items: list[OrderItemIn] = Field(min_length=1, max_length=20)


@router.post("/orders")
def create_order(body: CreateOrderIn, p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> dict[str, object]:
    """Creates an internal order (PENDING_PAYMENT). Prices come from the catalogue, never the client."""
    assert p.customer_id
    from app.models import Business

    business = db.get(Business, p.business_id)
    assert business
    total = Decimal("0")
    lines: list[tuple[Product, int]] = []
    for it in body.items:
        prod = db.get(Product, it.product_id)
        if prod is None or prod.business_id != p.business_id:
            raise ValidationFailed("Unknown product")
        lines.append((prod, it.quantity))
        total += prod.price * it.quantity
    number = int(db.scalar(select(func.max(Order.order_number)).where(Order.business_id == p.business_id)) or 1000) + 1
    order = Order(business_id=p.business_id, customer_id=p.customer_id, order_number=number, status=OrderStatus.PENDING_PAYMENT, currency=business.currency, total_amount=total, placed_at=utcnow())
    db.add(order)
    db.flush()
    for prod, qty in lines:
        db.add(OrderItem(order_id=order.id, product_id=prod.id, quantity=qty, unit_price=prod.price))
    audit(db, business_id=p.business_id, actor=p.actor, action="order.created", entity_type="order", entity_id=order.id, summary=f"Order #{number} created ({business.currency} {total})")
    db.commit()
    db.refresh(order)
    return order_out(order, detail=True)


@router.post("/orders/{order_id}/pay")
def pay_order(order_id: uuid.UUID, p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> dict[str, object]:
    """Creates a PayPal Sandbox order (Orders API v2) and returns the buyer approval URL."""
    o = _order(db, p, order_id)
    payment = payment_service.create_paypal_checkout(db, order=o, actor=p.actor)
    return payment_out(payment)


@router.post("/payments/{payment_id}/capture")
def capture(payment_id: uuid.UUID, p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> dict[str, object]:
    """Called after the buyer returns from PayPal approval. The capture result is PayPal's response."""
    pay = payment_service.get_payment(db, p.business_id, payment_id, customer_id=p.customer_id)
    pay = payment_service.capture_paypal_order(db, payment=pay, actor=p.actor)
    return payment_out(pay)


@router.get("/payments/{payment_id}")
def payment_detail(payment_id: uuid.UUID, p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> dict[str, object]:
    return payment_out(payment_service.get_payment(db, p.business_id, payment_id, customer_id=p.customer_id))


# ----------------------------------------------------------------------------------- tickets
class TicketIn(BaseModel):
    subject: str = Field(min_length=3, max_length=250)
    description: str = Field(min_length=5, max_length=5000)
    order_id: uuid.UUID | None = None
    category: IssueCategory | None = None


@router.get("/tickets")
def tickets(p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return [ticket_out(t) for t in db.scalars(select(SupportTicket).where(SupportTicket.customer_id == p.customer_id).order_by(SupportTicket.created_at.desc()))]


@router.post("/tickets")
def new_ticket(body: TicketIn, p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> dict[str, object]:
    assert p.customer_id
    if body.order_id:
        _order(db, p, body.order_id)
    t = create_ticket(db, business_id=p.business_id, customer_id=p.customer_id, subject=body.subject, description=body.description, actor=p.actor, order_id=body.order_id, category=body.category, priority=TicketPriority.MEDIUM)
    db.commit()
    return ticket_out(t, detail=True)


@router.get("/tickets/{ticket_id}")
def ticket_detail(ticket_id: uuid.UUID, p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> dict[str, object]:
    t = get_ticket(db, p.business_id, ticket_id, customer_id=p.customer_id)
    data = ticket_out(t, detail=True)
    data["events"] = [e for e in data["events"] if not str(e.get("event", "")).startswith("internal")]
    return data


class ReasonIn(BaseModel):
    reason: str = Field(default="", max_length=1000)


@router.post("/tickets/{ticket_id}/reopen")
def reopen(ticket_id: uuid.UUID, body: ReasonIn, p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> dict[str, object]:
    t = get_ticket(db, p.business_id, ticket_id, customer_id=p.customer_id)
    if t.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
        raise Conflict("Only resolved tickets can be reopened")
    t.reopened_count += 1
    t.resolved_at = None
    set_status(db, t, TicketStatus.OPEN, actor=p.actor, detail=body.reason or "Reopened by customer")
    db.commit()
    return ticket_out(t, detail=True)


@router.post("/tickets/{ticket_id}/escalate")
def escalate(ticket_id: uuid.UUID, body: ReasonIn, p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> dict[str, object]:
    t = get_ticket(db, p.business_id, ticket_id, customer_id=p.customer_id)
    if t.status in (TicketStatus.CLOSED,):
        raise Conflict("Ticket is closed")
    t.priority = TicketPriority.HIGH if t.priority in (TicketPriority.LOW, TicketPriority.MEDIUM) else t.priority
    set_status(db, t, TicketStatus.ESCALATED, actor=p.actor, detail=body.reason or "Customer requested a human agent")
    db.commit()
    return ticket_out(t, detail=True)


@router.post("/tickets/{ticket_id}/rate")
def rate(ticket_id: uuid.UUID, score: int, p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> dict[str, object]:
    if not 1 <= score <= 5:
        raise ValidationFailed("Score must be 1-5")
    t = get_ticket(db, p.business_id, ticket_id, customer_id=p.customer_id)
    t.satisfaction_score = score
    add_event(db, t, p.actor, "rated", f"{score}/5")
    db.commit()
    return ticket_out(t)


# ----------------------------------------------------------------------------------- refunds
class RefundRequestIn(BaseModel):
    order_id: uuid.UUID
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    reason: str = Field(min_length=3, max_length=500)


@router.get("/refunds")
def my_refunds(p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return [refund_out(r) for r in db.scalars(select(Refund).where(Refund.customer_id == p.customer_id).order_by(Refund.created_at.desc()))]


@router.post("/refunds")
def request_refund(body: RefundRequestIn, p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> dict[str, object]:
    """Customer refund request. Goes through the policy engine and execution engine like every
    other financial action; the customer cannot choose the outcome."""
    assert p.customer_id
    o = _order(db, p, body.order_id)
    open_refund = db.scalars(select(Refund).where(Refund.order_id == o.id, Refund.status.in_((RefundStatus.REQUESTED, RefundStatus.AWAITING_APPROVAL, RefundStatus.PENDING)))).first()
    if open_refund:
        raise Conflict("A refund for this order is already in progress", details={"refund_id": str(open_refund.id)})
    ticket = create_ticket(db, business_id=p.business_id, customer_id=p.customer_id, subject=f"Refund request for order #{o.order_number}", description=body.reason, actor=p.actor, order_id=o.id, category=IssueCategory.REFUND_REQUEST)
    db.commit()
    key = f"refund:{o.id}:{body.amount or 'full'}:{ticket.id}"
    outcome = ExecutionEngine(db).request_refund(business_id=p.business_id, order=o, amount=body.amount, reason=body.reason, requested_by=p.actor, idempotency_key=key, ticket=ticket, requested_by_user_id=p.user_id)
    return outcome.summary


# ----------------------------------------------------------------------------------- conversations
@router.get("/conversations")
def conversations(p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = db.scalars(select(Conversation).where(Conversation.user_id == p.user_id, Conversation.channel == "support").order_by(Conversation.updated_at.desc())).all()
    return [{"id": str(c.id), "title": c.title, "ticket_id": str(c.ticket_id) if c.ticket_id else None, "updated_at": c.updated_at.isoformat()} for c in rows]


@router.get("/conversations/{conv_id}")
def conversation(conv_id: uuid.UUID, p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> dict[str, object]:
    c = db.get(Conversation, conv_id)
    if c is None or c.user_id != p.user_id:
        raise NotFound("Conversation not found")
    msgs = db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at)).all()
    return {"id": str(c.id), "title": c.title, "ticket_id": str(c.ticket_id) if c.ticket_id else None, "messages": [message_out(m) for m in msgs]}


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None


@router.post("/chat")
def chat(body: ChatIn, p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> dict[str, object]:
    from app.agents.support_graph import run_support_turn

    if body.conversation_id:
        conv = db.get(Conversation, body.conversation_id)
        if conv is None or conv.user_id != p.user_id:
            raise NotFound("Conversation not found")
    else:
        conv = Conversation(business_id=p.business_id, customer_id=p.customer_id, user_id=p.user_id, channel="support", title=body.message[:60])
        db.add(conv)
        db.commit()
    db.add(Message(conversation_id=conv.id, role=MessageRole.CUSTOMER, content=body.message))
    db.commit()
    reply = run_support_turn(db, principal=p, conversation=conv, message=body.message)
    return {"conversation_id": str(conv.id), "reply": message_out(reply)}


# ----------------------------------------------------------------------------------- notifications
@router.get("/payments")
def my_payments(p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return [payment_out(x) for x in db.scalars(select(Payment).where(Payment.customer_id == p.customer_id).order_by(Payment.created_at.desc()))]
