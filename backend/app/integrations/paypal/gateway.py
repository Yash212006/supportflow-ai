"""Thin, typed gateway over the APIMatic PayPal SDK operations in scope (see paypal-plan.md).

Returns plain dataclasses so the rest of the app never handles SDK models or UNSET.
Every call logs a sanitised PayPalTransaction row via the `recorder` callback.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

from paypal.core import UNSET
from paypal.models import (
    CapturedPayment,
    Order,
    OrderRequestDict,
    Refund,
    RefundRequestDict,
)

from app.integrations.paypal.client import get_paypal_client
from app.integrations.paypal.errors import PayPalError, call_paypal

Recorder = Callable[[dict[str, Any]], None]


def _v(x: Any) -> Any:
    """UNSET → None; open enums → their wire string."""
    if x is UNSET:
        return None
    if isinstance(x, Enum):
        return x.value
    return x


@dataclass
class PayPalOrderResult:
    id: str
    status: str
    approve_url: str | None = None
    capture_id: str | None = None
    capture_status: str | None = None
    capture_amount: Decimal | None = None
    capture_currency: str | None = None
    payer_email: str | None = None
    raw_summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class PayPalCaptureResult:
    id: str
    status: str
    amount: Decimal | None
    currency: str | None


@dataclass
class PayPalRefundResult:
    id: str
    status: str
    amount: Decimal | None
    currency: str | None
    status_reason: str | None


def _summarise_order(o: Order) -> PayPalOrderResult:
    oid, status = _v(o.id), _v(o.status)
    if not oid or not status:
        # 2xx without the members we depend on: outcome unknown (python-error-handling)
        raise PayPalError(kind="decode", message="PayPal order response missing id/status", outcome="unknown")
    approve = None
    for link in _v(o.links) or []:
        if link.rel in ("approve", "payer-action"):
            approve = link.href
    cap_id = cap_status = cap_cur = None
    cap_amt: Decimal | None = None
    for pu in _v(o.purchase_units) or []:
        payments = _v(pu.payments)
        caps = _v(payments.captures) if payments else None
        for c in caps or []:
            cap_id, cap_status = _v(c.id), _v(c.status)
            amt = _v(c.amount)
            if amt:
                cap_amt, cap_cur = Decimal(amt.value), amt.currency_code
    payer = _v(o.payer)
    email = _v(payer.email_address) if payer else None
    return PayPalOrderResult(
        id=oid,
        status=status,
        approve_url=approve,
        capture_id=cap_id,
        capture_status=cap_status,
        capture_amount=cap_amt,
        capture_currency=cap_cur,
        payer_email=email,
        raw_summary={"id": oid, "status": status, "capture_id": cap_id, "capture_status": cap_status},
    )


class PayPalGateway:
    def __init__(self, recorder: Recorder | None = None):
        self._record = recorder or (lambda _row: None)

    def _run(self, operation: str, fn: Callable[[], Any], *, is_write: bool, request_id: str | None, resource_hint: str | None) -> Any:
        start = time.perf_counter()
        try:
            result = call_paypal(fn, is_write=is_write)
        except PayPalError as err:
            self._record(
                {
                    "operation": operation,
                    "request_id": request_id,
                    "http_status": err.status_code,
                    "paypal_debug_id": err.debug_id,
                    "resource_id": resource_hint,
                    "outcome": "unknown" if err.outcome == "unknown" else ("not_sent" if err.outcome == "not_sent" else "rejected"),
                    "error_message": str(err),
                    "response_summary": {"error": err.to_dict()},
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                }
            )
            raise
        self._last_duration = int((time.perf_counter() - start) * 1000)
        return result

    def _ok(self, operation: str, request_id: str | None, resource_id: str, status: str, summary: dict[str, Any]) -> None:
        self._record(
            {
                "operation": operation,
                "request_id": request_id,
                "http_status": 200,
                "resource_id": resource_id,
                "resource_status": status,
                "outcome": "success",
                "response_summary": summary,
                "duration_ms": getattr(self, "_last_duration", None),
            }
        )

    # --- Orders API v2 -------------------------------------------------------------------------
    def create_order(
        self,
        *,
        amount: Decimal,
        currency: str,
        reference_id: str,
        description: str,
        request_id: str,
        return_url: str,
        cancel_url: str,
        brand_name: str,
    ) -> PayPalOrderResult:
        body: OrderRequestDict = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": reference_id,
                    "custom_id": reference_id,
                    "invoice_id": f"{reference_id}-{request_id[-8:]}",
                    "description": description[:127],
                    "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
                }
            ],
            "application_context": {
                "brand_name": brand_name[:127],
                "user_action": "PAY_NOW",
                "shipping_preference": "NO_SHIPPING",
                "return_url": return_url,
                "cancel_url": cancel_url,
            },
        }
        client = get_paypal_client()
        order = self._run(
            "orders.create_order",
            lambda: client.orders.create_order(body, pay_pal_request_id=request_id, prefer="return=representation"),
            is_write=True,
            request_id=request_id,
            resource_hint=reference_id,
        )
        res = _summarise_order(order)
        self._ok("orders.create_order", request_id, res.id, res.status, res.raw_summary)
        return res

    def get_order(self, paypal_order_id: str) -> PayPalOrderResult:
        client = get_paypal_client()
        order = self._run("orders.get_order", lambda: client.orders.get_order(paypal_order_id), is_write=False, request_id=None, resource_hint=paypal_order_id)
        res = _summarise_order(order)
        self._ok("orders.get_order", None, res.id, res.status, res.raw_summary)
        return res

    def capture_order(self, paypal_order_id: str, *, request_id: str) -> PayPalOrderResult:
        client = get_paypal_client()
        order = self._run(
            "orders.capture_order",
            lambda: client.orders.capture_order(paypal_order_id, pay_pal_request_id=request_id, prefer="return=representation"),
            is_write=True,
            request_id=request_id,
            resource_hint=paypal_order_id,
        )
        res = _summarise_order(order)
        self._ok("orders.capture_order", request_id, res.id, res.status, res.raw_summary)
        return res

    # --- Payments API v2 -----------------------------------------------------------------------
    def get_capture(self, capture_id: str) -> PayPalCaptureResult:
        client = get_paypal_client()
        cap: CapturedPayment = self._run(
            "payments.get_captured_payment", lambda: client.payments.get_captured_payment(capture_id), is_write=False, request_id=None, resource_hint=capture_id
        )
        cid, status = _v(cap.id), _v(cap.status)
        if not cid or not status:
            raise PayPalError(kind="decode", message="PayPal capture response missing id/status", outcome="rejected")
        amt = _v(cap.amount)
        res = PayPalCaptureResult(id=cid, status=status, amount=Decimal(amt.value) if amt else None, currency=amt.currency_code if amt else None)
        self._ok("payments.get_captured_payment", None, cid, status, {"id": cid, "status": status})
        return res

    def refund_capture(
        self, capture_id: str, *, amount: Decimal, currency: str, request_id: str, invoice_id: str, note: str
    ) -> PayPalRefundResult:
        body: RefundRequestDict = {
            "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
            "invoice_id": invoice_id,
            "custom_id": invoice_id,
            "note_to_payer": note[:255],
        }
        client = get_paypal_client()
        refund: Refund = self._run(
            "payments.refund_captured_payment",
            lambda: client.payments.refund_captured_payment(capture_id, pay_pal_request_id=request_id, prefer="return=representation", body=body),
            is_write=True,
            request_id=request_id,
            resource_hint=capture_id,
        )
        res = self._refund_result(refund, unknown_if_missing=True)
        self._ok("payments.refund_captured_payment", request_id, res.id, res.status, {"id": res.id, "status": res.status, "capture_id": capture_id})
        return res

    def get_refund(self, refund_id: str) -> PayPalRefundResult:
        client = get_paypal_client()
        refund: Refund = self._run("payments.get_refund", lambda: client.payments.get_refund(refund_id), is_write=False, request_id=None, resource_hint=refund_id)
        res = self._refund_result(refund, unknown_if_missing=False)
        self._ok("payments.get_refund", None, res.id, res.status, {"id": res.id, "status": res.status})
        return res

    @staticmethod
    def _refund_result(refund: Refund, *, unknown_if_missing: bool) -> PayPalRefundResult:
        rid, status = _v(refund.id), _v(refund.status)
        if not rid or not status:
            raise PayPalError(
                kind="decode", message="PayPal refund response missing id/status", outcome="unknown" if unknown_if_missing else "rejected"
            )
        amt = _v(refund.amount)
        details = _v(refund.status_details)
        reason = _v(details.reason) if details else None
        return PayPalRefundResult(
            id=rid, status=status, amount=Decimal(amt.value) if amt else None, currency=amt.currency_code if amt else None, status_reason=reason
        )
