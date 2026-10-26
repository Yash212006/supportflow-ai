import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.audit import AuditLog, PendingAction
from backend.models.customer import Customer
from backend.models.order import Order
from backend.models.refund import Refund
from backend.models.ticket import Ticket
from backend.services.ticket_service import update_ticket


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def write_audit(
    db: Session,
    *,
    action_type: str,
    requested_by: str = "support_agent",
    ticket_id: int | None = None,
    agent_reason: str | None = None,
    tool_name: str | None = None,
    parameters: dict | None = None,
    approval_status: str = "N/A",
    result: str | None = None,
    latency_ms: int | None = None,
) -> AuditLog:
    log = AuditLog(
        action_id=f"AUD-{uuid.uuid4().hex[:12]}",
        ticket_id=ticket_id,
        action_type=action_type,
        requested_by=requested_by,
        agent_reason=agent_reason,
        tool_name=tool_name,
        parameters=json.dumps(parameters or {}, default=str),
        approval_status=approval_status,
        result=result,
        latency_ms=latency_ms,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def list_audit(db: Session, limit: int = 200) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)))


def enrich_action(action: PendingAction, db: Session) -> PendingAction:
    # 1. Resolve ticket
    ticket = action.ticket
    if not ticket and action.ticket_id:
        ticket = db.get(Ticket, action.ticket_id)
    if not ticket and action.order_id:
        ticket = db.query(Ticket).filter(Ticket.order_id == action.order_id).order_by(Ticket.id.desc()).first()

    # 2. Resolve order
    order = action.order
    if not order and action.order_id:
        order = db.get(Order, action.order_id)
    if not order and ticket and ticket.order_id:
        order = db.get(Order, ticket.order_id)
    if not order and action.parameters:
        try:
            params = json.loads(action.parameters) if isinstance(action.parameters, str) else action.parameters
            if isinstance(params, dict) and params.get("order_number"):
                order = db.query(Order).filter(Order.order_number == params["order_number"]).first()
        except Exception:
            pass

    # 3. Resolve customer
    customer = action.customer
    if not customer and action.customer_id:
        customer = db.get(Customer, action.customer_id)
    if not customer and order and order.customer_id:
        customer = db.get(Customer, order.customer_id)
    if not customer and ticket and ticket.customer_id:
        customer = db.get(Customer, ticket.customer_id)

    # Attach dynamic attributes matching PendingActionOut schema
    action.ticket_number = ticket.ticket_number if ticket else None
    action.ticket_subject = ticket.subject if ticket else None
    action.customer_code = customer.customer_code if customer else None
    action.customer_name = customer.name if customer else None
    action.customer_email = customer.email if customer else None
    action.order_number = order.order_number if order else None
    action.order_product = order.product_name if order else None
    return action


OPEN_TICKET_STATUSES = {"OPEN", "IN_PROGRESS", "WAITING_FOR_CUSTOMER", "ESCALATED"}


def sync_tickets_and_approvals(db: Session) -> dict:
    """Synchronize open tickets with the pending approval governance queue.

    Ensures:
    1. Any PENDING_APPROVAL action pointing to a ticket that is already RESOLVED/CLOSED is marked APPROVED/CLOSED.
    2. Any ticket in an open/in-process status (OPEN, IN_PROGRESS, WAITING_FOR_CUSTOMER, ESCALATED)
       has an active PENDING_APPROVAL action so it is visible in the human approvals governance queue.
    """
    # 1. Clean up lingering actions for resolved or closed tickets
    pending_actions = list(
        db.scalars(
            select(PendingAction).where(PendingAction.status == "PENDING_APPROVAL")
        )
    )
    for action in pending_actions:
        if action.ticket_id:
            ticket = db.get(Ticket, action.ticket_id)
            if ticket and ticket.status not in OPEN_TICKET_STATUSES:
                action.status = "APPROVED" if ticket.status == "RESOLVED" else "REJECTED"
                action.reviewed_at = _utcnow()
                action.reviewed_by = action.reviewed_by or "system_sync"
                action.review_note = action.review_note or f"Ticket {ticket.ticket_number} is already {ticket.status}."

    # 2. Deduplicate multiple active actions for the exact same ticket
    seen_tickets = set()
    for a in list(db.scalars(select(PendingAction).where(PendingAction.status == "PENDING_APPROVAL").order_by(PendingAction.id.desc()))):
        if a.ticket_id:
            if a.ticket_id in seen_tickets:
                a.status = "APPROVED"
                a.reviewed_at = _utcnow()
                a.reviewed_by = "system_dedup"
                a.review_note = "Merged with primary ticket approval."
            else:
                seen_tickets.add(a.ticket_id)
    db.commit()

    # 3. Re-query currently active actions after steps 1 & 2
    active_ticket_ids = set()
    for a in db.scalars(select(PendingAction).where(PendingAction.status == "PENDING_APPROVAL")):
        if a.ticket_id:
            active_ticket_ids.add(a.ticket_id)

    # 4. Find all tickets currently in open/in-process statuses
    open_tickets = list(
        db.scalars(
            select(Ticket).where(Ticket.status.in_(list(OPEN_TICKET_STATUSES)))
        )
    )

    created_count = 0
    for t in open_tickets:
        if t.id not in active_ticket_ids:
            if t.status == "ESCALATED":
                action_type = "ESCALATION"
            elif t.category == "REFUND":
                action_type = "REFUND_REQUEST"
            elif t.category == "DELIVERY":
                action_type = "DELIVERY_APPROVAL"
            else:
                action_type = f"TICKET_{t.category.upper()}"

            amount = None
            if t.order and t.category in {"REFUND", "CANCELLATION"}:
                amount = t.order.amount

            # Check if there is an associated pending refund
            refund_id = None
            if t.refunds:
                for r in t.refunds:
                    if r.status in {"PENDING_APPROVAL", "APPROVED"}:
                        refund_id = r.refund_id
                        break
            if not refund_id and t.order and t.order.refunds:
                for r in t.order.refunds:
                    if r.status in {"PENDING_APPROVAL", "APPROVED"}:
                        refund_id = r.refund_id
                        break

            new_action = PendingAction(
                action_id=f"ACT-{uuid.uuid4().hex[:12]}",
                ticket_id=t.id,
                customer_id=t.customer_id,
                order_id=t.order_id,
                refund_id=refund_id,
                action_type=action_type,
                requested_by=t.assigned_to or "support_agent",
                agent_reason=f"Support ticket {t.ticket_number} [{t.priority}] ({t.status}): {t.description or t.subject}",
                policy_evidence=json.dumps({
                    "ticket_number": t.ticket_number,
                    "status": t.status,
                    "priority": t.priority,
                    "category": t.category,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }),
                parameters=json.dumps({
                    "ticket_number": t.ticket_number,
                    "category": t.category,
                    "priority": t.priority,
                    "status": t.status,
                }),
                amount=amount,
                status="PENDING_APPROVAL",
            )
            db.add(new_action)
            active_ticket_ids.add(t.id)
            created_count += 1

    db.commit()
    return {"created": created_count, "open_tickets": len(open_tickets)}


