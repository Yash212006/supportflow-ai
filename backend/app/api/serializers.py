"""Response serialisers. Explicit field lists so internal columns (password hashes, raw payloads)
never leak by accident."""

from __future__ import annotations

from typing import Any

from app.models import (
    AgentExecution,
    ApprovalRequest,
    AuditLog,
    Customer,
    ExecutionAction,
    Message,
    Notification,
    Order,
    Payment,
    PolicyDecision,
    Product,
    Refund,
    SupportTicket,
    User,
)
from app.services.audit import jsonable


def j(v: Any) -> Any:
    return jsonable(v)


def user_out(u: User) -> dict[str, Any]:
    return {"id": str(u.id), "email": u.email, "full_name": u.full_name, "role": u.role.value, "business_id": str(u.business_id)}


def customer_out(c: Customer) -> dict[str, Any]:
    return j({"id": c.id, "email": c.email, "full_name": c.full_name, "phone": c.phone, "city": c.city, "segment": c.segment, "created_at": c.created_at})


def product_out(p: Product) -> dict[str, Any]:
    return j({"id": p.id, "sku": p.sku, "name": p.name, "category": p.category, "description": p.description, "price": p.price, "image_url": p.image_url, "refundable_days": p.refundable_days})


def payment_out(p: Payment) -> dict[str, Any]:
    return j(
        {
            "id": p.id,
            "order_id": p.order_id,
            "order_number": p.order.order_number if p.order else None,
            "customer_id": p.customer_id,
            "customer_name": p.customer.full_name if p.customer else None,
            "attempt": p.attempt,
            "source": p.source,
            "is_sample": p.source.value == "SEED_SAMPLE",
            "method": p.method,
            "status": p.status,
            "amount": p.amount,
            "refunded_amount": p.refunded_amount,
            "refundable_amount": p.refundable_amount,
            "currency": p.currency,
            "paypal_order_id": p.paypal_order_id,
            "paypal_capture_id": p.paypal_capture_id,
            "approve_url": p.approve_url,
            "payer_email": p.payer_email,
            "failure_reason": p.failure_reason,
            "captured_at": p.captured_at,
            "created_at": p.created_at,
        }
    )


def refund_out(r: Refund) -> dict[str, Any]:
    return j(
        {
            "id": r.id,
            "payment_id": r.payment_id,
            "order_id": r.order_id,
            "order_number": r.order.order_number if r.order else None,
            "customer_id": r.customer_id,
            "customer_name": r.customer.full_name if r.customer else None,
            "ticket_id": r.ticket_id,
            "capture_id": r.payment.paypal_capture_id if r.payment else None,
            "amount": r.amount,
            "currency": r.currency,
            "reason": r.reason,
            "status": r.status,
            "is_sample": r.is_sample,
            "paypal_refund_id": r.paypal_refund_id,
            "paypal_status": r.paypal_status,
            "paypal_status_reason": r.paypal_status_reason,
            "failure_reason": r.failure_reason,
            "policy_decision_id": r.policy_decision_id,
            "execution_action_id": r.execution_action_id,
            "executed_at": r.executed_at,
            "completed_at": r.completed_at,
            "created_at": r.created_at,
        }
    )


def order_out(o: Order, *, detail: bool = False) -> dict[str, Any]:
    latest = sorted(o.payments, key=lambda p: p.attempt)[-1] if o.payments else None
    shipment = sorted(o.shipments, key=lambda s: s.created_at)[-1] if o.shipments else None
    data: dict[str, Any] = {
        "id": o.id,
        "order_number": o.order_number,
        "customer_id": o.customer_id,
        "customer_name": o.customer.full_name if o.customer else None,
        "customer_email": o.customer.email if o.customer else None,
        "status": o.status,
        "currency": o.currency,
        "total_amount": o.total_amount,
        "is_sample": o.is_sample,
        "placed_at": o.placed_at,
        "delivered_at": o.delivered_at,
        "item_count": sum(i.quantity for i in o.items),
        "items_summary": ", ".join(f"{i.quantity}× {i.product.name}" for i in o.items),
        "payment_status": latest.status if latest else None,
        "payment_id": latest.id if latest else None,
        "shipment_status": shipment.status if shipment else None,
    }
    if detail:
        data["items"] = [
            {"id": i.id, "product_id": i.product_id, "product_name": i.product.name, "sku": i.product.sku, "category": i.product.category, "quantity": i.quantity, "unit_price": i.unit_price}
            for i in o.items
        ]
        data["shipments"] = [
            {"id": s.id, "carrier": s.carrier, "tracking_number": s.tracking_number, "status": s.status, "estimated_delivery": s.estimated_delivery, "delivered_at": s.delivered_at, "last_event": s.last_event}
            for s in o.shipments
        ]
        data["payments"] = [payment_out(p) for p in sorted(o.payments, key=lambda p: p.attempt)]
        data["notes"] = o.notes
    return j(data)


