"""Checkout, capture and webhook synchronisation against PayPal Sandbox.

Status changes on PAYPAL_SANDBOX payments only ever come from a PayPal API response or a
signature-verified webhook.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import String, cast, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import utcnow
from app.core.errors import Conflict, IntegrationUnavailable, NotFound, ValidationFailed
from app.integrations.paypal.errors import PayPalError
from app.integrations.paypal.gateway import PayPalGateway, PayPalOrderResult
from app.integrations.paypal.webhook_verify import verify_webhook
from app.models import Business, Order, Payment, Refund, WebhookEvent
from app.models.enums import (
    NotificationType,
    OrderStatus,
    PaymentSource,
    PaymentStatus,
    WebhookStatus,
)
from app.services.audit import audit
from app.services.notifications import notify_customer, notify_managers
from app.services.paypal_records import recorder_for

HANDLED_EVENTS = {
    "CHECKOUT.ORDER.APPROVED",
    "CHECKOUT.ORDER.COMPLETED",
    "PAYMENT.CAPTURE.COMPLETED",
    "PAYMENT.CAPTURE.PENDING",
    "PAYMENT.CAPTURE.DENIED",
    "PAYMENT.CAPTURE.DECLINED",
    "PAYMENT.CAPTURE.REFUNDED",
    "PAYMENT.CAPTURE.REVERSED",
    "PAYMENT.REFUND.PENDING",
    "PAYMENT.REFUND.FAILED",
    "PAYMENT.REFUND.CANCELLED",
    "PAYMENT.REFUND.COMPLETED",
}


def _require_paypal() -> None:
    if not get_settings().paypal_configured:
        raise IntegrationUnavailable("PayPal Sandbox is not configured. Add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET.", code="paypal_not_configured")


def _raise_http(err: PayPalError) -> None:
    status = 503 if err.outcome == "not_sent" else 502
    raise IntegrationUnavailable(f"PayPal: {err.user_message()}", code=f"paypal_{err.kind}", details=err.to_dict(), status_code=status)


def create_paypal_checkout(db: Session, *, order: Order, actor: str) -> Payment:
    _require_paypal()
    if order.status != OrderStatus.PENDING_PAYMENT:
        raise Conflict(f"Order #{order.order_number} is {order.status.value}; nothing to pay")
    existing = db.scalars(select(Payment).where(Payment.order_id == order.id, Payment.status.in_((PaymentStatus.CREATED, PaymentStatus.APPROVED)))).first()
    if existing is not None and existing.approve_url:
        return existing
    attempt = int(db.scalar(select(func.max(Payment.attempt)).where(Payment.order_id == order.id)) or 0) + 1
    payment = Payment(
        business_id=order.business_id,
        order_id=order.id,
        customer_id=order.customer_id,
        attempt=attempt,
        source=PaymentSource.PAYPAL_SANDBOX,
        status=PaymentStatus.CREATED,
        amount=order.total_amount,
        currency=order.currency,
    )
    try:
        db.add(payment)
        db.commit()  # claim (UNIQUE order_id, attempt) before calling PayPal
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("A checkout for this order is already being created") from exc

    s = get_settings()
    business = db.get(Business, order.business_id)
    gateway = PayPalGateway(recorder_for(db, business_id=order.business_id, payment_id=payment.id))
    try:
        res = gateway.create_order(
            amount=order.total_amount,
            currency=order.currency,
            reference_id=f"SF-{order.order_number}",
            description=f"Order #{order.order_number}",
            request_id=f"create-{payment.id}",
            return_url=f"{s.frontend_url}/customer/checkout/return?payment={payment.id}",
            cancel_url=f"{s.frontend_url}/customer/checkout/return?payment={payment.id}&cancelled=1",
            brand_name=business.name if business else "SupportFlow Store",
        )
    except PayPalError as err:
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = str(err)[:500]
        db.commit()
        _raise_http(err)
        raise  # unreachable
    payment.paypal_order_id = res.id
    payment.approve_url = res.approve_url
    payment.status = PaymentStatus.APPROVED if res.status == "APPROVED" else PaymentStatus.CREATED
    audit(db, business_id=order.business_id, actor=actor, action="paypal.order_created", entity_type="payment", entity_id=payment.id, summary=f"PayPal order {res.id} created for order #{order.order_number} ({order.currency} {order.total_amount})", data={"paypal_order_id": res.id, "status": res.status})
    db.commit()
    return payment


def capture_paypal_order(db: Session, *, payment: Payment, actor: str) -> Payment:
    _require_paypal()
    if payment.source != PaymentSource.PAYPAL_SANDBOX or not payment.paypal_order_id:
        raise ValidationFailed("Not a PayPal Sandbox payment")
    if payment.status == PaymentStatus.CAPTURED:
        return payment
    # Claim: conditional update so only one caller proceeds to PayPal.
    claimed = db.execute(
        update(Payment)
        .where(Payment.id == payment.id, Payment.status.in_((PaymentStatus.CREATED, PaymentStatus.APPROVED)), Payment.capture_claimed_at.is_(None))
        .values(status=PaymentStatus.CAPTURE_PENDING, capture_claimed_at=utcnow())
    ).rowcount  # type: ignore[attr-defined]
    db.commit()
    db.refresh(payment)
    if not claimed:
        if payment.status in (PaymentStatus.CAPTURE_PENDING, PaymentStatus.CAPTURED):
            return payment
        raise Conflict(f"Payment is {payment.status.value}; cannot capture")
    gateway = PayPalGateway(recorder_for(db, business_id=payment.business_id, payment_id=payment.id))
    try:
        res = gateway.capture_order(payment.paypal_order_id, request_id=f"capture-{payment.id}")
    except PayPalError as err:
        if err.outcome == "unknown":
            # leave CAPTURE_PENDING; a GET or webhook will settle it
            payment.failure_reason = str(err)[:500]
            db.commit()
            _raise_http(err)
        payment.status = PaymentStatus.APPROVED if err.name == "UNPROCESSABLE_ENTITY" and "ORDER_NOT_APPROVED" in str(err.details) else PaymentStatus.FAILED
        payment.capture_claimed_at = None
        payment.failure_reason = str(err)[:500]
        db.commit()
        _raise_http(err)
    apply_order_result(db, payment, res, actor=actor)
    db.commit()
    return payment


def sync_paypal_order(db: Session, *, payment: Payment, actor: str) -> Payment:
    _require_paypal()
    if not payment.paypal_order_id:
        raise ValidationFailed("Payment has no PayPal order id")
    gateway = PayPalGateway(recorder_for(db, business_id=payment.business_id, payment_id=payment.id))
    try:
        res = gateway.get_order(payment.paypal_order_id)
    except PayPalError as err:
        _raise_http(err)
        raise
    apply_order_result(db, payment, res, actor=actor)
    db.commit()
    return payment


def apply_order_result(db: Session, payment: Payment, res: PayPalOrderResult, *, actor: str) -> None:
    order = db.get(Order, payment.order_id)
    assert order is not None
    if res.payer_email:
        payment.payer_email = res.payer_email
    if res.capture_id:
        payment.paypal_capture_id = res.capture_id
    if res.capture_status == "COMPLETED" and res.status == "COMPLETED":
        if res.capture_amount is not None and res.capture_amount != payment.amount:
            payment.failure_reason = f"Captured amount {res.capture_amount} differs from expected {payment.amount}"
        if payment.status != PaymentStatus.CAPTURED and payment.refunded_amount == 0:
            payment.status = PaymentStatus.CAPTURED
            payment.captured_at = utcnow()
            if order.status == OrderStatus.PENDING_PAYMENT:
                order.status = OrderStatus.PAID
            notify_customer(db, customer_id=payment.customer_id, type_=NotificationType.PAYMENT_CAPTURED, title=f"Payment received for order #{order.order_number}", body=f"{payment.currency} {payment.amount} captured by PayPal (capture {res.capture_id}).", link=f"/customer/orders/{order.id}")
            audit(db, business_id=payment.business_id, actor="paypal", action="paypal.captured", entity_type="payment", entity_id=payment.id, summary=f"PayPal capture {res.capture_id} COMPLETED for order #{order.order_number}", data={"by": actor})
    elif res.capture_status in ("DECLINED", "FAILED"):
        payment.status = PaymentStatus.DECLINED
        payment.failure_reason = f"PayPal capture {res.capture_status}"
        notify_customer(db, customer_id=payment.customer_id, type_=NotificationType.PAYMENT_FAILED, title=f"Payment for order #{order.order_number} was declined", body="PayPal declined the capture. Please try another payment method.", link=f"/customer/orders/{order.id}")
    elif res.capture_status == "PENDING":
        payment.status = PaymentStatus.CAPTURE_PENDING
    elif res.status == "APPROVED" and payment.status == PaymentStatus.CREATED:
        payment.status = PaymentStatus.APPROVED
    elif res.status == "VOIDED":
        payment.status = PaymentStatus.VOIDED


# ------------------------------------------------------------------------------------------ webhooks
def ingest_webhook(db: Session, *, headers: dict[str, str], event: dict[str, Any]) -> WebhookEvent:
    event_id = str(event.get("id") or "")
    event_type = str(event.get("event_type") or "UNKNOWN")
    if not event_id:
        raise ValidationFailed("Webhook event has no id")
    existing = db.scalars(select(WebhookEvent).where(WebhookEvent.event_id == event_id)).first()
    if existing is not None and existing.status in (WebhookStatus.PROCESSED, WebhookStatus.IGNORED):
        return existing  # duplicate delivery: idempotent no-op

    result = verify_webhook(headers, event)
    resource = event.get("resource") or {}
    if existing is None:
        row = WebhookEvent(
            event_id=event_id,
            event_type=event_type,
            resource_id=str(resource.get("id")) if resource.get("id") else None,
            status=WebhookStatus.RECEIVED,
            verification_status=result.status,
            payload=event,
        )
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError:
            return db.scalars(select(WebhookEvent).where(WebhookEvent.event_id == event_id)).one()
    else:
        row = existing
        row.verification_status = result.status

    if not result.verified:
        row.status = WebhookStatus.REJECTED
        row.processing_note = f"Signature verification failed: {result.status} {result.detail}".strip()
        audit(db, business_id=None, actor="paypal", action="webhook.rejected", entity_type="webhook", entity_id=event_id, summary=f"Rejected unverified webhook {event_type}", data={"status": result.status, "detail": result.detail})
        db.commit()
        return row

    try:
        note = _process_event(db, row, event_type, resource)
        row.status = WebhookStatus.PROCESSED if note != "ignored" else WebhookStatus.IGNORED
        row.processing_note = note
        row.processed_at = utcnow()
    except Exception as exc:  # keep the event for replay; never half-apply
        db.rollback()
        row = db.scalars(select(WebhookEvent).where(WebhookEvent.event_id == event_id)).one()
        row.status = WebhookStatus.FAILED
        row.processing_note = f"{type(exc).__name__}: {exc}"[:500]
    db.commit()
    return row


def _process_event(db: Session, row: WebhookEvent, event_type: str, resource: dict[str, Any]) -> str:
    from app.workflows.execution_engine import ExecutionEngine

    if event_type not in HANDLED_EVENTS:
        return "ignored"
    rid = str(resource.get("id") or "")
    if event_type.startswith("CHECKOUT.ORDER"):
        payment = db.scalars(select(Payment).where(Payment.paypal_order_id == rid).with_for_update(key_share=True)).first()
        if payment is None:
            return f"no payment for PayPal order {rid}"
        row.business_id = payment.business_id
        if event_type == "CHECKOUT.ORDER.APPROVED" and payment.status == PaymentStatus.CREATED:
            payment.status = PaymentStatus.APPROVED
        return f"order {rid} → {resource.get('status')}"
    if event_type.startswith("PAYMENT.CAPTURE"):
        payment = db.scalars(select(Payment).where(Payment.paypal_capture_id == rid).with_for_update(key_share=True)).first()
        if payment is None:
            order_id = ((resource.get("supplementary_data") or {}).get("related_ids") or {}).get("order_id")
            payment = db.scalars(select(Payment).where(Payment.paypal_order_id == order_id).with_for_update(key_share=True)).first() if order_id else None
        if payment is None:
            return f"no payment for capture {rid}"
        row.business_id = payment.business_id
        payment.paypal_capture_id = payment.paypal_capture_id or rid
        order = db.get(Order, payment.order_id)
        assert order is not None
        if event_type == "PAYMENT.CAPTURE.COMPLETED" and payment.status in (PaymentStatus.CREATED, PaymentStatus.APPROVED, PaymentStatus.CAPTURE_PENDING):
            payment.status, payment.captured_at = PaymentStatus.CAPTURED, utcnow()
            if order.status == OrderStatus.PENDING_PAYMENT:
                order.status = OrderStatus.PAID
            notify_customer(db, customer_id=payment.customer_id, type_=NotificationType.PAYMENT_CAPTURED, title=f"Payment received for order #{order.order_number}", body=f"PayPal capture {rid} completed.", link=f"/customer/orders/{order.id}")
        elif event_type in ("PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.DECLINED"):
            payment.status = PaymentStatus.DECLINED
            payment.failure_reason = f"PayPal {event_type}"
            notify_managers(db, business_id=payment.business_id, type_=NotificationType.PAYMENT_FAILED, title=f"Capture denied — order #{order.order_number}", body=f"PayPal capture {rid} was denied.", link=f"/manager/payments/{payment.id}")
        elif event_type == "PAYMENT.CAPTURE.PENDING":
            payment.status = PaymentStatus.CAPTURE_PENDING
        return f"capture {rid}: {event_type}"
    if event_type.startswith("PAYMENT.REFUND"):
        refund = db.scalars(select(Refund).where(Refund.paypal_refund_id == rid)).first()
        if refund is None:
            # Our refund may still be OUTCOME_UNKNOWN (no id yet): match by invoice id we sent.
            inv = str(resource.get("invoice_id") or "")
            if inv.startswith("RF-"):
                refund = db.scalars(select(Refund).where(func.substr(cast(Refund.id, String), 1, 8) == inv[3:])).first()
        if refund is None:
            return f"no refund for PayPal refund {rid}"
        row.business_id = refund.business_id
        status = str(resource.get("status") or event_type.rsplit(".", 1)[-1])
        reason = (resource.get("status_details") or {}).get("reason")
        ExecutionEngine(db).apply_refund_status(refund, rid, status, actor="paypal:webhook", reason=reason)
        return f"refund {rid} → {status}"
    return "ignored"


def get_payment(db: Session, business_id: uuid.UUID, payment_id: uuid.UUID, customer_id: uuid.UUID | None = None) -> Payment:
    p = db.get(Payment, payment_id)
    if p is None or p.business_id != business_id or (customer_id is not None and p.customer_id != customer_id):
        raise NotFound("Payment not found")
    return p

