"""PayPal endpoints: staff-facing order operations, refund status, and the webhook receiver."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serializers import payment_out, refund_out
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import Principal, require_manager, require_staff
from app.core.errors import NotFound, ValidationFailed
from app.models import Order, Payment, Refund, WebhookEvent
from app.services import payments as payment_service
from app.services.audit import jsonable
from app.workflows.execution_engine import ExecutionEngine

router = APIRouter(prefix="/api/paypal", tags=["paypal"])


class CreateIn(BaseModel):
    order_id: uuid.UUID


@router.post("/orders")
def create_order(body: CreateIn, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Create a PayPal order for an internal order (e.g. to send a payment link)."""
    o = db.get(Order, body.order_id)
    if o is None or o.business_id != p.business_id:
        raise NotFound("Order not found")
    return payment_out(payment_service.create_paypal_checkout(db, order=o, actor=p.actor))


def _by_paypal_order(db: Session, p: Principal, paypal_order_id: str) -> Payment:
    pay = db.scalars(select(Payment).where(Payment.paypal_order_id == paypal_order_id, Payment.business_id == p.business_id)).first()
    if pay is None:
        raise NotFound("PayPal order not found for this business")
    return pay


@router.get("/orders/{paypal_order_id}")
def get_order(paypal_order_id: str, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    pay = _by_paypal_order(db, p, paypal_order_id)
    return payment_out(payment_service.sync_paypal_order(db, payment=pay, actor=p.actor))


@router.post("/orders/{paypal_order_id}/capture")
def capture(paypal_order_id: str, p: Principal = Depends(require_manager), db: Session = Depends(get_db)) -> dict[str, Any]:
    pay = _by_paypal_order(db, p, paypal_order_id)
    return payment_out(payment_service.capture_paypal_order(db, payment=pay, actor=p.actor))


class RefundIn(BaseModel):
    amount: str | None = Field(default=None, pattern=r"^\d+(\.\d{1,2})?$")
    reason: str = Field(min_length=3, max_length=500)


@router.post("/captures/{capture_id}/refund")
def refund_capture(capture_id: str, body: RefundIn, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Refund request against a capture. Routed through policy + execution engine, never direct."""
    from decimal import Decimal

    pay = db.scalars(select(Payment).where(Payment.paypal_capture_id == capture_id, Payment.business_id == p.business_id)).first()
    if pay is None:
        raise NotFound("Capture not found for this business")
    order = db.get(Order, pay.order_id)
    assert order
    outcome = ExecutionEngine(db).request_refund(
        business_id=p.business_id,
        order=order,
        amount=Decimal(body.amount) if body.amount else None,
        reason=body.reason,
        requested_by=p.actor,
        idempotency_key=f"capture-refund:{capture_id}:{body.amount or 'full'}:{uuid.uuid4().hex[:8]}",
        requested_by_user_id=p.user_id,
    )
    return outcome.summary


@router.get("/refunds/{paypal_refund_id}")
def refund_status(paypal_refund_id: str, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Reads GET /v2/payments/refunds/{id} and synchronises the local refund."""
    from app.integrations.paypal.errors import PayPalError
    from app.integrations.paypal.gateway import PayPalGateway
    from app.services.paypal_records import recorder_for

    r = db.scalars(select(Refund).where(Refund.paypal_refund_id == paypal_refund_id, Refund.business_id == p.business_id)).first()
    if r is None:
        raise NotFound("Refund not found")
    try:
        res = PayPalGateway(recorder_for(db, business_id=r.business_id, payment_id=r.payment_id, refund_id=r.id)).get_refund(paypal_refund_id)
    except PayPalError as err:
        payment_service._raise_http(err)
        raise
    ExecutionEngine(db).apply_refund_status(r, res.id, res.status, actor=p.actor, reason=res.status_reason)
    db.commit()
    return refund_out(r)


@router.post("/webhooks")
async def webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    """PayPal webhook receiver. Unverified events are stored as REJECTED and never applied."""
    raw = await request.body()
    if len(raw) > 512_000:
        raise ValidationFailed("Payload too large")
    try:
        event = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationFailed("Invalid JSON") from exc
    if not isinstance(event, dict):
        raise ValidationFailed("Invalid event")
    from starlette.concurrency import run_in_threadpool

    row = await run_in_threadpool(payment_service.ingest_webhook, db, headers=dict(request.headers), event=event)
    return {"event_id": row.event_id, "status": row.status.value, "verification": row.verification_status}


@router.get("/webhooks/events")
def webhook_events(limit: int = 50, p: Principal = Depends(require_manager), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(WebhookEvent).where((WebhookEvent.business_id == p.business_id) | (WebhookEvent.business_id.is_(None))).order_by(WebhookEvent.created_at.desc()).limit(min(limit, 200))).all()
    return [
        jsonable({"id": w.id, "event_id": w.event_id, "event_type": w.event_type, "resource_id": w.resource_id, "status": w.status, "verification_status": w.verification_status, "processing_note": w.processing_note, "created_at": w.created_at, "processed_at": w.processed_at})
        for w in rows
    ]


@router.get("/status")
def status(p: Principal = Depends(require_staff)) -> dict[str, Any]:
    s = get_settings()
    return {"configured": s.paypal_configured, "webhook_configured": s.paypal_webhook_configured, "base_url": s.paypal_base_url, "environment": "sandbox" if "sandbox" in s.paypal_base_url else "live"}
