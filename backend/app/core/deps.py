"""Request dependencies: DB session, authenticated principal, role guards.

Authorization is always enforced here (backend), never only in the frontend.
Every query a route makes must be scoped by `principal.business_id`; customer routes also by
`principal.customer_id`.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_token
from app.models import Customer, User
from app.models.enums import MANAGER_ROLES, STAFF_ROLES, Role

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user: User
    business_id: uuid.UUID
    role: Role
    customer_id: uuid.UUID | None

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    @property
    def actor(self) -> str:
        return f"user:{self.user.id}"

    @property
    def is_staff(self) -> bool:
        return self.role in STAFF_ROLES

    @property
    def is_manager(self) -> bool:
        return self.role in MANAGER_ROLES


def get_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Principal:
    if creds is None or creds.scheme.lower() != "bearer":
        raise Unauthorized("Missing bearer token")
    try:
        payload = decode_token(creds.credentials, "access")
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise Unauthorized("Invalid or expired token") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise Unauthorized("User not found or inactive")
    customer_id = None
    if user.role == Role.CUSTOMER:
        customer_id = db.scalar(select(Customer.id).where(Customer.user_id == user.id))
        if customer_id is None:
            raise Forbidden("Customer profile missing")
    principal = Principal(user=user, business_id=user.business_id, role=user.role, customer_id=customer_id)
    request.state.principal = principal
    return principal


def require_roles(*roles: Role) -> Callable[[Principal], Principal]:
    def _guard(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in roles:
            raise Forbidden(f"Requires role: {', '.join(r.value for r in roles)}")
        return principal

    return _guard


require_customer = require_roles(Role.CUSTOMER)
require_staff = require_roles(*STAFF_ROLES)
require_manager = require_roles(*MANAGER_ROLES)
require_admin = require_roles(Role.ADMIN)