def ticket_out(t: SupportTicket, *, detail: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": t.id,
        "ticket_number": t.ticket_number,
        "customer_id": t.customer_id,
        "customer_name": t.customer.full_name if t.customer else None,
        "order_id": t.order_id,
        "subject": t.subject,
        "description": t.description,
        "status": t.status,
        "priority": t.priority,
        "category": t.category,
        "ai_classification_confidence": t.ai_classification_confidence,
        "assigned_to": t.assigned_to.full_name if t.assigned_to else None,
        "assigned_to_user_id": t.assigned_to_user_id,
        "resolved_by": t.resolved_by,
        "resolution_summary": t.resolution_summary,
        "satisfaction_score": t.satisfaction_score,
        "is_sample": t.is_sample,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "resolved_at": t.resolved_at,
        "reopened_count": t.reopened_count,
    }
    if detail:
        data["events"] = [{"id": e.id, "actor": e.actor, "event": e.event, "detail": e.detail, "created_at": e.created_at} for e in t.events]
    return j(data)


def message_out(m: Message) -> dict[str, Any]:
    return j({"id": m.id, "role": m.role, "content": m.content, "meta": m.meta, "agent_execution_id": m.agent_execution_id, "created_at": m.created_at})


def notification_out(n: Notification) -> dict[str, Any]:
    return j({"id": n.id, "type": n.type, "title": n.title, "body": n.body, "link": n.link, "read_at": n.read_at, "created_at": n.created_at})


def decision_out(d: PolicyDecision) -> dict[str, Any]:
    return j(
        {
            "id": d.id,
            "policy_id": d.policy_id,
            "policy_version": d.policy_version,
            "action_type": d.action_type,
            "outcome": d.outcome,
            "matched_rule_id": d.matched_rule_id,
            "inputs": d.inputs,
            "evaluated_conditions": d.evaluated_conditions,
            "explanation": d.explanation,
            "customer_id": d.customer_id,
            "order_id": d.order_id,
            "payment_id": d.payment_id,
            "agent_execution_id": d.agent_execution_id,
            "risk_level": d.risk_level,
            "created_at": d.created_at,
        }
    )


def action_out(a: ExecutionAction) -> dict[str, Any]:
    return j(
        {
            "id": a.id,
            "action_type": a.action_type,
            "state": a.state,
            "idempotency_key": a.idempotency_key,
            "payload": a.payload,
            "result": a.result,
            "error_code": a.error_code,
            "error_message": a.error_message,
            "attempts": a.attempts,
            "history": a.history,
            "requested_by": a.requested_by,
            "policy_decision_id": a.policy_decision_id,
            "agent_execution_id": a.agent_execution_id,
            "order_id": a.order_id,
            "payment_id": a.payment_id,
            "ticket_id": a.ticket_id,
            "executed_at": a.executed_at,
            "created_at": a.created_at,
        }
    )


def approval_out(a: ApprovalRequest) -> dict[str, Any]:
    return j(
        {
            "id": a.id,
            "status": a.status,
            "title": a.title,
            "reason": a.reason,
            "proposed_by": a.proposed_by,
            "risk_level": a.risk_level,
            "risk_summary": a.risk_summary,
            "decided_by": a.decided_by.full_name if a.decided_by else None,
            "decided_at": a.decided_at,
            "manager_note": a.manager_note,
            "final_result": a.final_result,
            "is_sample": a.is_sample,
            "created_at": a.created_at,
            "action": action_out(a.action) if a.action else None,
            "decision": decision_out(a.decision) if a.decision else None,
            "history": [{"user": x.user.full_name, "action": x.action, "note": x.note, "revalidation": x.revalidation, "at": x.created_at} for x in a.approval_actions],
        }
    )


def execution_out(e: AgentExecution, *, detail: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": e.id,
        "workflow": e.workflow,
        "status": e.status,
        "intent": e.intent,
        "llm_mode": e.llm_mode,
        "input_summary": e.input_summary,
        "outcome_summary": e.outcome_summary,
        "decision_outcome": e.decision_outcome,
        "resolved_autonomously": e.resolved_autonomously,
        "required_human": e.required_human,
        "error": e.error,
        "duration_ms": e.duration_ms,
        "ticket_id": e.ticket_id,
        "order_id": e.order_id,
        "conversation_id": e.conversation_id,
        "is_sample": e.is_sample,
        "created_at": e.created_at,
        "finished_at": e.finished_at,
        "agents": sorted({s.get("agent", "") for s in (e.steps or []) if s.get("agent")}),
        "tool_count": len(e.tool_calls),
    }
    if detail:
        data["steps"] = e.steps
        data["tool_calls"] = [
            {"id": t.id, "agent": t.agent, "tool": t.tool, "arguments": t.arguments, "result_summary": t.result_summary, "success": t.success, "authorized": t.authorized, "duration_ms": t.duration_ms, "created_at": t.created_at}
            for t in e.tool_calls
        ]
    return j(data)


def audit_out(a: AuditLog) -> dict[str, Any]:
    return j({"id": a.id, "actor_type": a.actor_type, "actor_id": a.actor_id, "action": a.action, "entity_type": a.entity_type, "entity_id": a.entity_id, "summary": a.summary, "data": a.data, "created_at": a.created_at})
