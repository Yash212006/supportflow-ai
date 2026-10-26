from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.schemas import CustomerOut
from backend.services import customer_service

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("", response_model=list[CustomerOut])
def list_customers(q: str | None = None, db: Session = Depends(get_db)):
    return customer_service.list_customers(db, q=q)


@router.get("/{customer_key}")
def get_customer(customer_key: str, db: Session = Depends(get_db)):
    if customer_key.isdigit():
        customer = customer_service.get_customer_by_id(db, int(customer_key))
    else:
        customer = customer_service.get_customer_by_code(db, customer_key.upper())
        if customer is None and "@" in customer_key:
            customer = customer_service.get_customer_by_email(db, customer_key)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    from backend.services import order_service, refund_service, ticket_service

    return {
        "customer": customer_service.customer_to_dict(customer),
        "orders": [order_service.order_to_dict(o) for o in order_service.list_orders(db, customer_id=customer.id)],
        "tickets": [ticket_service.ticket_to_dict(t) for t in ticket_service.list_tickets(db, customer_id=customer.id)],
        "refunds": [refund_service.refund_to_dict(r) for r in refund_service.list_refunds(db, customer_id=customer.id)],
    }
