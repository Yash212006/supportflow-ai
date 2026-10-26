from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.customer import Customer
from backend.models.order import Order
from backend.models.ticket import Ticket


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def next_ticket_number(db: Session) -> str:
    count = db.scalar(select(func.count(Ticket.id))) or 0
    num = 1000 + count + 1
    while db.scalar(select(Ticket.id).where(Ticket.ticket_number == f"TKT{num}")):
        num += 1
    return f"TKT{num}"


def get_ticket_by_number(db: Session, ticket_number: str) -> Ticket | None:
    return db.scalar(select(Ticket).where(Ticket.ticket_number == ticket_number))


def get_ticket_by_id(db: Session, ticket_id: int) -> Ticket | None:
    return db.get(Ticket, ticket_id)


def list_tickets(
    db: Session,
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    customer_id: int | None = None,
    q: str | None = None,
    limit: int = 300,
) -> list[Ticket]:
    stmt = select(Ticket).order_by(Ticket.id.desc())
    if status:
        stmt = stmt.where(Ticket.status == status)
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
    if category:
        stmt = stmt.where(Ticket.category == category)
    if customer_id:
        stmt = stmt.where(Ticket.customer_id == customer_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            (Ticket.ticket_number.ilike(like))
            | (Ticket.subject.ilike(like))
            | (Ticket.description.ilike(like))
        )
    return list(db.scalars(stmt.limit(limit)))


def create_ticket(
    db: Session,
    *,
    customer: Customer,
    subject: str,
    description: str,
    order: Order | None = None,
    priority: str = "MEDIUM",
    category: str = "GENERAL",
    assigned_to: str | None = None,
) -> Ticket:
    ticket = Ticket(
        ticket_number=next_ticket_number(db),
        customer_id=customer.id,
        order_id=order.id if order else None,
        subject=subject,
        description=description,
        priority=priority.upper(),
        status="OPEN",
        category=category.upper(),
        assigned_to=assigned_to,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    # Queue an approval action for the new ticket
    try:
        from backend.services.approval_service import create_pending_action

        action_type = (
            "ESCALATION"
            if priority.upper() == "CRITICAL"
            else (
                "REFUND_REQUEST"
                if category.upper() == "REFUND"
                else f"TICKET_{category.upper()}"
            )
        )
        amount = (
            order.amount
            if (order and category.upper() in {"REFUND", "CANCELLATION"})
            else None
        )
        create_pending_action(
            db,
            action_type=action_type,
            agent_reason=f"Support ticket {ticket.ticket_number} [{ticket.priority}] ({ticket.status}): {subject}",
            requested_by=assigned_to or "support_agent",
            ticket_id=ticket.id,
            customer_id=customer.id,
            order_id=order.id if order else None,
            amount=amount,
            parameters={
                "ticket_number": ticket.ticket_number,
                "category": ticket.category,
                "priority": ticket.priority,
            },
        )
    except Exception:
        pass

    return ticket


def update_ticket(
    db: Session,
    ticket: Ticket,
    **fields,
) -> Ticket:
    allowed = {
        "status",
        "priority",
        "category",
        "resolution",
        "assigned_to",
        "investigation_notes",
    }
    for key, value in fields.items():
        if key in allowed and value is not None:
            setattr(ticket, key, value)
    ticket.updated_at = _utcnow()
    db.commit()
    db.refresh(ticket)

    # If ticket was resolved or closed, resolve/close any active pending actions
    if ticket.status in {"RESOLVED", "CLOSED"}:
        try:
            from backend.models.audit import PendingAction

            pending_acts = list(
                db.scalars(
                    select(PendingAction).where(
                        PendingAction.ticket_id == ticket.id,
                        PendingAction.status == "PENDING_APPROVAL",
                    )
                )
            )
            for pa in pending_acts:
                pa.status = "APPROVED" if ticket.status == "RESOLVED" else "REJECTED"
                pa.reviewed_at = _utcnow()
                pa.reviewed_by = pa.reviewed_by or "system_sync"
                pa.review_note = (
                    ticket.resolution or f"Ticket marked {ticket.status}."
                )
            if pending_acts:
                db.commit()
        except Exception:
            pass

    return ticket


def ticket_to_dict(t: Ticket) -> dict:
    return {
        "id": t.id,
        "ticket_number": t.ticket_number,
        "customer_id": t.customer_id,
        "order_id": t.order_id,
        "subject": t.subject,
        "description": t.description,
        "priority": t.priority,
        "status": t.status,
        "category": t.category,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "assigned_to": t.assigned_to,
        "resolution": t.resolution,
        "investigation_notes": t.investigation_notes,
    }
