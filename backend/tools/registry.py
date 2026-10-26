from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.connection import SessionLocal
from backend.rag.retriever import retrieve_policy
from backend.rules.business_rules import get_business_rules
from backend.services import customer_service, order_service, refund_service, ticket_service
from backend.services.approval_service import create_pending_action, write_audit
from backend.services.resolution_engine import should_escalate


class ToolRuntime:
    def __init__(self, db: Session, requested_by: str = "support_agent") -> None:
        self.db = db
        self.requested_by = requested_by
        self.traces: list[dict[str, Any]] = []
        self.sources: list[dict[str, Any]] = []
        self.last_customer_id: int | None = None
        self.last_order_number: str | None = None
        self.last_ticket_number: str | None = None

    def record(self, name: str, status: str, facts: Any, latency_ms: int) -> None:
        self.traces.append(
            {
                "tool_name": name,
                "status": status,
                "facts": facts,
                "latency_ms": latency_ms,
            }
        )


def _err(message: str) -> str:
    return json.dumps({"ok": False, "error": message})


def _ok(payload: dict) -> str:
    payload = {"ok": True, **payload}
    return json.dumps(payload, default=str)


def wrap(runtime: ToolRuntime, name: str, fn: Callable[[], dict]) -> str:
    start = time.perf_counter()
    try:
        result = fn()
        status = "success" if result.get("ok", True) else "error"
        ms = int((time.perf_counter() - start) * 1000)
        runtime.record(name, status, result, ms)
        write_audit(
            runtime.db,
            action_type="tool_call",
            requested_by=runtime.requested_by,
            tool_name=name,
            parameters={"tool": name},
            result=status,
            latency_ms=ms,
        )
        return json.dumps(result, default=str)
    except Exception as exc:
        ms = int((time.perf_counter() - start) * 1000)
        payload = {"ok": False, "error": f"Tool {name} failed.", "detail": str(exc)}
        runtime.record(name, "error", payload, ms)
        return json.dumps(payload)


class CustomerIdInput(BaseModel):
    customer_id: str = Field(description="Customer code such as CUST001 or numeric id")


class EmailInput(BaseModel):
    email: str


class OrderInput(BaseModel):
    order_number: str


class TicketLookupInput(BaseModel):
    ticket_number: str | None = None
    customer_id: str | None = None


class CreateTicketInput(BaseModel):
    customer_id: str
    subject: str
    description: str
    order_number: str | None = None
    priority: str = "MEDIUM"
    category: str = "GENERAL"


class UpdateTicketInput(BaseModel):
    ticket_number: str
    status: str | None = None
    priority: str | None = None
    category: str | None = None
    resolution: str | None = None


class RefundRequestInput(BaseModel):
    order_number: str
    reason: str
    amount: float | None = None
    ticket_number: str | None = None


class PolicyInput(BaseModel):
    query: str


class EscalateInput(BaseModel):
    ticket_number: str | None = None
    order_number: str | None = None
    reason: str


class ResponseInput(BaseModel):
    context: str = Field(description="Verified facts and policy points to include")


class QueryInput(BaseModel):
    query: str = ""


def _resolve_customer(db: Session, customer_id: str):
    customer_id = customer_id.strip()
    if customer_id.isdigit():
        return customer_service.get_customer_by_id(db, int(customer_id))
    return customer_service.get_customer_by_code(db, customer_id.upper())


