"""Staff/manager APIs: orders, customers, payments, refunds, tickets, approvals, policies,
executions, audit, notifications. All queries are tenant-scoped by principal.business_id."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.serializers import (
    action_out,
    approval_out,
    audit_out,
    customer_out,
    decision_out,
    execution_out,
    notification_out,
    order_out,
    payment_out,
    refund_out,
    ticket_out,
)
from app.core.database import get_db, utcnow
from app.core.deps import Principal, get_principal, require_manager, require_staff
from app.core.errors import NotFound, ValidationFailed
from app.models import (
    AgentExecution,
    ApprovalRequest,
    AuditLog,
    BusinessPolicy,
    Customer,
    ExecutionAction,
    Notification,
    Order,
    Payment,
    PayPalTransaction,
    PolicyDecision,
    PolicyVersion,
    Refund,
    SupportTicket,
    User,
)
from app.models.enums import (
    ActionState,
    ActionType,
    ApprovalStatus,
    DecisionOutcome,
    MessageRole,
    OrderStatus,
    PaymentStatus,
    RefundStatus,
    TicketPriority,
    TicketStatus,
)
from app.policies.engine import FACT_CATALOG, OPERATORS, evaluate
from app.policies.facts import assess_refund_risk, latest_payment, refund_facts
from app.policies.service import active_version, create_version, get_policy
from app.services import payments as payment_service
from app.services.audit import jsonable
from app.services.tickets import add_event, get_ticket, set_status
from app.workflows.execution_engine import ExecutionEngine, get_action

router = APIRouter(prefix="/api", tags=["manager"])


def _page(db: Session, q: Select[Any], limit: int, offset: int) -> tuple[list[Any], int]:
    total = db.scalar(select(func.count()).select_from(q.order_by(None).subquery())) or 0
    rows = list(db.scalars(q.limit(limit).offset(offset)))
    return rows, total


# ------------------------------------------------------------------------------------ orders
@router.get("/orders")
def list_orders(
    q: str | None = None,
    status: OrderStatus | None = None,
    customer_id: uuid.UUID | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    p: Principal = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(Order).where(Order.business_id == p.business_id).options(selectinload(Order.items), selectinload(Order.payments), selectinload(Order.shipments), selectinload(Order.customer))
    if status:
        stmt = stmt.where(Order.status == status)
    if customer_id:
        stmt = stmt.where(Order.customer_id == customer_id)
    if q:
        qs = q.strip().lstrip("#")
        conds = [Customer.full_name.ilike(f"%{qs}%"), Customer.email.ilike(f"%{qs}%")]
        if qs.isdigit():
            conds.append(Order.order_number == int(qs))  # type: ignore[arg-type]
        stmt = stmt.join(Customer, Customer.id == Order.customer_id).where(or_(*conds))
    rows, total = _page(db, stmt.order_by(Order.placed_at.desc()), limit, offset)
    return {"items": [order_out(o) for o in rows], "total": total}


def _get_order(db: Session, p: Principal, order_id: uuid.UUID) -> Order:
    o = db.get(Order, order_id)
    if o is None or o.business_id != p.business_id:
        raise NotFound("Order not found")
    return o


@router.get("/orders/{order_id}")
def order_detail(order_id: uuid.UUID, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    o = _get_order(db, p, order_id)
    data = order_out(o, detail=True)
    data["customer"] = customer_out(o.customer)
    data["refunds"] = [refund_out(r) for r in db.scalars(select(Refund).where(Refund.order_id == o.id).order_by(Refund.created_at.desc()))]
    data["tickets"] = [ticket_out(t) for t in db.scalars(select(SupportTicket).where(SupportTicket.order_id == o.id))]
    data["executions"] = [execution_out(e) for e in db.scalars(select(AgentExecution).where(AgentExecution.order_id == o.id).order_by(AgentExecution.created_at.desc()))]
    data["decisions"] = [decision_out(d) for d in db.scalars(select(PolicyDecision).where(PolicyDecision.order_id == o.id).order_by(PolicyDecision.created_at.desc()))]
    return data


@router.get("/orders/{order_id}/payments")
def order_payments(order_id: uuid.UUID, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    o = _get_order(db, p, order_id)
    return [payment_out(x) for x in o.payments]


# ------------------------------------------------------------------------------------ customers
@router.get("/customers")
def list_customers(q: str | None = None, limit: int = Query(50, le=200), offset: int = 0, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(Customer).where(Customer.business_id == p.business_id)
    if q:
        stmt = stmt.where(or_(Customer.full_name.ilike(f"%{q}%"), Customer.email.ilike(f"%{q}%")))
    rows, total = _page(db, stmt.order_by(Customer.full_name), limit, offset)
    ids = [c.id for c in rows]
    stats: dict[uuid.UUID, dict[str, Any]] = {i: {"orders": 0, "spent": Decimal("0"), "open_tickets": 0, "refunds": 0} for i in ids}
    if ids:
        for cid, n, spent in db.execute(select(Order.customer_id, func.count(Order.id), func.coalesce(func.sum(Order.total_amount), 0)).where(Order.customer_id.in_(ids)).group_by(Order.customer_id)):
            stats[cid].update(orders=n, spent=spent)
        for cid, n in db.execute(select(SupportTicket.customer_id, func.count()).where(SupportTicket.customer_id.in_(ids), SupportTicket.status.notin_((TicketStatus.RESOLVED, TicketStatus.CLOSED))).group_by(SupportTicket.customer_id)):
            stats[cid]["open_tickets"] = n
        for cid, n in db.execute(select(Refund.customer_id, func.count()).where(Refund.customer_id.in_(ids)).group_by(Refund.customer_id)):
            stats[cid]["refunds"] = n
    return {"items": [{**customer_out(c), **jsonable(stats[c.id])} for c in rows], "total": total}


@router.get("/customers/{customer_id}")
def customer_detail(customer_id: uuid.UUID, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    c = db.get(Customer, customer_id)
    if c is None or c.business_id != p.business_id:
        raise NotFound("Customer not found")
    orders = db.scalars(select(Order).where(Order.customer_id == c.id).order_by(Order.placed_at.desc())).all()
    return {
        **customer_out(c),
        "orders": [order_out(o) for o in orders],
        "tickets": [ticket_out(t) for t in db.scalars(select(SupportTicket).where(SupportTicket.customer_id == c.id).order_by(SupportTicket.created_at.desc()))],
        "refunds": [refund_out(r) for r in db.scalars(select(Refund).where(Refund.customer_id == c.id).order_by(Refund.created_at.desc()))],
    }


# ------------------------------------------------------------------------------------ payments
@router.get("/payments")
def list_payments(status: PaymentStatus | None = None, source: str | None = None, q: str | None = None, limit: int = Query(50, le=200), offset: int = 0, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(Payment).where(Payment.business_id == p.business_id).options(selectinload(Payment.order), selectinload(Payment.customer))
    if status:
        stmt = stmt.where(Payment.status == status)
    if source:
        stmt = stmt.where(Payment.source == source)
    if q:
        stmt = stmt.where(or_(Payment.paypal_order_id.ilike(f"%{q}%"), Payment.paypal_capture_id.ilike(f"%{q}%")))
    rows, total = _page(db, stmt.order_by(Payment.created_at.desc()), limit, offset)
    return {"items": [payment_out(x) for x in rows], "total": total}


@router.get("/payments/{payment_id}")
def payment_detail(payment_id: uuid.UUID, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    pay = payment_service.get_payment(db, p.business_id, payment_id)
    data = payment_out(pay)
    data["refunds"] = [refund_out(r) for r in pay.refunds]
    data["paypal_transactions"] = [
        jsonable({"id": t.id, "operation": t.operation, "request_id": t.request_id, "http_status": t.http_status, "paypal_debug_id": t.paypal_debug_id, "resource_id": t.resource_id, "resource_status": t.resource_status, "outcome": t.outcome, "error_message": t.error_message, "duration_ms": t.duration_ms, "created_at": t.created_at})
        for t in db.scalars(select(PayPalTransaction).where(PayPalTransaction.payment_id == pay.id).order_by(PayPalTransaction.created_at.desc()))
    ]
    return data


@router.post("/payments/{payment_id}/sync")
def payment_sync(payment_id: uuid.UUID, p: Principal = Depends(require_manager), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Reads the PayPal order (GET /v2/checkout/orders/{id}) and synchronises local state."""
    pay = payment_service.get_payment(db, p.business_id, payment_id)
    return payment_out(payment_service.sync_paypal_order(db, payment=pay, actor=p.actor))


