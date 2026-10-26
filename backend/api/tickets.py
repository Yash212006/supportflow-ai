from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.schemas import TicketCreate, TicketOut, TicketUpdate
from backend.services import customer_service, order_service, ticket_service
from backend.services.approval_service import write_audit

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.get("", response_model=list[TicketOut])
def list_tickets(
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    return ticket_service.list_tickets(
        db, status=status, priority=priority, category=category, q=q
    )


@router.get("/{ticket_key}")
def get_ticket(ticket_key: str, db: Session = Depends(get_db)):
    ticket = (
        ticket_service.get_ticket_by_id(db, int(ticket_key))
        if ticket_key.isdigit()
        else ticket_service.get_ticket_by_number(db, ticket_key.upper())
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    customer = customer_service.get_customer_by_id(db, ticket.customer_id)
    order = order_service.get_order_by_id(db, ticket.order_id) if ticket.order_id else None
    from backend.services.approval_service import list_audit

    history = [
        {
            "action_id": a.action_id,
            "tool_name": a.tool_name,
            "action_type": a.action_type,
            "approval_status": a.approval_status,
            "result": a.result,
            "executed_at": a.executed_at.isoformat() if a.executed_at else None,
        }
        for a in list_audit(db, limit=50)
        if a.ticket_id == ticket.id
    ]
    return {
        "ticket": ticket_service.ticket_to_dict(ticket),
        "customer": customer_service.customer_to_dict(customer) if customer else None,
        "order": order_service.order_to_dict(order) if order else None,
        "action_history": history,
    }


@router.post("", response_model=TicketOut)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db)):
    customer = None
    if payload.customer_id:
        customer = customer_service.get_customer_by_id(db, payload.customer_id)
    elif payload.customer_code:
        customer = customer_service.get_customer_by_code(db, payload.customer_code.upper())
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    order = None
    if payload.order_id:
        order = order_service.get_order_by_id(db, payload.order_id)
    elif payload.order_number:
        order = order_service.get_order_by_number(db, payload.order_number.upper())
    ticket = ticket_service.create_ticket(
        db,
        customer=customer,
        subject=payload.subject,
        description=payload.description,
        order=order,
        priority=payload.priority,
        category=payload.category,
        assigned_to=payload.assigned_to,
    )
    write_audit(
        db,
        action_type="create_ticket",
        tool_name="create_support_ticket",
        ticket_id=ticket.id,
        parameters=payload.model_dump(),
        result="created",
    )
    return ticket


@router.put("/{ticket_id}", response_model=TicketOut)
def update_ticket(ticket_id: int, payload: TicketUpdate, db: Session = Depends(get_db)):
    ticket = ticket_service.get_ticket_by_id(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    updated = ticket_service.update_ticket(db, ticket, **payload.model_dump())
    write_audit(
        db,
        action_type="update_ticket",
        tool_name="update_support_ticket",
        ticket_id=ticket.id,
        parameters=payload.model_dump(),
        result="updated",
    )
    return updated
