from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serializers import user_out
from app.core.database import get_db
from app.core.deps import Principal, get_principal
from app.core.errors import Conflict, NotFound, Unauthorized
from app.core.rate_limit import auth_limit
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.models import Business, Customer, User
from app.models.enums import Role
from app.services.audit import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=200)
    business_slug: str = Field(default="northwind", max_length=80)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str


def _tokens(user: User) -> dict[str, object]:
    return {
        "access_token": create_token(str(user.id), str(user.business_id), user.role.value, "access"),
        "refresh_token": create_token(str(user.id), str(user.business_id), user.role.value, "refresh"),
        "token_type": "bearer",
        "user": user_out(user),
    }


@router.post("/register", dependencies=[Depends(auth_limit)])
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)) -> dict[str, object]:
    """Public registration creates CUSTOMER accounts only. Staff accounts are created by admins."""
    business = db.scalars(select(Business).where(Business.slug == body.business_slug)).first()
    if business is None:
        raise NotFound("Business not found")
    email = body.email.lower()
    if db.scalars(select(User).where(User.email == email)).first():
        raise Conflict("An account with this email already exists")
    user = User(business_id=business.id, email=email, full_name=body.full_name, password_hash=hash_password(body.password), role=Role.CUSTOMER)
    db.add(user)
    db.flush()
    customer = db.scalars(select(Customer).where(Customer.business_id == business.id, Customer.email == email)).first()
    if customer is None:
        customer = Customer(business_id=business.id, email=email, full_name=body.full_name)
        db.add(customer)
    customer.user_id = user.id
    audit(db, business_id=business.id, actor=f"user:{user.id}", action="auth.registered", entity_type="user", entity_id=user.id, summary=f"Customer {email} registered", ip=request.client.host if request.client else None)
    db.commit()
    return _tokens(user)


@router.post("/login", dependencies=[Depends(auth_limit)])
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> dict[str, object]:
    user = db.scalars(select(User).where(User.email == body.email.lower())).first()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise Unauthorized("Invalid email or password")
    audit(db, business_id=user.business_id, actor=f"user:{user.id}", action="auth.login", entity_type="user", entity_id=user.id, summary=f"{user.email} signed in", ip=request.client.host if request.client else None)
    db.commit()
    return _tokens(user)


@router.post("/refresh", dependencies=[Depends(auth_limit)])
def refresh(body: RefreshIn, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        payload = decode_token(body.refresh_token, "refresh")
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise Unauthorized("Invalid refresh token") from exc
    if user is None or not user.is_active:
        raise Unauthorized("User inactive")
    return _tokens(user)


@router.get("/me")
def me(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> dict[str, object]:
    business = db.get(Business, principal.business_id)
    return {
        "user": user_out(principal.user),
        "customer_id": str(principal.customer_id) if principal.customer_id else None,
        "business": {"id": str(business.id), "name": business.name, "currency": business.currency} if business else None,
    }