def build_tools(runtime: ToolRuntime) -> list[StructuredTool]:
    db = runtime.db

    def get_customer(customer_id: str) -> str:
        def run():
            c = _resolve_customer(db, customer_id)
            if not c:
                return {
                    "ok": False,
                    "error": "I could not retrieve the customer information. Please verify the customer id.",
                }
            runtime.last_customer_id = c.id
            return {"ok": True, "customer": customer_service.customer_to_dict(c)}

        return wrap(runtime, "get_customer", run)

    def get_customer_by_email(email: str) -> str:
        def run():
            c = customer_service.get_customer_by_email(db, email.strip())
            if not c:
                return {"ok": False, "error": "No customer found for that email."}
            runtime.last_customer_id = c.id
            return {"ok": True, "customer": customer_service.customer_to_dict(c)}

        return wrap(runtime, "get_customer_by_email", run)

    def get_order(order_number: str) -> str:
        def run():
            o = order_service.get_order_by_number(db, order_number.strip().upper())
            if not o:
                return {
                    "ok": False,
                    "error": "I could not retrieve the order information. Please verify the order number.",
                }
            runtime.last_order_number = o.order_number
            runtime.last_customer_id = o.customer_id
            return {"ok": True, "order": order_service.order_to_dict(o)}

        return wrap(runtime, "get_order", run)

    def get_customer_orders(customer_id: str) -> str:
        def run():
            c = _resolve_customer(db, customer_id)
            if not c:
                return {"ok": False, "error": "Customer not found."}
            orders = order_service.list_orders(db, customer_id=c.id)
            return {"ok": True, "orders": [order_service.order_to_dict(o) for o in orders]}

        return wrap(runtime, "get_customer_orders", run)

    def get_delivery_status(order_number: str) -> str:
        def run():
            o = order_service.get_order_by_number(db, order_number.strip().upper())
            if not o:
                return {"ok": False, "error": "I could not retrieve the order information."}
            data = order_service.order_to_dict(o)
            return {
                "ok": True,
                "order_number": o.order_number,
                "status": data["status"],
                "payment_status": data["payment_status"],
                "expected_delivery": data["expected_delivery"],
                "actual_delivery": data["actual_delivery"],
                "delay_days": data["delay_days"],
                "shipping_address": o.shipping_address,
                "refund_status": data["refund_status"],
                "is_refunded": data["is_refunded"],
                "has_active_refund": data["has_active_refund"],
                "latest_refund": data["latest_refund"],
                "open_ticket_count": data["open_ticket_count"],
                "latest_ticket": data["latest_ticket"],
            }

        return wrap(runtime, "get_delivery_status", run)

    def get_customer_tickets(customer_id: str) -> str:
        def run():
            c = _resolve_customer(db, customer_id)
            if not c:
                return {"ok": False, "error": "Customer not found."}
            tickets = ticket_service.list_tickets(db, customer_id=c.id)
            return {"ok": True, "tickets": [ticket_service.ticket_to_dict(t) for t in tickets]}

        return wrap(runtime, "get_customer_tickets", run)

    def search_company_policy(query: str) -> str:
        def run():
            result = retrieve_policy(query)
            if result.get("sources"):
                runtime.sources.extend(result["sources"])
            return result

        return wrap(runtime, "search_company_policy", run)

    def get_business_rules_tool(query: str = "") -> str:
        def run():
            rules = get_business_rules().to_dict()
            return {"ok": True, "rules": rules, "note": "Use these thresholds; do not invent numeric policy limits."}

        return wrap(runtime, "get_business_rules", run)

    def create_support_ticket(
        customer_id: str,
        subject: str,
        description: str,
        order_number: str | None = None,
        priority: str = "MEDIUM",
        category: str = "GENERAL",
    ) -> str:
        def run():
            c = _resolve_customer(db, customer_id)
            if not c:
                return {"ok": False, "error": "Customer not found."}
            order = None
            if order_number:
                order = order_service.get_order_by_number(db, order_number.strip().upper())
            ticket = ticket_service.create_ticket(
                db,
                customer=c,
                subject=subject,
                description=description,
                order=order,
                priority=priority,
                category=category,
                assigned_to=runtime.requested_by,
            )
            runtime.last_ticket_number = ticket.ticket_number
            return {"ok": True, "ticket": ticket_service.ticket_to_dict(ticket)}

        return wrap(runtime, "create_support_ticket", run)

    def update_support_ticket(
        ticket_number: str,
        status: str | None = None,
        priority: str | None = None,
        category: str | None = None,
        resolution: str | None = None,
    ) -> str:
        def run():
            ticket = ticket_service.get_ticket_by_number(db, ticket_number.strip().upper())
            if not ticket:
                return {"ok": False, "error": "Ticket not found."}
            if status and status.upper() in {"CLOSED", "RESOLVED"}:
                return {
                    "ok": False,
                    "error": "Closing or resolving a ticket is a sensitive action. Create a pending approval instead of closing it directly.",
                }
            updated = ticket_service.update_ticket(
                db,
                ticket,
                status=status.upper() if status else None,
                priority=priority.upper() if priority else None,
                category=category.upper() if category else None,
                resolution=resolution,
            )
            return {"ok": True, "ticket": ticket_service.ticket_to_dict(updated)}

        return wrap(runtime, "update_support_ticket", run)

    def create_refund_request(
        order_number: str,
        reason: str,
        amount: float | None = None,
        ticket_number: str | None = None,
    ) -> str:
        def run():
            o = order_service.get_order_by_number(db, order_number.strip().upper())
            if not o:
                return {"ok": False, "error": "Order not found."}
            customer = customer_service.get_customer_by_id(db, o.customer_id)
            ticket = None
            if ticket_number:
                ticket = ticket_service.get_ticket_by_number(db, ticket_number.strip().upper())
            if not ticket and o.tickets:
                open_tickets = [t for t in o.tickets if t.status not in {"RESOLVED", "CLOSED"}]
                if open_tickets:
                    ticket = open_tickets[0]
            if not ticket and customer:
                ticket = ticket_service.create_ticket(
                    db,
                    customer=customer,
                    order=o,
                    subject=f"Refund request for {o.order_number}",
                    description=reason,
                    priority="HIGH",
                    category="REFUND",
                    assigned_to=runtime.requested_by,
                )
            if ticket:
                runtime.last_ticket_number = ticket.ticket_number
            runtime.last_order_number = o.order_number
            evaluation = refund_service.evaluate_refund_eligibility(db, o)
            if evaluation.get("high_value"):
                return {
                    "ok": False,
                    "error": "This case exceeds the automated refund threshold. Escalating to a human support specialist.",
                    "evaluation": evaluation,
                    "hint": "Call escalate_ticket instead of creating a refund.",
                }
            refund, err = refund_service.create_refund_request(
                db,
                order=o,
                customer=customer,
                reason=reason,
                amount=amount,
                ticket=ticket,
            )
            if err:
                return {"ok": False, "error": err, "evaluation": evaluation}
            action = None
            if ticket:
                from backend.models.audit import PendingAction
                action = db.scalar(
                    select(PendingAction).where(
                        PendingAction.ticket_id == ticket.id,
                        PendingAction.status == "PENDING_APPROVAL",
                    )
                )
            if action:
                action.action_type = "REFUND"
                action.agent_reason = reason
                action.amount = refund.amount
                action.refund_id = refund.refund_id
                action.order_id = o.id
                action.policy_evidence = json.dumps(evaluation, default=str)
                action.parameters = json.dumps({"order_number": o.order_number, "amount": refund.amount})
                db.commit()
            else:
                action = create_pending_action(
                    db,
                    action_type="REFUND",
                    agent_reason=reason,
                    requested_by=runtime.requested_by,
                    ticket_id=ticket.id if ticket else None,
                    customer_id=customer.id if customer else None,
                    order_id=o.id,
                    refund_id=refund.refund_id,
                    policy_evidence=json.dumps(evaluation, default=str),
                    parameters={"order_number": o.order_number, "amount": refund.amount},
                    amount=refund.amount,
                )
            return {
                "ok": True,
                "refund": refund_service.refund_to_dict(refund),
                "pending_action": {
                    "action_id": action.action_id,
                    "status": action.status,
                },
                "evaluation": evaluation,
                "message": "Refund request created as PENDING_APPROVAL. A human must approve before processing.",
            }

        return wrap(runtime, "create_refund_request", run)

    def escalate_ticket(reason: str, ticket_number: str | None = None, order_number: str | None = None) -> str:
        def run():
            ticket = None
            order = None
            if ticket_number:
                ticket = ticket_service.get_ticket_by_number(db, ticket_number.strip().upper())
            if order_number:
                order = order_service.get_order_by_number(db, order_number.strip().upper())
            if not ticket and order and order.tickets:
                open_tickets = [t for t in order.tickets if t.status not in {"RESOLVED", "CLOSED"}]
                if open_tickets:
                    ticket = open_tickets[0]
            if not ticket and order:
                customer = customer_service.get_customer_by_id(db, order.customer_id) if order.customer_id else None
                if customer:
                    ticket = ticket_service.create_ticket(
                        db,
                        customer=customer,
                        order=order,
                        subject=f"Escalation for {order.order_number}",
                        description=reason,
                        priority="CRITICAL",
                        category="REFUND" if "refund" in reason.lower() else "GENERAL",
                        assigned_to=runtime.requested_by,
                    )
            decision = should_escalate(query=reason, order=order, ticket=ticket, db=db)
            if ticket:
                ticket_service.update_ticket(
                    db,
                    ticket,
                    status="ESCALATED",
                    resolution=None,
                    investigation_notes=reason,
                )
                runtime.last_ticket_number = ticket.ticket_number
            if order:
                runtime.last_order_number = order.order_number

            action = None
            if ticket:
                from backend.models.audit import PendingAction
                action = db.scalar(
                    select(PendingAction).where(
                        PendingAction.ticket_id == ticket.id,
                        PendingAction.status == "PENDING_APPROVAL",
                    )
                )
            if action:
                action.action_type = "ESCALATION"
                action.agent_reason = reason
                action.amount = order.amount if order else action.amount
                action.order_id = order.id if order else action.order_id
                action.parameters = json.dumps({
                    "reason": reason,
                    "order_number": order.order_number if order else None,
                    "ticket_number": ticket.ticket_number if ticket else None,
                })
                db.commit()
            else:
                action = create_pending_action(
                    db,
                    action_type="ESCALATION",
                    agent_reason=reason,
                    requested_by=runtime.requested_by,
                    ticket_id=ticket.id if ticket else None,
                    customer_id=order.customer_id if order else (ticket.customer_id if ticket else None),
                    order_id=order.id if order else (ticket.order_id if ticket else None),
                    amount=order.amount if order else None,
                    parameters={
                        "reason": reason,
                        "order_number": order.order_number if order else None,
                        "ticket_number": ticket.ticket_number if ticket else None,
                    },
                )
            return {
                "ok": True,
                "escalated": True,
                "decision": decision,
                "pending_action": action.action_id,
                "ticket": ticket_service.ticket_to_dict(ticket) if ticket else None,
                "message": decision["message"],
            }

        return wrap(runtime, "escalate_ticket", run)

    def generate_customer_response(context: str) -> str:
        def run():
            return {
                "ok": True,
                "instruction": "Write a professional customer reply using ONLY this verified context.",
                "context": context,
            }

        return wrap(runtime, "generate_customer_response", run)

    def evaluate_refund(order_number: str) -> str:
        def run():
            o = order_service.get_order_by_number(db, order_number.strip().upper())
            if not o:
                return {"ok": False, "error": "Order not found."}
            evaluation = refund_service.evaluate_refund_eligibility(db, o)
            decision = should_escalate(order=o, db=db)
            return {
                "ok": True,
                "order": order_service.order_to_dict(o),
                "evaluation": evaluation,
                "escalation": decision,
            }

        return wrap(runtime, "evaluate_refund_eligibility", run)

    return [
        StructuredTool.from_function(
            func=get_customer,
            name="get_customer",
            description="Get customer details by customer code (CUST001) or numeric id.",
            args_schema=CustomerIdInput,
        ),
        StructuredTool.from_function(
            func=get_customer_by_email,
            name="get_customer_by_email",
            description="Find a customer using their email address.",
            args_schema=EmailInput,
        ),
        StructuredTool.from_function(
            func=get_order,
            name="get_order",
            description="Get order details by order number such as ORD1001.",
            args_schema=OrderInput,
        ),
        StructuredTool.from_function(
            func=get_customer_orders,
            name="get_customer_orders",
            description="List order history for a customer.",
            args_schema=CustomerIdInput,
        ),
        StructuredTool.from_function(
            func=get_delivery_status,
            name="get_delivery_status",
            description="Get delivery status, expected date, and delay days for an order.",
            args_schema=OrderInput,
        ),
        StructuredTool.from_function(
            func=get_customer_tickets,
            name="get_customer_tickets",
            description="List previous support tickets for a customer.",
            args_schema=CustomerIdInput,
        ),
        StructuredTool.from_function(
            func=search_company_policy,
            name="search_company_policy",
            description="Retrieve relevant fictional company policy chunks with sources via RAG.",
            args_schema=PolicyInput,
        ),
        StructuredTool.from_function(
            func=get_business_rules_tool,
            name="get_business_rules",
            description="Return configured numeric business rules such as refund delay days and auto refund limit.",
            args_schema=QueryInput,
        ),
        StructuredTool.from_function(
            func=create_support_ticket,
            name="create_support_ticket",
            description="Create a support ticket. Does not close tickets.",
            args_schema=CreateTicketInput,
        ),
        StructuredTool.from_function(
            func=update_support_ticket,
            name="update_support_ticket",
            description="Update ticket fields. Cannot close or resolve tickets without human approval.",
            args_schema=UpdateTicketInput,
        ),
        StructuredTool.from_function(
            func=create_refund_request,
            name="create_refund_request",
            description="Create a PENDING_APPROVAL refund request. Never processes money. High-value orders must be escalated instead.",
            args_schema=RefundRequestInput,
        ),
        StructuredTool.from_function(
            func=escalate_ticket,
            name="escalate_ticket",
            description="Escalate a case to a human specialist. Use for critical, fraud, missing info, high-value, or human-request cases.",
            args_schema=EscalateInput,
        ),
        StructuredTool.from_function(
            func=generate_customer_response,
            name="generate_customer_response",
            description="Prepare a customer-facing reply from verified context only.",
            args_schema=ResponseInput,
        ),
        StructuredTool.from_function(
            func=evaluate_refund,
            name="evaluate_refund_eligibility",
            description="Apply configured business rules to decide refund eligibility for an order.",
            args_schema=OrderInput,
        ),
    ]


