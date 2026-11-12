"""Manager Copilot: a LangGraph ReAct agent over restricted, read-only, tenant-scoped tools.

The copilot can never execute financial actions. `prepare_refund_proposal` only dry-runs the policy
engine and returns a proposal; the manager submits it through the normal refund API, where the
execution engine and policy engine apply.

Without an LLM configured the copilot uses a transparent intent router over the same tools.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.agents.llm import get_chat_model, llm_mode
from app.agents.tooling import ToolContext, ToolRunner, Tracer
from app.analytics import service as analytics
from app.core.database import utcnow
from app.core.deps import Principal
from app.knowledge.service import search as kb_search
from app.models import (
    AgentExecution,
    ApprovalRequest,
    Conversation,
    Customer,
    Message,
    Order,
    Payment,
    PolicyDecision,
    Refund,
    SupportTicket,
)
from app.models.enums import (
    ActionType,
    ApprovalStatus,
    ExecutionStatus,
    MessageRole,
    PaymentStatus,
    RefundStatus,
    TicketStatus,
)
from app.policies.engine import evaluate
from app.policies.facts import assess_refund_risk, latest_payment, refund_facts
from app.policies.service import active_version
from app.services.audit import jsonable

AGENT = "manager_copilot"


# ------------------------------------------------------------------------------------ tools
def _money(v: Any) -> float:
    return float(v or 0)


def search_orders(ctx: ToolContext, query: str = "", status: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    stmt = select(Order).where(Order.business_id == ctx.business_id).options(selectinload(Order.customer), selectinload(Order.payments))
    q = (query or "").strip().lstrip("#")
    if q.isdigit():
        stmt = stmt.where(Order.order_number == int(q))
    elif q:
        stmt = stmt.join(Customer, Customer.id == Order.customer_id).where(or_(Customer.full_name.ilike(f"%{q}%"), Customer.email.ilike(f"%{q}%")))
    if status:
        stmt = stmt.where(Order.status == status.upper())
    rows = ctx.db.scalars(stmt.order_by(Order.placed_at.desc()).limit(min(limit, 50))).all()
    return [jsonable({"order_id": o.id, "order_number": o.order_number, "customer": o.customer.full_name, "status": o.status, "total": o.total_amount, "currency": o.currency, "placed_at": o.placed_at, "payment_status": (sorted(o.payments, key=lambda p: p.attempt)[-1].status if o.payments else None), "link": f"/manager/orders/{o.id}"}) for o in rows]


def get_order(ctx: ToolContext, order_number: int) -> dict[str, Any] | None:
    o = ctx.db.scalars(select(Order).where(Order.business_id == ctx.business_id, Order.order_number == int(order_number))).first()
    if not o:
        return None
    refunds = ctx.db.scalars(select(Refund).where(Refund.order_id == o.id)).all()
    return jsonable({"order_id": o.id, "order_number": o.order_number, "customer": o.customer.full_name, "status": o.status, "total": o.total_amount, "currency": o.currency, "items": [f"{i.quantity}× {i.product.name}" for i in o.items], "payments": [{"status": p.status, "amount": p.amount, "refunded": p.refunded_amount, "paypal_capture_id": p.paypal_capture_id, "source": p.source} for p in o.payments], "refunds": [{"amount": r.amount, "status": r.status, "reason": r.reason} for r in refunds], "link": f"/manager/orders/{o.id}"})


def search_customers(ctx: ToolContext, query: str = "", with_open_tickets: bool = False, limit: int = 15) -> list[dict[str, Any]]:
    stmt = select(Customer).where(Customer.business_id == ctx.business_id)
    if query:
        stmt = stmt.where(or_(Customer.full_name.ilike(f"%{query}%"), Customer.email.ilike(f"%{query}%")))
    if with_open_tickets:
        sub = select(SupportTicket.customer_id).where(SupportTicket.business_id == ctx.business_id, SupportTicket.status.notin_((TicketStatus.RESOLVED, TicketStatus.CLOSED)))
        stmt = stmt.where(Customer.id.in_(sub))
    rows = ctx.db.scalars(stmt.limit(min(limit, 50))).all()
    out = []
    for c in rows:
        open_n = ctx.db.scalar(select(func.count(SupportTicket.id)).where(SupportTicket.customer_id == c.id, SupportTicket.status.notin_((TicketStatus.RESOLVED, TicketStatus.CLOSED)))) or 0
        out.append({"customer_id": str(c.id), "name": c.full_name, "email": c.email, "city": c.city, "open_tickets": open_n, "link": f"/manager/customers/{c.id}"})
    return out


def search_payments(ctx: ToolContext, status: str | None = None, since_days: int | None = None, limit: int = 20) -> list[dict[str, Any]]:
    stmt = select(Payment).where(Payment.business_id == ctx.business_id).options(selectinload(Payment.order), selectinload(Payment.customer))
    if status:
        sts = [s.strip().upper() for s in status.split(",")]
        stmt = stmt.where(Payment.status.in_(sts))
    if since_days is not None:
        stmt = stmt.where(Payment.created_at >= utcnow() - timedelta(days=since_days))
    rows = ctx.db.scalars(stmt.order_by(Payment.created_at.desc()).limit(min(limit, 100))).all()
    return [jsonable({"payment_id": p.id, "order_number": p.order.order_number, "customer": p.customer.full_name, "status": p.status, "amount": p.amount, "currency": p.currency, "paypal_order_id": p.paypal_order_id, "failure_reason": p.failure_reason, "created_at": p.created_at, "source": p.source, "link": f"/manager/payments/{p.id}"}) for p in rows]


def search_refunds(ctx: ToolContext, status: str | None = None, min_amount: float | None = None, limit: int = 25) -> list[dict[str, Any]]:
    stmt = select(Refund).where(Refund.business_id == ctx.business_id).options(selectinload(Refund.order), selectinload(Refund.customer))
    if status:
        s = status.upper()
        if s == "PENDING_ANY":
            stmt = stmt.where(Refund.status.in_((RefundStatus.REQUESTED, RefundStatus.AWAITING_APPROVAL, RefundStatus.PENDING, RefundStatus.OUTCOME_UNKNOWN)))
        else:
            stmt = stmt.where(Refund.status.in_([x.strip() for x in s.split(",")]))
    if min_amount is not None:
        stmt = stmt.where(Refund.amount > Decimal(str(min_amount)))
    rows = ctx.db.scalars(stmt.order_by(Refund.amount.desc()).limit(min(limit, 100))).all()
    return [jsonable({"refund_id": r.id, "order_number": r.order.order_number, "customer": r.customer.full_name, "amount": r.amount, "currency": r.currency, "status": r.status, "paypal_status": r.paypal_status, "reason": r.reason, "created_at": r.created_at, "link": f"/manager/refunds/{r.id}"}) for r in rows]


def search_tickets(ctx: ToolContext, status: str | None = None, category: str | None = None, open_only: bool = False, limit: int = 25) -> list[dict[str, Any]]:
    stmt = select(SupportTicket).where(SupportTicket.business_id == ctx.business_id).options(selectinload(SupportTicket.customer))
    if status:
        stmt = stmt.where(SupportTicket.status == status.upper())
    if open_only:
        stmt = stmt.where(SupportTicket.status.notin_((TicketStatus.RESOLVED, TicketStatus.CLOSED)))
    if category:
        stmt = stmt.where(SupportTicket.category == category.upper())
    rows = ctx.db.scalars(stmt.order_by(SupportTicket.created_at.desc()).limit(min(limit, 100))).all()
    return [jsonable({"ticket_id": t.id, "ticket_number": t.ticket_number, "customer": t.customer.full_name, "subject": t.subject, "category": t.category, "status": t.status, "priority": t.priority, "created_at": t.created_at, "link": f"/manager/tickets/{t.id}"}) for t in rows]


def list_pending_approvals(ctx: ToolContext) -> list[dict[str, Any]]:
    rows = ctx.db.scalars(select(ApprovalRequest).where(ApprovalRequest.business_id == ctx.business_id, ApprovalRequest.status == ApprovalStatus.PENDING).order_by(ApprovalRequest.created_at)).all()
    return [jsonable({"approval_id": a.id, "title": a.title, "reason": a.reason, "risk_level": a.risk_level, "proposed_by": a.proposed_by, "created_at": a.created_at, "link": f"/manager/approvals/{a.id}"}) for a in rows]


def get_policies(ctx: ToolContext) -> list[dict[str, Any]]:
    out = []
    for at in (ActionType.INITIATE_REFUND, ActionType.CANCEL_ORDER):
        found = active_version(ctx.db, ctx.business_id, at)
        if found:
            p, v = found
            out.append(jsonable({"policy": p.name, "action_type": at, "version": v.version, "effective_from": v.effective_from, "default_outcome": v.default_outcome, "rules": [{"id": r["id"], "name": r.get("name"), "priority": r.get("priority"), "match": r.get("match", "all"), "conditions": r.get("conditions"), "outcome": r["outcome"]} for r in v.rules]}))
    return out


def explain_decision(ctx: ToolContext, order_number: int | None = None, refund_id: str | None = None) -> dict[str, Any] | None:
    d = None
    if refund_id:
        r = ctx.db.get(Refund, uuid.UUID(refund_id))
        if r and r.business_id == ctx.business_id and r.policy_decision_id:
            d = ctx.db.get(PolicyDecision, r.policy_decision_id)
    elif order_number is not None:
        o = ctx.db.scalars(select(Order).where(Order.business_id == ctx.business_id, Order.order_number == int(order_number))).first()
        if o:
            d = ctx.db.scalars(select(PolicyDecision).where(PolicyDecision.order_id == o.id).order_by(PolicyDecision.created_at.desc())).first()
    if d is None:
        return None
    failed = [c for rule in d.evaluated_conditions for c in rule["conditions"] if rule.get("matched")]
    return jsonable({"decision_id": d.id, "outcome": d.outcome, "policy_version": d.policy_version, "matched_rule": d.matched_rule_id, "explanation": d.explanation, "matched_conditions": failed, "inputs": {k: d.inputs.get(k) for k in ("refund_amount", "order_total", "payment_status", "risk_level", "customer_refunds_90d", "within_refund_window", "prior_refund_on_payment")}, "risk_level": d.risk_level, "created_at": d.created_at})


def get_analytics_summary(ctx: ToolContext, days: int = 30) -> dict[str, Any]:
    o = analytics.overview(ctx.db, ctx.business_id, days=days)
    o.pop("series", None)
    return o


def summarize_agent_executions(ctx: ToolContext, days: int = 7, only_failed: bool = False) -> dict[str, Any]:
    since = utcnow() - timedelta(days=days)
    stmt = select(AgentExecution).where(AgentExecution.business_id == ctx.business_id, AgentExecution.created_at >= since)
    if only_failed:
        stmt = stmt.where(AgentExecution.status == ExecutionStatus.FAILED)
    rows = ctx.db.scalars(stmt).all()
    return {
        "count": len(rows),
        "by_status": dict(Counter(e.status.value for e in rows)),
        "by_intent": dict(Counter(e.intent or "—" for e in rows)),
        "by_decision": dict(Counter((e.decision_outcome.value if e.decision_outcome else "NONE") for e in rows)),
        "autonomous": sum(1 for e in rows if e.resolved_autonomously),
        "human_required": sum(1 for e in rows if e.required_human),
        "avg_duration_ms": int(sum(e.duration_ms or 0 for e in rows) / len(rows)) if rows else 0,
        "recent_failures": [{"execution_id": str(e.id), "error": (e.error or "")[:160], "link": f"/manager/ai-operations/{e.id}"} for e in rows if e.status == ExecutionStatus.FAILED][:5],
    }


def autonomy_trend(ctx: ToolContext, weeks: int = 4) -> dict[str, Any]:
    """Weekly autonomous-resolution rate with breakdown of why executions needed humans."""
    now = utcnow()
    out = []
    for w in range(weeks - 1, -1, -1):
        start, end = now - timedelta(days=7 * (w + 1)), now - timedelta(days=7 * w)
        rows = ctx.db.scalars(select(AgentExecution).where(AgentExecution.business_id == ctx.business_id, AgentExecution.workflow == "support", AgentExecution.created_at >= start, AgentExecution.created_at < end)).all()
        reasons: Counter[str] = Counter()
        for e in rows:
            if not e.resolved_autonomously:
                if e.status == ExecutionStatus.FAILED:
                    reasons["agent_failure"] += 1
                elif e.decision_outcome:
                    reasons[f"policy_{e.decision_outcome.value.lower()}"] += 1
                elif e.required_human:
                    reasons[f"escalated_{(e.intent or 'other').lower()}"] += 1
                else:
                    reasons["informational"] += 1
        out.append({"week_start": start.date().isoformat(), "executions": len(rows), "autonomous_rate": round(sum(1 for e in rows if e.resolved_autonomously) / len(rows), 3) if rows else None, "non_autonomous_reasons": dict(reasons.most_common(5))})
    return {"weeks": out}


def top_complaints(ctx: ToolContext, limit: int = 5, days: int = 90) -> list[dict[str, Any]]:
    since = utcnow() - timedelta(days=days)
    rows = ctx.db.execute(select(SupportTicket.category, func.count()).where(SupportTicket.business_id == ctx.business_id, SupportTicket.created_at >= since).group_by(SupportTicket.category).order_by(func.count().desc()).limit(limit)).all()
    out = []
    for cat, n in rows:
        examples = ctx.db.scalars(select(SupportTicket.subject).where(SupportTicket.business_id == ctx.business_id, SupportTicket.category == cat).limit(3)).all()
        out.append({"category": cat.value if cat else "UNCLASSIFIED", "tickets": n, "examples": list(examples)})
    return out


def refund_rate_by_product(ctx: ToolContext, limit: int = 10) -> list[dict[str, Any]]:
    orders = analytics.dataset_orders(ctx.db, ctx.business_id)
    agg: dict[str, dict[str, Any]] = {}
    for o in orders:
        if o["payment_status"] not in ("CAPTURED", "PARTIALLY_REFUNDED", "REFUNDED"):
            continue
        a = agg.setdefault(o["product"], {"product": o["product"], "category": o["category"], "orders": 0, "refunded_orders": 0, "refund_amount": 0.0})
        a["orders"] += 1
        a["refunded_orders"] += o["refunded"]
        a["refund_amount"] += o["refund_amount"]
    out = [{**a, "refund_rate": round(a["refunded_orders"] / a["orders"], 3)} for a in agg.values() if a["orders"]]
    return sorted(out, key=lambda x: (-x["refund_rate"], -x["orders"]))[:limit]


def prepare_refund_proposal(ctx: ToolContext, order_number: int, amount: float | None = None, reason: str = "Manager-initiated refund") -> dict[str, Any]:
    """Dry-run only: evaluates current policy and risk, records nothing, executes nothing."""
    o = ctx.db.scalars(select(Order).where(Order.business_id == ctx.business_id, Order.order_number == int(order_number))).first()
    if o is None:
        return {"error": f"Order #{order_number} not found"}
    pay = latest_payment(ctx.db, o.id)
    amt = Decimal(str(amount)) if amount else (pay.refundable_amount if pay else None)
    risk = assess_refund_risk(ctx.db, order=o, payment=pay, amount=amt)
    facts = refund_facts(ctx.db, order=o, payment=pay, amount=amt, risk=risk)
    found = active_version(ctx.db, ctx.business_id, ActionType.INITIATE_REFUND)
    if not found:
        return {"error": "No active refund policy"}
    ev = evaluate(ActionType.INITIATE_REFUND, found[1].rules, found[1].default_outcome, facts)
    return jsonable({"proposal": {"order_id": o.id, "order_number": o.order_number, "amount": amt, "currency": o.currency, "reason": reason}, "predicted_outcome": ev.outcome, "explanation": ev.explanation, "policy_version": found[1].version, "risk": risk.to_dict(), "is_sample_payment": bool(pay and pay.source.value == "SEED_SAMPLE"), "note": "Not executed. Submit the proposal to route it through the execution engine; the policy engine re-evaluates at submission."})


def search_knowledge_base(ctx: ToolContext, query: str) -> list[dict[str, Any]]:
    return [c.to_dict() for c in kb_search(ctx.db, ctx.business_id, query, k=4)]


COPILOT_TOOLS: dict[str, Callable[..., Any]] = {
    "search_orders": search_orders,
    "get_order": get_order,
    "search_customers": search_customers,
    "search_payments": search_payments,
    "search_refunds": search_refunds,
    "search_tickets": search_tickets,
    "list_pending_approvals": list_pending_approvals,
    "get_policies": get_policies,
    "explain_decision": explain_decision,
    "get_analytics_summary": get_analytics_summary,
    "summarize_agent_executions": summarize_agent_executions,
    "autonomy_trend": autonomy_trend,
    "top_complaints": top_complaints,
    "refund_rate_by_product": refund_rate_by_product,
    "prepare_refund_proposal": prepare_refund_proposal,
    "search_knowledge_base": search_knowledge_base,
}

TOOL_DOCS = {
    "search_orders": "Search orders. Args: query (order number or customer name/email), status (optional), limit.",
    "get_order": "Get one order with payments/refunds. Args: order_number (int).",
    "search_customers": "Search customers. Args: query, with_open_tickets (bool), limit.",
    "search_payments": "Search payments. Args: status (comma list e.g. FAILED,DECLINED), since_days (int), limit.",
    "search_refunds": "Search refunds. Args: status (e.g. AWAITING_APPROVAL, COMPLETED, or PENDING_ANY), min_amount (number), limit.",
    "search_tickets": "Search tickets. Args: status, category, open_only (bool), limit.",
    "list_pending_approvals": "List actions awaiting manager approval. No args.",
    "get_policies": "Read active business policies and their rules. No args.",
    "explain_decision": "Explain the latest policy decision for an order or a refund. Args: order_number or refund_id.",
    "get_analytics_summary": "Business KPIs (revenue, refunds, tickets, AI autonomy). Args: days.",
    "summarize_agent_executions": "Summarise AI agent executions. Args: days, only_failed.",
    "autonomy_trend": "Weekly autonomous-resolution rate and reasons executions needed humans. Args: weeks.",
    "top_complaints": "Most common complaint categories with example subjects. Args: limit, days.",
    "refund_rate_by_product": "Products ranked by refund rate. Args: limit.",
    "prepare_refund_proposal": "DRY-RUN a refund: predicts policy outcome, never executes. Args: order_number, amount (optional), reason.",
    "search_knowledge_base": "Search the company knowledge base. Args: query.",
}


# ------------------------------------------------------------------------------------ agent
COPILOT_SYSTEM = """You are the SupportFlow Manager Copilot for an online retail business.
Answer managers' questions using ONLY the provided tools; never guess numbers. Be concise and structured
(short intro sentence, then bullets or a compact table). Mention record identifiers (order #, ticket #) so the
manager can open them. You cannot execute refunds or any financial action: for such requests call
prepare_refund_proposal and explain that the manager can submit it to the policy-governed execution engine.
Currency: {currency}. Today: {today}."""


def _langchain_tools(runner: ToolRunner) -> list[Any]:
    from langchain_core.tools import StructuredTool

    tools = []
    for name, fn in COPILOT_TOOLS.items():
        def make(n: str, f: Any) -> Any:
            def _call(**kwargs: Any) -> str:
                result = runner.call(AGENT, n, **kwargs)
                runner.collected.append({"tool": n, "args": kwargs, "result": result})  # type: ignore[attr-defined]
                return json.dumps(result, default=str)[:6000]

            import inspect

            sig = inspect.signature(f)
            params = [p for p in list(sig.parameters.values())[1:]]
            _call.__signature__ = sig.replace(parameters=params)  # type: ignore[attr-defined]
            _call.__annotations__ = {p.name: p.annotation for p in params}
            return StructuredTool.from_function(func=_call, name=n, description=TOOL_DOCS[n])

        tools.append(make(name, fn))
    return tools


def route_deterministic(text: str) -> list[tuple[str, dict[str, Any]]]:
    t = text.lower()
    num = re.search(r"#\s?(\d{4,6})|order\s+(\d{4,6})", t)
    order_no = int(num.group(1) or num.group(2)) if num else None
    amt = re.search(r"(?:above|over|more than|greater than|>)\s*(?:₹|rs\.?|\$)?\s*([\d,]+)", t)
    min_amount = float(amt.group(1).replace(",", "")) if amt else None
    plan: list[tuple[str, dict[str, Any]]] = []
    if re.search(r"why|explain", t) and re.search(r"refund|reject|escalat|decision", t) and order_no:
        plan.append(("explain_decision", {"order_number": order_no}))
    elif re.search(r"autonom|resolution rate", t):
        plan += [("autonomy_trend", {"weeks": 4}), ("summarize_agent_executions", {"days": 14})]
    elif re.search(r"(issue|create|start|process|give).*(refund)|refund .*order", t) and order_no:
        plan.append(("prepare_refund_proposal", {"order_number": order_no, "amount": min_amount}))
    elif order_no:
        plan.append(("get_order", {"order_number": order_no}))
    elif "approv" in t or "awaiting" in t:
        plan.append(("list_pending_approvals", {}))
    elif "refund rate" in t and ("product" in t or "highest" in t):
        plan.append(("refund_rate_by_product", {"limit": 10}))
    elif "refund" in t:
        status = "PENDING_ANY" if re.search(r"pending|open|waiting", t) else ("COMPLETED" if "complet" in t else ("FAILED" if "fail" in t else None))
        plan.append(("search_refunds", {"status": status, "min_amount": min_amount}))
    elif re.search(r"fail|declin", t) and "payment" in t:
        plan.append(("search_payments", {"status": "FAILED,DECLINED", "since_days": 1 if "today" in t else 30}))
    elif "payment" in t:
        plan.append(("search_payments", {"since_days": 30}))
    elif re.search(r"complain|common|issues", t):
        plan.append(("top_complaints", {"limit": 5}))
    elif "customer" in t and re.search(r"unresolved|open", t):
        plan.append(("search_customers", {"with_open_tickets": True}))
    elif "ticket" in t:
        plan.append(("search_tickets", {"open_only": bool(re.search(r"open|unresolved", t))}))
    elif re.search(r"agent|execution|ai ", t):
        plan.append(("summarize_agent_executions", {"days": 7, "only_failed": "fail" in t}))
    elif "polic" in t:
        plan.append(("get_policies", {}))
    elif re.search(r"revenue|summary|performance|kpi|how are we|overview", t):
        plan.append(("get_analytics_summary", {"days": 30}))
    else:
        plan.append(("search_knowledge_base", {"query": text}))
    return plan


def _render_fallback(question: str, results: list[dict[str, Any]], currency: str) -> str:
    sym = "₹" if currency == "INR" else "$"
    parts: list[str] = []
    for r in results:
        tool, data = r["tool"], r["result"]
        if isinstance(data, list):
            if not data:
                parts.append(f"No matching records found ({tool.replace('_', ' ')}).")
                continue
            parts.append(f"Found {len(data)} result(s):")
            for row in data[:12]:
                if "refund_id" in row:
                    parts.append(f"- Order #{row['order_number']} · {row['customer']} · {sym}{float(row['amount']):,.2f} · {row['status']}" + (f" (PayPal {row['paypal_status']})" if row.get("paypal_status") else ""))
                elif "ticket_number" in row:
                    parts.append(f"- Ticket #{row['ticket_number']} · {row['customer']} · {row['subject']} · {row['status']} · {row['priority']}")
                elif "order_number" in row and "payment_id" in row:
                    parts.append(f"- Order #{row['order_number']} · {row['customer']} · {sym}{float(row['amount']):,.2f} · {row['status']}" + (f" — {row['failure_reason']}" if row.get("failure_reason") else ""))
                elif "order_number" in row:
                    parts.append(f"- Order #{row['order_number']} · {row['customer']} · {sym}{float(row['total']):,.2f} · {row['status']}")
                elif "approval_id" in row:
                    parts.append(f"- {row['title']} · risk {row.get('risk_level') or '—'}")
                elif "category" in row and "tickets" in row:
                    parts.append(f"- {row['category'].replace('_', ' ').title()}: {row['tickets']} tickets (e.g. “{row['examples'][0] if row['examples'] else ''}”)")
                elif "refund_rate" in row:
                    parts.append(f"- {row['product']} ({row['category']}): {row['refund_rate']:.0%} of {row['orders']} orders refunded")
                elif "name" in row:
                    parts.append(f"- {row['name']} ({row['email']}) · {row['open_tickets']} open ticket(s)")
                elif "title" in row and "content" in row:
                    parts.append(f"- [{row['title']} v{row['version']}] {row['content'][:220]}…")
        elif isinstance(data, dict):
            if tool == "explain_decision":
                parts.append(f"Decision: **{data['outcome']}** (policy v{data['policy_version']}, rule {data['matched_rule'] or 'default'}).\n{data['explanation']}")
            elif tool == "get_order":
                parts.append(f"Order #{data['order_number']} · {data['customer']} · {sym}{float(data['total']):,.2f} · {data['status']}\nItems: {', '.join(data['items'])}\nPayments: " + "; ".join(f"{p['status']} {sym}{float(p['amount']):,.2f}" for p in data["payments"]) + ("\nRefunds: " + "; ".join(f"{sym}{float(x['amount']):,.2f} {x['status']}" for x in data["refunds"]) if data["refunds"] else ""))
            elif tool == "prepare_refund_proposal":
                if "error" in data:
                    parts.append(data["error"])
                else:
                    pr = data["proposal"]
                    parts.append(f"Refund proposal for order #{pr['order_number']}: {sym}{float(pr['amount'] or 0):,.2f}. Predicted policy outcome: **{data['predicted_outcome']}** (v{data['policy_version']}). {data['explanation']}\nRisk: {data['risk']['level']}. Nothing has been executed; submit the proposal to route it through the execution engine.")
            elif tool == "get_analytics_summary":
                parts.append(f"Last 30 days: revenue {sym}{data['revenue']:,.2f}, net {sym}{data['net_revenue']:,.2f}, refunds {sym}{data['refund_volume']:,.2f} ({data['refund_count']}), {data['open_tickets']} open tickets, {data['pending_approvals']} pending approvals, AI autonomous rate {((data['ai_autonomous_rate'] or 0) * 100):.0f}%.")
            elif tool == "autonomy_trend":
                for w in data["weeks"]:
                    rate = f"{w['autonomous_rate']:.0%}" if w["autonomous_rate"] is not None else "n/a"
                    reasons = ", ".join(f"{k} ({v})" for k, v in w["non_autonomous_reasons"].items()) or "—"
                    parts.append(f"- Week of {w['week_start']}: {w['executions']} executions, autonomous {rate}; non-autonomous reasons: {reasons}")
            elif tool == "summarize_agent_executions":
                parts.append(f"{data['count']} executions: {data['autonomous']} autonomous, {data['human_required']} needed a human. By decision: {data['by_decision']}.")
            else:
                parts.append(json.dumps(data, default=str)[:800])
    return "\n".join(parts) or "I couldn't find anything for that question."


def run_copilot(db: Session, *, principal: Principal, message: str, conversation_id: uuid.UUID | None) -> dict[str, Any]:
    from app.models import Business

    started = time.perf_counter()
    if conversation_id:
        conv = db.get(Conversation, conversation_id)
        if conv is None or conv.user_id != principal.user_id:
            from app.core.errors import NotFound

            raise NotFound("Conversation not found")
    else:
        conv = Conversation(business_id=principal.business_id, user_id=principal.user_id, channel="copilot", title=message[:60])
        db.add(conv)
        db.flush()
    db.add(Message(conversation_id=conv.id, role=MessageRole.STAFF, content=message))
    execution = AgentExecution(business_id=principal.business_id, workflow="copilot", status=ExecutionStatus.RUNNING, triggered_by_user_id=principal.user_id, conversation_id=conv.id, llm_mode=llm_mode(), input_summary=message[:500], intent="MANAGER_QUERY")
    db.add(execution)
    db.commit()
    tracer = Tracer(db, execution)
    runner = ToolRunner(ToolContext(db=db, business_id=principal.business_id, user_id=principal.user_id), tracer, COPILOT_TOOLS)
    runner.collected = []  # type: ignore[attr-defined]
    business = db.get(Business, principal.business_id)
    currency = business.currency if business else "USD"
    answer: str | None = None
    model = get_chat_model()
    if model is not None:
        try:
            from langgraph.prebuilt import create_react_agent

            history = db.scalars(select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at)).all()[-10:]
            msgs = [("human" if m.role == MessageRole.STAFF else "ai", m.content) for m in history]
            agent = create_react_agent(model, _langchain_tools(runner), prompt=COPILOT_SYSTEM.format(currency=currency, today=utcnow().date().isoformat()))
            out = agent.invoke({"messages": msgs}, config={"recursion_limit": 12})
            answer = str(out["messages"][-1].content)
            tracer.step(AGENT, "react", f"LLM agent answered using {len(runner.collected)} tool call(s)", tools=[c["tool"] for c in runner.collected])  # type: ignore[attr-defined]
        except Exception as exc:
            tracer.step(AGENT, "llm_error", f"LLM agent failed ({type(exc).__name__}); falling back to deterministic routing")
            answer = None
    if answer is None:
        runner.collected = []  # type: ignore[attr-defined]
        for tool, args in route_deterministic(message):
            result = runner.call(AGENT, tool, **{k: v for k, v in args.items() if v is not None})
            runner.collected.append({"tool": tool, "args": args, "result": result})  # type: ignore[attr-defined]
        answer = _render_fallback(message, runner.collected, currency)  # type: ignore[attr-defined]
        tracer.step(AGENT, "route", f"Deterministic router used {', '.join(c['tool'] for c in runner.collected)}")  # type: ignore[attr-defined]
    cards = [{"tool": c["tool"], "args": jsonable(c["args"]), "result": jsonable(c["result"])} for c in runner.collected]  # type: ignore[attr-defined]
    proposal = next((c["result"] for c in cards if c["tool"] == "prepare_refund_proposal" and isinstance(c["result"], dict) and "proposal" in c["result"]), None)
    tracer.finish(outcome=answer[:500])
    execution.duration_ms = int((time.perf_counter() - started) * 1000)
    reply = Message(conversation_id=conv.id, role=MessageRole.ASSISTANT, content=answer, agent_execution_id=execution.id, meta={"cards": cards, "proposal": proposal, "llm_mode": execution.llm_mode, "execution_id": str(execution.id)})
    db.add(reply)
    db.commit()
    return {"conversation_id": str(conv.id), "answer": answer, "cards": cards, "proposal": proposal, "execution_id": str(execution.id), "llm_mode": execution.llm_mode}


_ = PaymentStatus
