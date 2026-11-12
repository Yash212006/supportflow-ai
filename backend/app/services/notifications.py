from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Notification, User
from app.models.enums import MANAGER_ROLES, NotificationType


def notify_user(db: Session, *, business_id: uuid.UUID, user_id: uuid.UUID, type_: NotificationType, title: str, body: str, link: str | None = None) -> Notification:
    n = Notification(business_id=business_id, user_id=user_id, type=type_, title=title, body=body, link=link)
    db.add(n)
    return n


def notify_customer(db: Session, *, customer_id: uuid.UUID, type_: NotificationType, title: str, body: str, link: str | None = None) -> Notification | None:
    customer = db.get(Customer, customer_id)
    if customer is None or customer.user_id is None:
        return None
    return notify_user(db, business_id=customer.business_id, user_id=customer.user_id, type_=type_, title=title, body=body, link=link)


def notify_managers(db: Session, *, business_id: uuid.UUID, type_: NotificationType, title: str, body: str, link: str | None = None) -> int:
    managers = db.scalars(select(User).where(User.business_id == business_id, User.role.in_(MANAGER_ROLES), User.is_active.is_(True))).all()
    for m in managers:
        notify_user(db, business_id=business_id, user_id=m.id, type_=type_, title=title, body=body, link=link)
    return len(managers)