def analytics_snapshot(db: Session | None = None) -> dict:
    close = False
    if db is None:
        db = SessionLocal()
        close = True
    try:
        import pandas as pd

        from backend.models.refund import Refund
        from backend.models.ticket import Ticket

        tickets = ticket_service.list_tickets(db, limit=5000)
        refunds = refund_service.list_refunds(db, limit=5000)
        tdf = pd.DataFrame([ticket_service.ticket_to_dict(t) for t in tickets])
        rdf = pd.DataFrame([refund_service.refund_to_dict(r) for r in refunds]) if refunds else pd.DataFrame()

        def count_status(status: str) -> int:
            if tdf.empty:
                return 0
            return int((tdf["status"] == status).sum())

        avg_resolution_hours = None
        if not tdf.empty:
            resolved = tdf[tdf["status"].isin(["RESOLVED", "CLOSED"])].copy()
            if not resolved.empty:
                resolved["created_at"] = pd.to_datetime(resolved["created_at"], format="ISO8601")
                resolved["updated_at"] = pd.to_datetime(resolved["updated_at"], format="ISO8601")
                hours = (resolved["updated_at"] - resolved["created_at"]).dt.total_seconds() / 3600
                avg_resolution_hours = float(hours.mean()) if len(hours) else None

        most_common_issue = None
        if not tdf.empty:
            most_common_issue = tdf["category"].mode().iloc[0] if not tdf["category"].mode().empty else None

        total_refund_amount = float(rdf[rdf["status"] == "PROCESSED"]["amount"].sum()) if not rdf.empty else 0.0

        from backend.models.audit import PendingAction
        from backend.services.approval_service import sync_tickets_and_approvals

        sync_tickets_and_approvals(db)

        pending_count = (
            db.query(PendingAction).filter(PendingAction.status == "PENDING_APPROVAL").count()
        )

        return {
            "total_tickets": int(len(tdf)),
            "open_tickets": count_status("OPEN") + count_status("IN_PROGRESS") + count_status("WAITING_FOR_CUSTOMER"),
            "resolved_tickets": count_status("RESOLVED") + count_status("CLOSED"),
            "escalated_tickets": count_status("ESCALATED"),
            "pending_approvals": pending_count,
            "average_resolution_hours": avg_resolution_hours,
            "average_response_hours": avg_resolution_hours,
            "total_refund_amount": total_refund_amount,
            "most_common_issue": most_common_issue,
            "most_common_product_issue": most_common_issue,
            "tickets_by_status": tdf["status"].value_counts().to_dict() if not tdf.empty else {},
            "tickets_by_priority": tdf["priority"].value_counts().to_dict() if not tdf.empty else {},
            "tickets_by_category": tdf["category"].value_counts().to_dict() if not tdf.empty else {},
            "refunds_by_status": rdf["status"].value_counts().to_dict() if not rdf.empty else {},
        }
    finally:
        if close:
            db.close()