def list_pending_actions(db: Session, status: str | None = "PENDING_APPROVAL") -> list[PendingAction]:
    if status == "PENDING_APPROVAL" or status is None:
        sync_tickets_and_approvals(db)
    stmt = select(PendingAction).order_by(PendingAction.id.desc())
    if status:
        stmt = stmt.where(PendingAction.status == status)
    actions = list(db.scalars(stmt))
    for a in actions:
        enrich_action(a, db)
    return actions


def get_pending_by_action_id(db: Session, action_id: str) -> PendingAction | None:
    action = db.scalar(select(PendingAction).where(PendingAction.action_id == action_id))
    if action:
        enrich_action(action, db)
    return action


def create_pending_action(
    db: Session,
    *,
    action_type: str,
    agent_reason: str,
    requested_by: str = "support_agent",
    ticket_id: int | None = None,
    customer_id: int | None = None,
    order_id: int | None = None,
    refund_id: str | None = None,
    policy_evidence: str | None = None,
    parameters: dict | None = None,
    amount: float | None = None,
) -> PendingAction:
    action = PendingAction(
        action_id=f"ACT-{uuid.uuid4().hex[:12]}",
        ticket_id=ticket_id,
        customer_id=customer_id,
        order_id=order_id,
        refund_id=refund_id,
        action_type=action_type,
        requested_by=requested_by,
        agent_reason=agent_reason,
        policy_evidence=policy_evidence,
        parameters=json.dumps(parameters or {}, default=str),
        amount=amount,
        status="PENDING_APPROVAL",
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def approve_action(
    db: Session,
    action: PendingAction,
    reviewed_by: str,
    note: str | None = None,
) -> dict:
    if action.status != "PENDING_APPROVAL":
        return {"ok": False, "error": f"Action is already {action.status}."}

    action.status = "APPROVED"
    action.reviewed_at = _utcnow()
    action.reviewed_by = reviewed_by
    action.review_note = note
    db.commit()

    steps: list[str] = ["Approval recorded"]
    refund: Refund | None = None
    if action.refund_id:
        refund = db.scalar(select(Refund).where(Refund.refund_id == action.refund_id))
        if refund:
            if refund.status not in {"PENDING_APPROVAL", "APPROVED"}:
                write_audit(
                    db,
                    action_type="approve_refund",
                    requested_by=reviewed_by,
                    ticket_id=action.ticket_id,
                    tool_name="approve_refund",
                    parameters={"refund_id": action.refund_id},
                    approval_status="APPROVED",
                    result=f"Refund in unexpected status {refund.status}",
                )
                return {"ok": False, "error": f"Refund status is {refund.status}."}
            refund.status = "APPROVED"
            refund.approved_at = _utcnow()
            db.commit()
            steps.append("Refund approved")
            refund.status = "PROCESSED"
            refund.processed_at = _utcnow()
            db.commit()
            steps.append("Refund processed (simulated)")

    # Transition linked Order to REFUNDED and resolve any linked Tickets
    order_id = action.order_id or (refund.order_id if refund else None)
    if order_id:
        order = db.get(Order, order_id)
        if order:
            is_refund_action = (
                action.action_type in {"REFUND", "REFUND_REQUEST"}
                or refund is not None
                or (
                    action.action_type == "ESCALATION"
                    and (
                        "refund" in (action.agent_reason or "").lower()
                        or action.amount is not None
                    )
                )
            )
            if is_refund_action:
                order.status = "REFUNDED"
                order.payment_status = "REFUNDED"
                db.commit()
                steps.append(f"Order {order.order_number} status updated to REFUNDED")

                if not refund and action.amount:
                    ref_id = f"RFD{uuid.uuid4().hex[:6].upper()}"
                    r_new = Refund(
                        refund_id=ref_id,
                        order_id=order.id,
                        customer_id=order.customer_id,
                        ticket_id=action.ticket_id,
                        amount=action.amount,
                        reason=action.agent_reason or "Escalation refund approved by human supervisor.",
                        status="PROCESSED",
                    )
                    db.add(r_new)
                    db.commit()
                    steps.append(f"Refund {ref_id} created and marked PROCESSED")

            # Resolve any open tickets linked to this order if it was a refund
            if is_refund_action:
                if order.tickets:
                    for t in order.tickets:
                        if t.status in OPEN_TICKET_STATUSES:
                            update_ticket(
                                db,
                                t,
                                status="RESOLVED",
                                resolution=note or f"Action {action.action_type} approved and completed.",
                            )
                            steps.append(f"Ticket {t.ticket_number} marked RESOLVED")

    if action.ticket_id:
        ticket = db.get(Ticket, action.ticket_id)
        if ticket and ticket.status != "RESOLVED":
            resolution = (
                note
                or f"{action.action_type} approved. {action.agent_reason}"
            )
            update_ticket(
                db,
                ticket,
                status="RESOLVED",
                resolution=resolution[:2000],
            )
            steps.append("Ticket updated to RESOLVED")

        # Concurrently resolve any duplicate/sibling pending actions for this ticket
        siblings = list(
            db.scalars(
                select(PendingAction).where(
                    PendingAction.ticket_id == action.ticket_id,
                    PendingAction.id != action.id,
                    PendingAction.status == "PENDING_APPROVAL",
                )
            )
        )
        for sib in siblings:
            sib.status = "APPROVED"
            sib.reviewed_at = action.reviewed_at
            sib.reviewed_by = reviewed_by
            sib.review_note = note or f"Resolved concurrently with {action.action_id}."
        if siblings:
            db.commit()

    write_audit(
        db,
        action_type=action.action_type,
        requested_by=reviewed_by,
        ticket_id=action.ticket_id,
        agent_reason=action.agent_reason,
        tool_name="approve_action",
        parameters={"action_id": action.action_id, "refund_id": action.refund_id},
        approval_status="APPROVED",
        result="; ".join(steps),
    )
    steps.append("Audit log created")
    return {
        "ok": True,
        "steps": steps,
        "action_id": action.action_id,
        "refund_id": action.refund_id,
        "status": "APPROVED",
    }


def reject_action(
    db: Session,
    action: PendingAction,
    reviewed_by: str,
    note: str | None = None,
) -> dict:
    if action.status != "PENDING_APPROVAL":
        return {"ok": False, "error": f"Action is already {action.status}."}

    action.status = "REJECTED"
    action.reviewed_at = _utcnow()
    action.reviewed_by = reviewed_by
    action.review_note = note or "Action rejected by human reviewer."
    db.commit()

    if action.refund_id:
        refund = db.scalar(select(Refund).where(Refund.refund_id == action.refund_id))
        if refund and refund.status == "PENDING_APPROVAL":
            refund.status = "REJECTED"
            refund.rejected_reason = action.review_note
            db.commit()

    if action.ticket_id:
        ticket = db.get(Ticket, action.ticket_id)
        if ticket and ticket.status in OPEN_TICKET_STATUSES:
            update_ticket(
                db,
                ticket,
                status="CLOSED",
                resolution=f"Action {action.action_type} rejected by human reviewer: {action.review_note}",
            )

        # Concurrently close any duplicate/sibling pending actions for this ticket
        siblings = list(
            db.scalars(
                select(PendingAction).where(
                    PendingAction.ticket_id == action.ticket_id,
                    PendingAction.id != action.id,
                    PendingAction.status == "PENDING_APPROVAL",
                )
            )
        )
        for sib in siblings:
            sib.status = "REJECTED"
            sib.reviewed_at = action.reviewed_at
            sib.reviewed_by = reviewed_by
            sib.review_note = action.review_note
        if siblings:
            db.commit()

    write_audit(
        db,
        action_type=action.action_type,
        requested_by=reviewed_by,
        ticket_id=action.ticket_id,
        agent_reason=action.agent_reason,
        tool_name="reject_action",
        parameters={"action_id": action.action_id},
        approval_status="REJECTED",
        result=f"Action {action.action_type} rejected by human reviewer.",
    )
    return {
        "ok": True,
        "status": "REJECTED",
        "message": f"Action {action.action_type} rejected by human reviewer.",
        "action_id": action.action_id,
    }
