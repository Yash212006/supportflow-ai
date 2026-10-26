from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.customer import Customer


def get_customer_by_id(db: Session, customer_id: int) -> Customer | None:
    return db.get(Customer, customer_id)


def get_customer_by_code(db: Session, customer_code: str) -> Customer | None:
    return db.scalar(select(Customer).where(Customer.customer_code == customer_code))


def get_customer_by_email(db: Session, email: str) -> Customer | None:
    return db.scalar(select(Customer).where(Customer.email == email.lower()))


def list_customers(db: Session, q: str | None = None, limit: int = 200) -> list[Customer]:
    stmt = select(Customer).order_by(Customer.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            (Customer.name.ilike(like))
            | (Customer.email.ilike(like))
            | (Customer.customer_code.ilike(like))
        )
    return list(db.scalars(stmt.limit(limit)))


def customer_to_dict(c: Customer) -> dict:
    return {
        "id": c.id,
        "customer_code": c.customer_code,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
