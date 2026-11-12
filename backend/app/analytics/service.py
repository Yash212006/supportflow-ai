"""Analytics: normalised, tenant-scoped, read-only datasets computed from application data.

Used by the manager overview, the Manager Copilot and the AG Studio data sources. No raw SQL from
clients: each dataset is a fixed query with a fixed column list.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import utcnow
from app.models import (
    AgentExecution,
    ApprovalRequest,
    Customer,
    Order,
    Payment,
    PolicyDecision,
    Refund,
    SupportTicket,
)
from app.models.enums import (
    ApprovalStatus,
    ExecutionStatus,
    PaymentStatus,
    RefundStatus,
    TicketStatus,
)

CAPTURED_STATES = (PaymentStatus.CAPTURED, PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED)
DONE_REFUNDS = (RefundStatus.COMPLETED, RefundStatus.PENDING)


def _f(v: Any) -> float:
    return float(v or 0)


def _day(d: datetime | None) -> str | None:
    return d.date().isoformat() if d else None


def _month(d: datetime | None) -> str | None:
    return d.strftime("%Y-%m") if d else None


def _primary(o: Order) -> tuple[str, str]:
    if not o.items:
        return ("—", "—")
    top = max(o.items, key=lambda i: i.unit_price * i.quantity)
    return (top.product.name, top.product.category)


def dataset_orders(db: Session, bid: uuid.UUID) -> list[dict[str, Any]]:
    orders = db.scalars(select(Order).where(Order.business_id == bid).options(selectinload(Order.items), selectinload(Order.payments), selectinload(Order.shipments), selectinload(Order.customer))).all()
    refunds: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for oid, amt in db.execute(select(Refund.order_id, func.sum(Refund.amount)).where(Refund.business_id == bid, Refund.status.in_(DONE_REFUNDS)).group_by(Refund.order_id)):
        refunds[oid] = amt
    rows = []
    for o in orders:
        prod, cat = _primary(o)
        pay = sorted(o.payments, key=lambda p: p.attempt)[-1] if o.payments else None
        ship = sorted(o.shipments, key=lambda s: s.created_at)[-1] if o.shipments else None
        rows.append(
            {
                "order_number": o.order_number,
                "customer": o.customer.full_name,
                "city": o.customer.city or "—",
                "status": o.status.value,
                "order_value": _f(o.total_amount),
                "item_count": sum(i.quantity for i in o.items),
                "product": prod,
                "category": cat,
                "payment_status": pay.status.value if pay else "NONE",
                "payment_method": pay.method if pay else "—",
                "shipment_status": ship.status.value if ship else "NONE",
                "refund_amount": _f(refunds.get(o.id)),
                "refunded": 1 if refunds.get(o.id) else 0,
                "placed_date": _day(o.placed_at),
                "month": _month(o.placed_at),
                "data_origin": "sample" if o.is_sample else "live",
            }
        )
    return rows


def dataset_payments(db: Session, bid: uuid.UUID) -> list[dict[str, Any]]:
    pays = db.scalars(select(Payment).where(Payment.business_id == bid).options(selectinload(Payment.order).selectinload(Order.items), selectinload(Payment.customer))).all()
    rows = []
    for p in pays:
        _, cat = _primary(p.order)
        captured = p.status in CAPTURED_STATES
        rows.append(
            {
                "payment_id": str(p.id)[:8],
                "order_number": p.order.order_number,
                "customer": p.customer.full_name,
                "status": p.status.value,
                "outcome": "captured" if captured else ("failed" if p.status in (PaymentStatus.FAILED, PaymentStatus.DECLINED) else "open"),
                "source": p.source.value,
                "payment_method": p.method,
                "amount": _f(p.amount),
                "captured_amount": _f(p.amount) if captured else 0.0,
                "refunded_amount": _f(p.refunded_amount),
                "net_amount": _f(p.amount - p.refunded_amount) if captured else 0.0,
                "currency": p.currency,
                "category": cat,
                "paypal_order_id": p.paypal_order_id or "",
                "created_date": _day(p.created_at),
                "month": _month(p.created_at),
                "data_origin": "sample" if p.source.value == "SEED_SAMPLE" else "paypal_sandbox",
            }
        )
    return rows


def dataset_refunds(db: Session, bid: uuid.UUID) -> list[dict[str, Any]]:
    refunds = db.scalars(select(Refund).where(Refund.business_id == bid).options(selectinload(Refund.order).selectinload(Order.items), selectinload(Refund.customer))).all()
    decisions = {d.id: d for d in db.scalars(select(PolicyDecision).where(PolicyDecision.business_id == bid))}
    rows = []
    for r in refunds:
        d = decisions.get(r.policy_decision_id) if r.policy_decision_id else None
        prod, cat = _primary(r.order)
        rows.append(
            {
                "refund_id": str(r.id)[:8],
                "order_number": r.order.order_number,
                "customer": r.customer.full_name,
                "amount": _f(r.amount),
                "order_value": _f(r.order.total_amount),
                "refund_ratio": round(_f(r.amount) / _f(r.order.total_amount), 3) if r.order.total_amount else 0,
                "status": r.status.value,
                "paypal_status": r.paypal_status or "—",
                "policy_outcome": d.outcome.value if d else "NONE",
                "risk_level": d.risk_level.value if d and d.risk_level else "—",
                "auto_executed": 1 if d and d.outcome.value == "AUTO_EXECUTE" else 0,
                "reason": (r.reason or "")[:80],
                "product": prod,
                "category": cat,
                "created_date": _day(r.created_at),
                "month": _month(r.created_at),
                "data_origin": "sample" if r.is_sample else "live",
            }
        )
    return rows


def dataset_tickets(db: Session, bid: uuid.UUID) -> list[dict[str, Any]]:
    rows = []
    for t in db.scalars(select(SupportTicket).where(SupportTicket.business_id == bid).options(selectinload(SupportTicket.customer))):
        hours = round((t.resolved_at - t.created_at).total_seconds() / 3600, 2) if t.resolved_at else None
        rows.append(
            {
                "ticket_number": t.ticket_number,
                "customer": t.customer.full_name,
                "category": t.category.value if t.category else "UNCLASSIFIED",
                "status": t.status.value,
                "priority": t.priority.value,
                "resolved_by": t.resolved_by or ("OPEN" if t.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED) else "HUMAN"),
                "resolution_hours": hours if hours is not None else 0.0,
                "is_resolved": 1 if t.resolved_at else 0,
                "is_escalated": 1 if t.escalated_at else 0,
                "csat": t.satisfaction_score or 0,
                "has_csat": 1 if t.satisfaction_score else 0,
                "created_date": _day(t.created_at),
                "month": _month(t.created_at),
                "data_origin": "sample" if t.is_sample else "live",
            }
        )
    return rows


def dataset_agent_executions(db: Session, bid: uuid.UUID) -> list[dict[str, Any]]:
    rows = []
    for e in db.scalars(select(AgentExecution).where(AgentExecution.business_id == bid).options(selectinload(AgentExecution.tool_calls))):
        rows.append(
            {
                "execution_id": str(e.id)[:8],
                "workflow": e.workflow,
                "intent": e.intent or "—",
                "status": e.status.value,
                "decision_outcome": e.decision_outcome.value if e.decision_outcome else "NONE",
                "autonomous": 1 if e.resolved_autonomously else 0,
                "human_required": 1 if e.required_human else 0,
                "failed": 1 if e.status == ExecutionStatus.FAILED else 0,
                "duration_ms": e.duration_ms or 0,
                "tool_calls": len(e.tool_calls),
                "llm_mode": e.llm_mode,
                "created_date": _day(e.created_at),
                "month": _month(e.created_at),
                "data_origin": "sample" if e.is_sample else "live",
            }
        )
    return rows


def dataset_customers(db: Session, bid: uuid.UUID) -> list[dict[str, Any]]:
    orders = dataset_orders(db, bid)
    agg: dict[str, dict[str, Any]] = {}
    for o in orders:
        a = agg.setdefault(o["customer"], {"customer": o["customer"], "city": o["city"], "orders": 0, "total_spent": 0.0, "refunds": 0, "refund_amount": 0.0})
        a["orders"] += 1
        a["total_spent"] += o["order_value"] if o["payment_status"] in ("CAPTURED", "PARTIALLY_REFUNDED", "REFUNDED") else 0
        a["refunds"] += o["refunded"]
        a["refund_amount"] += o["refund_amount"]
    open_t = Counter(t["customer"] for t in dataset_tickets(db, bid) if t["is_resolved"] == 0)
    seg = {c.full_name: c.segment for c in db.scalars(select(Customer).where(Customer.business_id == bid))}
    out = []
    for a in agg.values():
        a["refund_rate"] = round(a["refunds"] / a["orders"], 3) if a["orders"] else 0
        a["open_tickets"] = open_t.get(a["customer"], 0)
        a["segment"] = seg.get(a["customer"], "standard")
        a["total_spent"] = round(a["total_spent"], 2)
        out.append(a)
    return out


def dataset_revenue_daily(db: Session, bid: uuid.UUID) -> list[dict[str, Any]]:
    days: dict[str, dict[str, Any]] = {}
    for p in dataset_payments(db, bid):
        d = days.setdefault(p["created_date"], {"date": p["created_date"], "month": p["month"], "captured": 0.0, "refunded": 0.0, "net": 0.0, "payments": 0, "failed_payments": 0})
        d["payments"] += 1
        d["captured"] += p["captured_amount"]
        d["failed_payments"] += 1 if p["outcome"] == "failed" else 0
    for r in dataset_refunds(db, bid):
        if r["status"] in ("COMPLETED", "PENDING"):
            d = days.setdefault(r["created_date"], {"date": r["created_date"], "month": r["month"], "captured": 0.0, "refunded": 0.0, "net": 0.0, "payments": 0, "failed_payments": 0})
            d["refunded"] += r["amount"]
    for d in days.values():
        d["net"] = round(d["captured"] - d["refunded"], 2)
        d["payment_success_rate"] = round(1 - d["failed_payments"] / d["payments"], 3) if d["payments"] else 1.0
    return sorted(days.values(), key=lambda x: x["date"] or "")


DATASETS = {
    "orders": ("Orders", dataset_orders),
    "payments": ("Payments", dataset_payments),
    "refunds": ("Refunds", dataset_refunds),
    "tickets": ("Support tickets", dataset_tickets),
    "agent_executions": ("AI agent executions", dataset_agent_executions),
    "customers": ("Customer activity", dataset_customers),
    "revenue_daily": ("Revenue & transaction history", dataset_revenue_daily),
}


def overview(db: Session, bid: uuid.UUID, days: int = 30) -> dict[str, Any]:
    since = utcnow() - timedelta(days=days)
    pays = db.scalars(select(Payment).where(Payment.business_id == bid)).all()
    captured = [p for p in pays if p.status in CAPTURED_STATES]
    failed = [p for p in pays if p.status in (PaymentStatus.FAILED, PaymentStatus.DECLINED)]
    refunds = db.scalars(select(Refund).where(Refund.business_id == bid)).all()
    done = [r for r in refunds if r.status in DONE_REFUNDS]
    tickets = db.scalars(select(SupportTicket).where(SupportTicket.business_id == bid)).all()
    open_t = [t for t in tickets if t.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED)]
    resolved = [t for t in tickets if t.resolved_at]
    execs = db.scalars(select(AgentExecution).where(AgentExecution.business_id == bid, AgentExecution.workflow == "support")).all()
    auto = [e for e in execs if e.resolved_autonomously]
    pending_appr = db.scalar(select(func.count(ApprovalRequest.id)).where(ApprovalRequest.business_id == bid, ApprovalRequest.status == ApprovalStatus.PENDING)) or 0
    gross = sum((p.amount for p in captured), Decimal("0"))
    refunded = sum((r.amount for r in done), Decimal("0"))
    res_hours = [(t.resolved_at - t.created_at).total_seconds() / 3600 for t in resolved if t.resolved_at]
    csat = [t.satisfaction_score for t in tickets if t.satisfaction_score]
    series: dict[str, dict[str, float]] = {}
    for p in captured:
        if p.created_at >= since:
            k = p.created_at.date().isoformat()
            series.setdefault(k, {"captured": 0.0, "refunded": 0.0})["captured"] += float(p.amount)
    for r in done:
        if r.created_at >= since:
            k = r.created_at.date().isoformat()
            series.setdefault(k, {"captured": 0.0, "refunded": 0.0})["refunded"] += float(r.amount)
    alerts = []
    if pending_appr:
        alerts.append({"level": "warning", "title": f"{pending_appr} refund approval(s) waiting", "link": "/manager/approvals"})
    unknown = [r for r in refunds if r.status == RefundStatus.OUTCOME_UNKNOWN]
    if unknown:
        alerts.append({"level": "danger", "title": f"{len(unknown)} refund(s) with unknown PayPal outcome need reconciliation", "link": "/manager/refunds"})
    failed_execs = [e for e in execs if e.status == ExecutionStatus.FAILED and e.created_at >= utcnow() - timedelta(days=7)]
    if failed_execs:
        alerts.append({"level": "danger", "title": f"{len(failed_execs)} agent execution(s) failed this week", "link": "/manager/ai-operations"})
    urgent = [t for t in open_t if t.priority.value in ("HIGH", "URGENT")]
    if urgent:
        alerts.append({"level": "warning", "title": f"{len(urgent)} high-priority ticket(s) open", "link": "/manager/tickets"})
    return {
        "currency": db.scalar(select(Order.currency).where(Order.business_id == bid).limit(1)) or "INR",
        "revenue": float(gross),
        "net_revenue": float(gross - refunded),
        "total_payments": len(captured),
        "failed_payments": len(failed),
        "payment_success_rate": round(len(captured) / (len(captured) + len(failed)), 3) if (captured or failed) else None,
        "avg_transaction_value": round(float(gross) / len(captured), 2) if captured else 0,
        "refund_volume": float(refunded),
        "refund_count": len(done),
        "refund_rate": round(len({r.order_id for r in done}) / len(captured), 3) if captured else 0,
        "pending_approvals": pending_appr,
        "open_tickets": len(open_t),
        "resolved_tickets": len(resolved),
        "avg_resolution_hours": round(sum(res_hours) / len(res_hours), 1) if res_hours else None,
        "escalation_rate": round(len([t for t in tickets if t.escalated_at]) / len(tickets), 3) if tickets else 0,
        "csat": round(sum(csat) / len(csat), 2) if csat else None,
        "ai_executions": len(execs),
        "ai_autonomous_rate": round(len(auto) / len(execs), 3) if execs else None,
        "ai_human_rate": round(len([e for e in execs if e.required_human]) / len(execs), 3) if execs else None,
        "series": [{"date": k, **v} for k, v in sorted(series.items())],
        "alerts": alerts,
    }