# ------------------------------------------------------------------------------------ refunds
@router.get("/refunds")
def list_refunds(status: RefundStatus | None = None, min_amount: Decimal | None = None, limit: int = Query(50, le=200), offset: int = 0, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(Refund).where(Refund.business_id == p.business_id).options(selectinload(Refund.order), selectinload(Refund.customer), selectinload(Refund.payment))
    if status:
        stmt = stmt.where(Refund.status == status)
    if min_amount is not None:
        stmt = stmt.where(Refund.amount >= min_amount)
    rows, total = _page(db, stmt.order_by(Refund.created_at.desc()), limit, offset)
    decisions = {d.id: d for d in db.scalars(select(PolicyDecision).where(PolicyDecision.id.in_([r.policy_decision_id for r in rows if r.policy_decision_id])))}
    approvals = {a.execution_action_id: a for a in db.scalars(select(ApprovalRequest).where(ApprovalRequest.execution_action_id.in_([r.execution_action_id for r in rows if r.execution_action_id])))}
    items = []
    for r in rows:
        d = decisions.get(r.policy_decision_id) if r.policy_decision_id else None
        a = approvals.get(r.execution_action_id) if r.execution_action_id else None
        items.append({**refund_out(r), "policy_outcome": d.outcome.value if d else None, "approval_status": a.status.value if a else None, "approval_id": str(a.id) if a else None})
    return {"items": items, "total": total}


@router.get("/refunds/{refund_id}")
def refund_detail(refund_id: uuid.UUID, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    r = db.get(Refund, refund_id)
    if r is None or r.business_id != p.business_id:
        raise NotFound("Refund not found")
    data = refund_out(r)
    data["decision"] = decision_out(db.get(PolicyDecision, r.policy_decision_id)) if r.policy_decision_id else None  # type: ignore[arg-type]
    action = db.get(ExecutionAction, r.execution_action_id) if r.execution_action_id else None
    data["action"] = action_out(action) if action else None
    appr = db.scalars(select(ApprovalRequest).where(ApprovalRequest.execution_action_id == r.execution_action_id)).first() if r.execution_action_id else None
    data["approval"] = approval_out(appr) if appr else None
    data["paypal_transactions"] = [
        jsonable({"operation": t.operation, "request_id": t.request_id, "http_status": t.http_status, "paypal_debug_id": t.paypal_debug_id, "resource_id": t.resource_id, "resource_status": t.resource_status, "outcome": t.outcome, "error_message": t.error_message, "created_at": t.created_at})
        for t in db.scalars(select(PayPalTransaction).where(PayPalTransaction.refund_id == r.id).order_by(PayPalTransaction.created_at))
    ]
    return data


class StaffRefundIn(BaseModel):
    order_id: uuid.UUID
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    reason: str = Field(min_length=3, max_length=500)
    ticket_id: uuid.UUID | None = None


@router.post("/refunds")
def staff_refund(body: StaffRefundIn, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Staff-initiated refund proposal: still evaluated by the policy engine."""
    o = _get_order(db, p, body.order_id)
    ticket = get_ticket(db, p.business_id, body.ticket_id) if body.ticket_id else None
    outcome = ExecutionEngine(db).request_refund(business_id=p.business_id, order=o, amount=body.amount, reason=body.reason, requested_by=p.actor, idempotency_key=f"staff-refund:{o.id}:{body.amount or 'full'}:{uuid.uuid4().hex[:8]}", ticket=ticket, requested_by_user_id=p.user_id)
    return outcome.summary


@router.post("/actions/{action_id}/reconcile")
def reconcile(action_id: uuid.UUID, p: Principal = Depends(require_manager), db: Session = Depends(get_db)) -> dict[str, Any]:
    action = get_action(db, p.business_id, action_id)
    return ExecutionEngine(db).reconcile(action, actor=p.actor).summary


@router.post("/actions/{action_id}/retry")
def retry(action_id: uuid.UUID, p: Principal = Depends(require_manager), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Retry only when PayPal was never reached (not configured / connection refused)."""
    from app.workflows.execution_engine import transition

    action = get_action(db, p.business_id, action_id)
    if action.error_code not in ("PAYPAL_NOT_CONFIGURED", "PAYPAL_TRANSPORT", "PAYPAL_AUTH"):
        raise ValidationFailed("This action cannot be retried; PayPal may have processed it or rejected it")
    transition(action, ActionState.APPROVED, actor=p.actor, note="Manual retry")
    refund = db.scalars(select(Refund).where(Refund.execution_action_id == action.id)).one()
    refund.status = RefundStatus.REQUESTED
    db.commit()
    return ExecutionEngine(db).execute_refund(action, actor=p.actor, approver=p.user).summary


@router.get("/actions")
def list_actions(state: str | None = None, limit: int = Query(50, le=200), offset: int = 0, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(ExecutionAction).where(ExecutionAction.business_id == p.business_id)
    if state:
        stmt = stmt.where(ExecutionAction.state == state)
    rows, total = _page(db, stmt.order_by(ExecutionAction.created_at.desc()), limit, offset)
    return {"items": [action_out(a) for a in rows], "total": total}


# ------------------------------------------------------------------------------------ tickets
@router.get("/tickets")
def list_tickets(
    q: str | None = None,
    status: TicketStatus | None = None,
    priority: TicketPriority | None = None,
    category: str | None = None,
    assigned_to_me: bool = False,
    limit: int = Query(50, le=200),
    offset: int = 0,
    p: Principal = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(SupportTicket).where(SupportTicket.business_id == p.business_id).options(selectinload(SupportTicket.customer), selectinload(SupportTicket.assigned_to))
    if status:
        stmt = stmt.where(SupportTicket.status == status)
    if priority:
        stmt = stmt.where(SupportTicket.priority == priority)
    if category:
        stmt = stmt.where(SupportTicket.category == category)
    if assigned_to_me:
        stmt = stmt.where(SupportTicket.assigned_to_user_id == p.user_id)
    if q:
        qs = q.strip().lstrip("#")
        conds = [SupportTicket.subject.ilike(f"%{qs}%")]
        if qs.isdigit():
            conds.append(SupportTicket.ticket_number == int(qs))  # type: ignore[arg-type]
        stmt = stmt.where(or_(*conds))
    rows, total = _page(db, stmt.order_by(SupportTicket.created_at.desc()), limit, offset)
    return {"items": [ticket_out(t) for t in rows], "total": total}


@router.get("/tickets/{ticket_id}")
def ticket_detail(ticket_id: uuid.UUID, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.api.serializers import message_out
    from app.models import Conversation, Message

    t = get_ticket(db, p.business_id, ticket_id)
    data = ticket_out(t, detail=True)
    data["customer"] = customer_out(t.customer)
    data["order"] = order_out(db.get(Order, t.order_id)) if t.order_id else None  # type: ignore[arg-type]
    conv = db.scalars(select(Conversation).where(Conversation.ticket_id == t.id)).first()
    data["messages"] = [message_out(m) for m in db.scalars(select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at))] if conv else []
    data["executions"] = [execution_out(e) for e in db.scalars(select(AgentExecution).where(AgentExecution.ticket_id == t.id).order_by(AgentExecution.created_at.desc()))]
    data["refunds"] = [refund_out(r) for r in db.scalars(select(Refund).where(Refund.ticket_id == t.id))]
    return data


class TicketUpdateIn(BaseModel):
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    assigned_to_user_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=2000)
    reply_to_customer: str | None = Field(default=None, max_length=4000)


@router.patch("/tickets/{ticket_id}")
def update_ticket(ticket_id: uuid.UUID, body: TicketUpdateIn, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.models import Conversation, Message
    from app.models.enums import NotificationType
    from app.services.notifications import notify_customer

    t = get_ticket(db, p.business_id, ticket_id)
    if body.assigned_to_user_id:
        u = db.get(User, body.assigned_to_user_id)
        if u is None or u.business_id != p.business_id or u.role.value == "CUSTOMER":
            raise ValidationFailed("Invalid assignee")
        t.assigned_to_user_id = u.id
        add_event(db, t, p.actor, "assigned", u.full_name)
    if body.priority:
        t.priority = body.priority
        add_event(db, t, p.actor, "priority_changed", body.priority.value)
    if body.note:
        add_event(db, t, p.actor, "internal_note", body.note)
    if body.reply_to_customer:
        conv = db.scalars(select(Conversation).where(Conversation.ticket_id == t.id)).first()
        if conv is None and t.customer.user_id:
            conv = Conversation(business_id=t.business_id, customer_id=t.customer_id, user_id=t.customer.user_id, channel="support", ticket_id=t.id, title=t.subject[:60])
            db.add(conv)
            db.flush()
        if conv is not None:
            db.add(Message(conversation_id=conv.id, role=MessageRole.STAFF, content=body.reply_to_customer, meta={"author": p.user.full_name}))
        add_event(db, t, p.actor, "staff_reply", body.reply_to_customer[:300])
        notify_customer(db, customer_id=t.customer_id, type_=NotificationType.TICKET_UPDATED, title=f"New reply on ticket #{t.ticket_number}", body=body.reply_to_customer[:200], link=f"/customer/tickets/{t.id}")
    if body.status:
        set_status(db, t, body.status, actor=p.actor, detail=body.note, resolved_by="HUMAN")
    db.commit()
    return ticket_out(t, detail=True)


@router.get("/staff")
def staff(p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    from app.models.enums import STAFF_ROLES

    return [{"id": str(u.id), "full_name": u.full_name, "role": u.role.value} for u in db.scalars(select(User).where(User.business_id == p.business_id, User.role.in_(STAFF_ROLES)))]


# ------------------------------------------------------------------------------------ approvals
@router.get("/approvals")
def list_approvals(status: ApprovalStatus | None = None, limit: int = Query(50, le=200), offset: int = 0, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(ApprovalRequest).where(ApprovalRequest.business_id == p.business_id)
    if status:
        stmt = stmt.where(ApprovalRequest.status == status)
    rows, total = _page(db, stmt.order_by(ApprovalRequest.created_at.desc()), limit, offset)
    items = []
    for a in rows:
        out = approval_out(a)
        refund = db.scalars(select(Refund).where(Refund.execution_action_id == a.execution_action_id)).first()
        out["refund"] = refund_out(refund) if refund else None
        items.append(out)
    return {"items": items, "total": total}


def _approval(db: Session, p: Principal, approval_id: uuid.UUID) -> ApprovalRequest:
    a = db.get(ApprovalRequest, approval_id)
    if a is None or a.business_id != p.business_id:
        raise NotFound("Approval not found")
    return a


@router.get("/approvals/{approval_id}")
def approval_detail(approval_id: uuid.UUID, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    a = _approval(db, p, approval_id)
    out = approval_out(a)
    refund = db.scalars(select(Refund).where(Refund.execution_action_id == a.execution_action_id)).first()
    out["refund"] = refund_out(refund) if refund else None
    if refund:
        order = db.get(Order, refund.order_id)
        out["order"] = order_out(order, detail=True) if order else None
        out["customer"] = customer_out(refund.customer)
        pay = db.get(Payment, refund.payment_id)
        out["payment"] = payment_out(pay) if pay else None
        out["customer_refund_history"] = [refund_out(r) for r in db.scalars(select(Refund).where(Refund.customer_id == refund.customer_id, Refund.id != refund.id).order_by(Refund.created_at.desc()).limit(10))]
        # Live preview of what revalidation will see right now
        if order and pay:
            risk = assess_refund_risk(db, order=order, payment=pay, amount=refund.amount)
            out["current_check"] = {"refundable_amount": str(pay.refundable_amount), "payment_status": pay.status.value, "risk": risk.to_dict(), "paypal_capture": pay.paypal_capture_id, "is_sample": pay.source.value == "SEED_SAMPLE"}
        cur = active_version(db, p.business_id, ActionType.INITIATE_REFUND)
        out["current_policy_version"] = cur[1].version if cur else None
    if a.action and a.action.agent_execution_id:
        ex = db.get(AgentExecution, a.action.agent_execution_id)
        out["agent_execution"] = execution_out(ex) if ex else None
    return out


class DecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


@router.post("/approvals/{approval_id}/approve")
def approve(approval_id: uuid.UUID, body: DecisionIn, p: Principal = Depends(require_manager), db: Session = Depends(get_db)) -> dict[str, Any]:
    a = _approval(db, p, approval_id)
    outcome = ExecutionEngine(db).approve(a, manager=p.user, note=body.note)
    return {**outcome.summary, "approval": approval_out(a)}


@router.post("/approvals/{approval_id}/reject")
def reject(approval_id: uuid.UUID, body: DecisionIn, p: Principal = Depends(require_manager), db: Session = Depends(get_db)) -> dict[str, Any]:
    a = _approval(db, p, approval_id)
    if not body.note:
        raise ValidationFailed("A note is required when rejecting")
    outcome = ExecutionEngine(db).reject(a, manager=p.user, note=body.note)
    return {**outcome.summary, "approval": approval_out(a)}


# ------------------------------------------------------------------------------------ policies
def _policy_out(db: Session, pol: BusinessPolicy) -> dict[str, Any]:
    versions = db.scalars(select(PolicyVersion).where(PolicyVersion.policy_id == pol.id).order_by(PolicyVersion.version.desc())).all()
    cur = active_version(db, pol.business_id, pol.action_type)
    now = utcnow()
    return jsonable(
        {
            "id": pol.id,
            "key": pol.key,
            "name": pol.name,
            "action_type": pol.action_type,
            "description": pol.description,
            "is_active": pol.is_active,
            "current_version": pol.current_version,
            "active_version": cur[1].version if cur and cur[0].id == pol.id else None,
            "versions": [
                {
                    "id": v.id,
                    "version": v.version,
                    "rules": v.rules,
                    "default_outcome": v.default_outcome,
                    "effective_from": v.effective_from,
                    "effective_to": v.effective_to,
                    "change_note": v.change_note,
                    "created_at": v.created_at,
                    "status": "scheduled" if v.effective_from > now else ("active" if v.effective_to is None or v.effective_to > now else "retired"),
                }
                for v in versions
            ],
            "decision_count": db.scalar(select(func.count(PolicyDecision.id)).where(PolicyDecision.policy_id == pol.id)) or 0,
        }
    )


@router.get("/policies")
def list_policies(p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    pols = db.scalars(select(BusinessPolicy).where(BusinessPolicy.business_id == p.business_id).order_by(BusinessPolicy.name)).all()
    return {"items": [_policy_out(db, x) for x in pols], "facts": FACT_CATALOG, "operators": list(OPERATORS), "outcomes": [o.value for o in DecisionOutcome]}


class PolicyIn(BaseModel):
    key: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=2, max_length=200)
    action_type: ActionType
    description: str | None = None
    rules: list[dict[str, Any]]
    default_outcome: DecisionOutcome = DecisionOutcome.REQUIRES_APPROVAL
    effective_from: datetime | None = None
    change_note: str | None = None


@router.post("/policies")
def create_policy(body: PolicyIn, p: Principal = Depends(require_manager), db: Session = Depends(get_db)) -> dict[str, Any]:
    existing = db.scalars(select(BusinessPolicy).where(BusinessPolicy.business_id == p.business_id, BusinessPolicy.action_type == body.action_type, BusinessPolicy.is_active.is_(True))).first()
    pol = BusinessPolicy(business_id=p.business_id, key=body.key, name=body.name, action_type=body.action_type, description=body.description, is_active=existing is None, current_version=0)
    db.add(pol)
    db.flush()
    create_version(db, policy=pol, rules=body.rules, default_outcome=body.default_outcome, effective_from=body.effective_from, change_note=body.change_note or "Initial version", user_id=p.user_id)
    db.commit()
    return _policy_out(db, pol)


class PolicyUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    rules: list[dict[str, Any]] | None = None
    default_outcome: DecisionOutcome | None = None
    effective_from: datetime | None = None
    change_note: str | None = None


@router.put("/policies/{policy_id}")
def update_policy(policy_id: uuid.UUID, body: PolicyUpdateIn, p: Principal = Depends(require_manager), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Editing rules creates a new immutable version; prior decisions keep pointing at the version used."""
    pol = get_policy(db, p.business_id, policy_id)
    if body.name:
        pol.name = body.name
    if body.description is not None:
        pol.description = body.description
    if body.is_active is not None:
        if body.is_active:
            for other in db.scalars(select(BusinessPolicy).where(BusinessPolicy.business_id == p.business_id, BusinessPolicy.action_type == pol.action_type, BusinessPolicy.id != pol.id)):
                other.is_active = False
        pol.is_active = body.is_active
    if body.rules is not None:
        latest = db.scalars(select(PolicyVersion).where(PolicyVersion.policy_id == pol.id).order_by(PolicyVersion.version.desc())).first()
        create_version(db, policy=pol, rules=body.rules, default_outcome=body.default_outcome or (latest.default_outcome if latest else DecisionOutcome.REQUIRES_APPROVAL), effective_from=body.effective_from, change_note=body.change_note, user_id=p.user_id)
    db.commit()
    return _policy_out(db, pol)


class EvaluateIn(BaseModel):
    action_type: ActionType = ActionType.INITIATE_REFUND
    order_id: uuid.UUID | None = None
    amount: Decimal | None = None
    facts: dict[str, Any] | None = None
    rules: list[dict[str, Any]] | None = None  # optional draft rules to test before saving
    default_outcome: DecisionOutcome | None = None


@router.post("/policies/evaluate")
def evaluate_policy(body: EvaluateIn, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Dry-run: evaluates without recording a decision or executing anything."""
    facts: dict[str, Any] = dict(body.facts or {})
    risk = None
    if body.order_id:
        o = _get_order(db, p, body.order_id)
        pay = latest_payment(db, o.id)
        amount = body.amount if body.amount is not None else (pay.refundable_amount if pay else None)
        risk = assess_refund_risk(db, order=o, payment=pay, amount=amount)
        facts = {**refund_facts(db, order=o, payment=pay, amount=amount, risk=risk), **facts}
    if body.rules is not None:
        from app.policies.engine import validate_rules

        problems = validate_rules(body.rules)
        if problems:
            raise ValidationFailed("Draft rules are invalid", details=problems)
        ev = evaluate(body.action_type, body.rules, body.default_outcome or DecisionOutcome.REQUIRES_APPROVAL, facts)
        version = None
    else:
        cur = active_version(db, p.business_id, body.action_type)
        if cur is None:
            raise NotFound("No active policy for this action type")
        ev = evaluate(body.action_type, cur[1].rules, cur[1].default_outcome, facts)
        version = cur[1].version
    return jsonable({"outcome": ev.outcome, "matched_rule_id": ev.matched_rule_id, "matched_rule_name": ev.matched_rule_name, "explanation": ev.explanation, "evaluated": ev.evaluated_conditions(), "facts": facts, "policy_version": version, "risk": risk.to_dict() if risk else None, "missing_facts": ev.missing_facts})


@router.get("/policies/decisions")
def decisions(outcome: DecisionOutcome | None = None, limit: int = Query(50, le=200), offset: int = 0, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(PolicyDecision).where(PolicyDecision.business_id == p.business_id)
    if outcome:
        stmt = stmt.where(PolicyDecision.outcome == outcome)
    rows, total = _page(db, stmt.order_by(PolicyDecision.created_at.desc()), limit, offset)
    return {"items": [decision_out(d) for d in rows], "total": total}


# ------------------------------------------------------------------------------------ agents
@router.get("/agents/executions")
def executions(workflow: str | None = None, status: str | None = None, limit: int = Query(50, le=200), offset: int = 0, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(AgentExecution).where(AgentExecution.business_id == p.business_id).options(selectinload(AgentExecution.tool_calls))
    if workflow:
        stmt = stmt.where(AgentExecution.workflow == workflow)
    if status:
        stmt = stmt.where(AgentExecution.status == status)
    rows, total = _page(db, stmt.order_by(AgentExecution.created_at.desc()), limit, offset)
    return {"items": [execution_out(e) for e in rows], "total": total}


@router.get("/agents/executions/{execution_id}")
def execution_detail(execution_id: uuid.UUID, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    e = db.get(AgentExecution, execution_id)
    if e is None or e.business_id != p.business_id:
        raise NotFound("Execution not found")
    data = execution_out(e, detail=True)
    data["decisions"] = [decision_out(d) for d in db.scalars(select(PolicyDecision).where(PolicyDecision.agent_execution_id == e.id))]
    data["actions"] = [action_out(a) for a in db.scalars(select(ExecutionAction).where(ExecutionAction.agent_execution_id == e.id))]
    return data


# ------------------------------------------------------------------------------------ audit + notifications
@router.get("/audit-logs")
def audit_logs(action: str | None = None, entity_type: str | None = None, entity_id: str | None = None, actor_type: str | None = None, limit: int = Query(100, le=500), offset: int = 0, p: Principal = Depends(require_manager), db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(AuditLog).where(AuditLog.business_id == p.business_id)
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"{action}%"))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if actor_type:
        stmt = stmt.where(AuditLog.actor_type == actor_type)
    rows, total = _page(db, stmt.order_by(AuditLog.created_at.desc()), limit, offset)
    return {"items": [audit_out(a) for a in rows], "total": total}


@router.get("/notifications")
def notifications(unread_only: bool = False, limit: int = Query(50, le=200), p: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(Notification).where(Notification.user_id == p.user_id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = db.scalars(stmt.order_by(Notification.created_at.desc()).limit(limit)).all()
    unread = db.scalar(select(func.count(Notification.id)).where(Notification.user_id == p.user_id, Notification.read_at.is_(None))) or 0
    return {"items": [notification_out(n) for n in rows], "unread": unread}


@router.post("/notifications/read-all")
def read_all(p: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    for n in db.scalars(select(Notification).where(Notification.user_id == p.user_id, Notification.read_at.is_(None))):
        n.read_at = utcnow()
    db.commit()
    return {"ok": True}


@router.post("/notifications/{notification_id}/read")
def read_one(notification_id: uuid.UUID, p: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != p.user_id:
        raise NotFound("Notification not found")
    n.read_at = n.read_at or utcnow()
    db.commit()
    return notification_out(n)
