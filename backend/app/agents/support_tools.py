"""Backend tools for the customer-support agents. All are customer-scoped via ToolContext."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.tooling import ToolContext
from app.core.errors import NotFound
from app.knowledge.service import search as kb_search
from app.models import Order, Payment, Shipment, SupportTicket
from app.models.enums import (
    ActionType,
    IssueCategory,
    OrderStatus,
    PaymentStatus,
    TicketPriority,
    TicketStatus,
)
from app.policies.facts import assess_refund_risk, latest_payment
from app.policies.service import active_version
from app.services.audit import audit, jsonable
from app.services.tickets import create_ticket, set_status
from app.workflows.execution_engine import ExecutionEngine


def _scoped_order(ctx: ToolContext, order_number: int | None = None, order_id: str | None = None) -> Order:
    stmt = select(Order).where(Order.business_id == ctx.business_id)
    if ctx.customer_id is not None:
        stmt = stmt.where(Order.customer_id == ctx.customer_id)  # ownership verification
    if order_id:
        stmt = stmt.where(Order.id == uuid.UUID(order_id))
    elif order_number is not None:
        stmt = stmt.where(Order.order_number == int(order_number))
    else:
        raise NotFound("No order reference")
    o = ctx.db.scalars(stmt).first()
    if o is None:
        raise NotFound("Order not found for this customer")
    return o


def list_customer_orders(ctx: ToolContext, limit: int = 8) -> list[dict[str, Any]]:
    rows = ctx.db.scalars(select(Order).where(Order.business_id == ctx.business_id, Order.customer_id == ctx.customer_id).order_by(Order.placed_at.desc()).limit(limit)).all()
    return [
        jsonable({"order_id": o.id, "order_number": o.order_number, "status": o.status, "total": o.total_amount, "currency": o.currency, "placed_at": o.placed_at, "items": ", ".join(i.product.name for i in o.items)})
        for o in rows
    ]


def get_conversation_context(ctx: ToolContext, context: dict[str, Any]) -> dict[str, Any]:
    return {"last_order_number": context.get("last_order_number"), "last_intent": context.get("last_intent")}


def get_order_details(ctx: ToolContext, order_number: int | None = None, order_id: str | None = None) -> dict[str, Any]:
    o = _scoped_order(ctx, order_number, order_id)
    return jsonable(
        {
            "order_id": o.id,
            "order_number": o.order_number,
            "status": o.status,
            "currency": o.currency,
            "total": o.total_amount,
            "placed_at": o.placed_at,
            "delivered_at": o.delivered_at,
            "is_sample": o.is_sample,
            "items": [{"name": i.product.name, "qty": i.quantity, "unit_price": i.unit_price, "category": i.product.category, "refundable_days": i.product.refundable_days} for i in o.items],
        }
    )


def get_payment_records(ctx: ToolContext, order_id: str) -> list[dict[str, Any]]:
    o = _scoped_order(ctx, order_id=order_id)
    pays = ctx.db.scalars(select(Payment).where(Payment.order_id == o.id).order_by(Payment.attempt)).all()
    return [
        jsonable({"payment_id": p.id, "status": p.status, "source": p.source, "amount": p.amount, "refunded": p.refunded_amount, "refundable": p.refundable_amount, "currency": p.currency, "paypal_order_id": p.paypal_order_id, "paypal_capture_id": p.paypal_capture_id, "failure_reason": p.failure_reason, "captured_at": p.captured_at})
        for p in pays
    ]


def get_shipment_records(ctx: ToolContext, order_id: str) -> list[dict[str, Any]]:
    o = _scoped_order(ctx, order_id=order_id)
    rows = ctx.db.scalars(select(Shipment).where(Shipment.order_id == o.id).order_by(Shipment.created_at)).all()
    return [jsonable({"carrier": s.carrier, "tracking_number": s.tracking_number, "status": s.status, "estimated_delivery": s.estimated_delivery, "delivered_at": s.delivered_at, "last_event": s.last_event}) for s in rows]


def search_knowledge_base(ctx: ToolContext, query: str, category: str | None = None, k: int = 4) -> list[dict[str, Any]]:
    return [c.to_dict() for c in kb_search(ctx.db, ctx.business_id, query, k=k, category=category)]


def get_active_policy(ctx: ToolContext, action_type: str = "INITIATE_REFUND") -> dict[str, Any] | None:
    found = active_version(ctx.db, ctx.business_id, ActionType(action_type))
    if not found:
        return None
    pol, ver = found
    return jsonable({"policy": pol.name, "key": pol.key, "version": ver.version, "effective_from": ver.effective_from, "default_outcome": ver.default_outcome, "rules": [{"id": r.get("id"), "name": r.get("name"), "outcome": r.get("outcome"), "explanation": r.get("explanation")} for r in ver.rules]})


def assess_refund_risk_tool(ctx: ToolContext, order_id: str, amount: str | None) -> dict[str, Any]:
    o = _scoped_order(ctx, order_id=order_id)
    pay = latest_payment(ctx.db, o.id)
    amt = Decimal(amount) if amount else (pay.refundable_amount if pay else None)
    return assess_refund_risk(ctx.db, order=o, payment=pay, amount=amt).to_dict()


def request_refund_action(ctx: ToolContext, order_id: str, amount: str | None, reason: str, ticket_id: str | None, execution_id: str, idempotency_key: str) -> dict[str, Any]:
    """Hands the refund to the Controlled Action Execution Engine. The engine and the deterministic
    policy engine decide; this tool only reports what actually happened."""
    o = _scoped_order(ctx, order_id=order_id)
    ticket = ctx.db.get(SupportTicket, uuid.UUID(ticket_id)) if ticket_id else None
    outcome = ExecutionEngine(ctx.db).request_refund(
        business_id=ctx.business_id,
        order=o,
        amount=Decimal(amount) if amount else None,
        reason=reason,
        requested_by="agent:resolution",
        idempotency_key=idempotency_key,
        ticket=ticket,
        agent_execution_id=uuid.UUID(execution_id),
        requested_by_user_id=ctx.user_id,
    )
    return outcome.summary


def cancel_unpaid_order(ctx: ToolContext, order_id: str, reason: str) -> dict[str, Any]:
    """Only unpaid (PENDING_PAYMENT) orders can be cancelled without a financial action."""
    o = _scoped_order(ctx, order_id=order_id)
    if o.status != OrderStatus.PENDING_PAYMENT:
        return {"cancelled": False, "reason": f"Order is {o.status.value}; paid orders are cancelled via refund"}
    has_capture = ctx.db.scalars(select(Payment).where(Payment.order_id == o.id, Payment.status.in_((PaymentStatus.CAPTURED, PaymentStatus.CAPTURE_PENDING)))).first()
    if has_capture:
        return {"cancelled": False, "reason": "A payment capture exists for this order"}
    from app.core.database import utcnow

    o.status = OrderStatus.CANCELLED
    o.cancelled_at = utcnow()
    audit(ctx.db, business_id=ctx.business_id, actor="agent:resolution", action="order.cancelled", entity_type="order", entity_id=o.id, summary=f"Order #{o.order_number} cancelled: {reason}")
    ctx.db.commit()
    return {"cancelled": True, "order_number": o.order_number}


def create_or_update_ticket(ctx: ToolContext, subject: str, description: str, category: str, order_id: str | None, ticket_id: str | None, confidence: float | None, priority: str = "MEDIUM") -> dict[str, Any]:
    db: Session = ctx.db
    assert ctx.customer_id
    if ticket_id:
        t = db.get(SupportTicket, uuid.UUID(ticket_id))
        if t is None or t.customer_id != ctx.customer_id:
            raise NotFound("Ticket not found")
        if t.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
            t.reopened_count += 1
            set_status(db, t, TicketStatus.OPEN, actor="agent:resolution", detail="Customer followed up")
        t.category = IssueCategory(category)
        if order_id and not t.order_id:
            t.order_id = uuid.UUID(order_id)
    else:
        t = create_ticket(db, business_id=ctx.business_id, customer_id=ctx.customer_id, subject=subject, description=description, actor="agent:orchestrator", order_id=uuid.UUID(order_id) if order_id else None, category=IssueCategory(category), priority=TicketPriority(priority), confidence=confidence)
    if t.status == TicketStatus.OPEN:
        set_status(db, t, TicketStatus.IN_PROGRESS, actor="agent:orchestrator", detail=f"AI classified as {category}")
    db.flush()
    return {"ticket_id": str(t.id), "ticket_number": t.ticket_number, "status": t.status.value}


def escalate_ticket(ctx: ToolContext, ticket_id: str, reason: str) -> dict[str, Any]:
    t = ctx.db.get(SupportTicket, uuid.UUID(ticket_id))
    if t is None or t.business_id != ctx.business_id:
        raise NotFound("Ticket not found")
    t.priority = TicketPriority.HIGH
    set_status(ctx.db, t, TicketStatus.ESCALATED, actor="agent:resolution", detail=reason)
    return {"ticket_id": str(t.id), "status": t.status.value}


def resolve_ticket(ctx: ToolContext, ticket_id: str, summary: str) -> dict[str, Any]:
    t = ctx.db.get(SupportTicket, uuid.UUID(ticket_id))
    if t is None or t.business_id != ctx.business_id:
        raise NotFound("Ticket not found")
    set_status(ctx.db, t, TicketStatus.RESOLVED, actor="agent:resolution", detail=summary, resolved_by="AI")
    return {"ticket_id": str(t.id), "status": t.status.value}


def notify_customer_tool(ctx: ToolContext, title: str, body: str) -> dict[str, Any]:
    from app.models.enums import NotificationType
    from app.services.notifications import notify_customer

    assert ctx.customer_id
    notify_customer(ctx.db, customer_id=ctx.customer_id, type_=NotificationType.TICKET_UPDATED, title=title, body=body)
    return {"sent": True}


SUPPORT_TOOLS: dict[str, Callable[..., Any]] = {
    "list_customer_orders": list_customer_orders,
    "get_conversation_context": get_conversation_context,
    "get_order_details": get_order_details,
    "get_payment_records": get_payment_records,
    "get_shipment_records": get_shipment_records,
    "search_knowledge_base": search_knowledge_base,
    "get_active_policy": get_active_policy,
    "assess_refund_risk": assess_refund_risk_tool,
    "request_refund_action": request_refund_action,
    "cancel_unpaid_order": cancel_unpaid_order,
    "create_or_update_ticket": create_or_update_ticket,
    "escalate_ticket": escalate_ticket,
    "resolve_ticket": resolve_ticket,
    "notify_customer": notify_customer_tool,
}
