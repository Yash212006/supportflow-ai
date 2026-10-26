from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.schemas import RefundCreate, RefundOut
from backend.services import customer_service, order_service, refund_service, ticket_service
from backend.services.approval_service import create_pending_action, write_audit

router = APIRouter(prefix="/api/refunds", tags=["refunds"])


@router.get("", response_model=list[RefundOut])
def list_refunds(status: str | None = None, db: Session = Depends(get_db)):
    return refund_service.list_refunds(db, status=status)


@router.post("")
def create_refund(payload: RefundCreate, db: Session = Depends(get_db)):
    order = order_service.get_order_by_number(db, payload.order_number.upper())
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    customer = customer_service.get_customer_by_id(db, order.customer_id)
    ticket = None
    if payload.ticket_number:
        ticket = ticket_service.get_ticket_by_number(db, payload.ticket_number.upper())
    evaluation = refund_service.evaluate_refund_eligibility(db, order)
    if evaluation.get("high_value"):
        raise HTTPException(
            status_code=400,
            detail="This case exceeds the automated refund threshold. Escalate instead.",
        )
    refund, err = refund_service.create_refund_request(
        db,
        order=order,
        customer=customer,
        reason=payload.reason,
        amount=payload.amount,
        ticket=ticket,
    )
    if err:
        raise HTTPException(status_code=409, detail=err)
    action = create_pending_action(
        db,
        action_type="REFUND",
        agent_reason=payload.reason,
        requested_by=payload.requested_by,
        ticket_id=ticket.id if ticket else None,
        customer_id=customer.id if customer else None,
        order_id=order.id,
        refund_id=refund.refund_id,
        parameters={"order_number": order.order_number},
        amount=refund.amount,
    )
    write_audit(
        db,
        action_type="create_refund_request",
        tool_name="create_refund_request",
        ticket_id=ticket.id if ticket else None,
        parameters={"refund_id": refund.refund_id},
        approval_status="PENDING_APPROVAL",
        result="created",
    )
    return {
        "refund": refund_service.refund_to_dict(refund),
        "pending_action": action.action_id,
        "evaluation": evaluation,
    }


@router.get("/{refund_id}")
def get_refund(refund_id: str, db: Session = Depends(get_db)):
    refund = refund_service.get_refund_by_id_str(db, refund_id)
    if not refund:
        raise HTTPException(status_code=404, detail="Refund not found")
    return refund_service.refund_to_dict(refund)
