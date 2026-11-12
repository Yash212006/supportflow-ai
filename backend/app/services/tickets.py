from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.core.errors import NotFound
from app.models import SupportTicket, TicketEvent
from app.models.enums import (
    IssueCategory,
    NotificationType,
    TicketPriority,
    TicketStatus,
)
from app.services.audit import audit
from app.services.notifications import notify_customer, notify_managers


def next_ticket_number(db: Session, business_id: uuid.UUID) -> int:
    n = db.scalar(select(func.max(SupportTicket.ticket_number)).where(SupportTicket.business_id == business_id))
    return int(n or 1000) + 1


def create_ticket(
    db: Session,
    *,
    business_id: uuid.UUID,
    customer_id: uuid.UUID,
    subject: str,
    description: str,
    actor: str,
    order_id: uuid.UUID | None = None,
    category: IssueCategory | None = None,
    priority: TicketPriority = TicketPriority.MEDIUM,
    confidence: float | None = None,
) -> SupportTicket:
    t = SupportTicket(
        business_id=business_id,
        ticket_number=next_ticket_number(db, business_id),
        customer_id=customer_id,
        order_id=order_id,
        subject=subject[:250],
        description=description,
        status=TicketStatus.OPEN,
        priority=priority,
        category=category,
        ai_classification_confidence=confidence,
    )
    db.add(t)
    db.flush()
    add_event(db, t, actor, "created", subject)
    audit(db, business_id=business_id, actor=actor, action="ticket.created", entity_type="ticket", entity_id=t.id, summary=f"Ticket #{t.ticket_number} created: {subject}")
    return t


def add_event(db: Session, ticket: SupportTicket, actor: str, event: str, detail: str | None = None) -> None:
    db.add(TicketEvent(ticket_id=ticket.id, actor=actor, event=event, detail=detail))


def set_status(db: Session, ticket: SupportTicket, status: TicketStatus, *, actor: str, detail: str | None = None, resolved_by: str | None = None) -> None:
    if ticket.status == status:
        if detail:
            add_event(db, ticket, actor, "note", detail)
        return
    old = ticket.status
    ticket.status = status
    now = utcnow()
    if status == TicketStatus.RESOLVED:
        ticket.resolved_at = now
        ticket.resolved_by = resolved_by or ("AI" if actor.startswith("agent") else "HUMAN")
        if detail:
            ticket.resolution_summary = detail
        notify_customer(
            db, customer_id=ticket.customer_id, type_=NotificationType.TICKET_RESOLVED, title=f"Ticket #{ticket.ticket_number} resolved", body=detail or "Your ticket was resolved.", link=f"/customer/tickets/{ticket.id}"
        )
    elif status == TicketStatus.ESCALATED:
        ticket.escalated_at = now
        notify_managers(
            db, business_id=ticket.business_id, type_=NotificationType.TICKET_ESCALATED, title=f"Ticket #{ticket.ticket_number} escalated", body=detail or ticket.subject, link=f"/manager/tickets/{ticket.id}"
        )
        notify_customer(
            db, customer_id=ticket.customer_id, type_=NotificationType.TICKET_ESCALATED, title=f"Ticket #{ticket.ticket_number} escalated to our team", body="A support specialist will review your request.", link=f"/customer/tickets/{ticket.id}"
        )
    add_event(db, ticket, actor, "status_changed", f"{old.value} → {status.value}" + (f": {detail}" if detail else ""))
    audit(db, business_id=ticket.business_id, actor=actor, action="ticket.status_changed", entity_type="ticket", entity_id=ticket.id, summary=f"Ticket #{ticket.ticket_number}: {old.value} → {status.value}", data={"detail": detail})


def get_ticket(db: Session, business_id: uuid.UUID, ticket_id: uuid.UUID, customer_id: uuid.UUID | None = None) -> SupportTicket:
    t = db.get(SupportTicket, ticket_id)
    if t is None or t.business_id != business_id or (customer_id is not None and t.customer_id != customer_id):
        raise NotFound("Ticket not found")
    return t
