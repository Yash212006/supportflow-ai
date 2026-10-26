from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.schemas import OrderOut
from backend.services import customer_service, order_service

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("", response_model=list[OrderOut])
def list_orders(
    customer_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    return order_service.list_orders(db, customer_id=customer_id, status=status, q=q)


@router.get("/{order_key}")
def get_order(order_key: str, db: Session = Depends(get_db)):
    order = (
        order_service.get_order_by_id(db, int(order_key))
        if order_key.isdigit()
        else order_service.get_order_by_number(db, order_key.upper())
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    customer = customer_service.get_customer_by_id(db, order.customer_id)
    return {
        "order": order_service.order_to_dict(order),
        "customer": customer_service.customer_to_dict(customer) if customer else None,
    }
