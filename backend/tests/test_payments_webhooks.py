"""PayPal checkout/capture through the API and webhook ingestion (stub transport; not real transactions)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.integrations.paypal import webhook_verify
from app.integrations.paypal.webhook_verify import VerificationResult, verify_webhook
from app.models import Order, Payment, Refund, WebhookEvent
from app.models.enums import OrderStatus, PaymentStatus, RefundStatus, WebhookStatus
from tests.conftest import login, make_customer, make_paid_order
from tests.paypal_stub import StubTransport, json_response, token_response


def new_customer_order(client: TestClient, db) -> tuple[dict[str, str], dict]:  # type: ignore[no-untyped-def,type-arg]
    c = make_customer(db, with_login=True)
    h = login(client, c.email, "Customer@123")
    products = client.get("/api/customer/products", headers=h).json()
    p = next(x for x in products if Decimal(str(x["price"])) < 1000)
    r = client.post("/api/customer/orders", headers=h, json={"items": [{"product_id": p["id"], "quantity": 1}]})
    assert r.status_code == 200, r.text
    return h, r.json()


def created_order_body(pid: str) -> dict:  # type: ignore[type-arg]
    return {"id": pid, "status": "PAYER_ACTION_REQUIRED", "links": [{"href": f"https://www.sandbox.paypal.com/checkoutnow?token={pid}", "rel": "payer-action", "method": "GET"}]}


def captured_order_body(pid: str, cap: str, value: str) -> dict:  # type: ignore[type-arg]
    return {
        "id": pid, "status": "COMPLETED",
        "payer": {"email_address": "buyer@example.com"},
        "purchase_units": [{"reference_id": "x", "payments": {"captures": [{"id": cap, "status": "COMPLETED", "amount": {"currency_code": "INR", "value": value}}]}}],
    }


def test_checkout_then_capture(client: TestClient, db, no_real_paypal: StubTransport) -> None:  # type: ignore[no-untyped-def]
    h, order = new_customer_order(client, db)
    pid = f"PP{uuid.uuid4().hex[:15].upper()}"
    no_real_paypal.queue(token_response(), json_response(200, created_order_body(pid)))
    r = client.post(f"/api/customer/orders/{order['id']}/pay", headers=h)
    assert r.status_code == 200, r.text
    pay = r.json()
    assert pay["paypal_order_id"] == pid
    assert pay["approve_url"].startswith("https://www.sandbox.paypal.com/")
    assert pay["status"] in ("CREATED",)
    create_req = no_real_paypal.operation_requests[-1]
    assert create_req.url.endswith("/v2/checkout/orders")
    assert create_req.headers["paypal-request-id"]
    cap = f"CP{uuid.uuid4().hex[:15].upper()}"
    no_real_paypal.queue(json_response(201, captured_order_body(pid, cap, order["total_amount"])))
    r2 = client.post(f"/api/customer/payments/{pay['id']}/capture", headers=h)
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "CAPTURED"
    assert r2.json()["paypal_capture_id"] == cap
    db.expire_all()
    o = db.get(Order, uuid.UUID(order["id"]))
    assert o.status == OrderStatus.PAID
    # capturing again does not call PayPal again
    n = len(no_real_paypal.requests)
    assert client.post(f"/api/customer/payments/{pay['id']}/capture", headers=h).json()["status"] == "CAPTURED"
    assert len(no_real_paypal.requests) == n


def test_declined_capture_is_not_success(client: TestClient, db, no_real_paypal: StubTransport) -> None:  # type: ignore[no-untyped-def]
    h, order = new_customer_order(client, db)
    pid = f"PP{uuid.uuid4().hex[:15].upper()}"
    no_real_paypal.queue(token_response(), json_response(200, created_order_body(pid)))
    pay = client.post(f"/api/customer/orders/{order['id']}/pay", headers=h).json()
    no_real_paypal.queue(json_response(422, {"name": "UNPROCESSABLE_ENTITY", "message": "The requested action could not be performed.", "debug_id": "dbg-decl", "details": [{"issue": "INSTRUMENT_DECLINED", "description": "The instrument presented was declined."}]}))
    r = client.post(f"/api/customer/payments/{pay['id']}/capture", headers=h)
    assert r.status_code == 502, r.text
    assert r.json()["error"]["code"].startswith("paypal_"), r.text
    assert r.json()["error"]["details"]["outcome"] == "rejected", r.text
    db.expire_all()
    p = db.get(Payment, uuid.UUID(pay["id"]))
    assert p.status == PaymentStatus.FAILED
    assert db.get(Order, uuid.UUID(order["id"])).status == OrderStatus.PENDING_PAYMENT


def test_paypal_not_configured_is_reported(client: TestClient, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.core.config import get_settings

    h, order = new_customer_order(client, db)
    monkeypatch.setattr(get_settings(), "paypal_client_id", "")
    r = client.post(f"/api/customer/orders/{order['id']}/pay", headers=h)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "paypal_not_configured"


def _refund_event(eid: str, rid: str, invoice: str, status: str = "COMPLETED") -> dict:  # type: ignore[type-arg]
    return {"id": eid, "event_type": f"PAYMENT.REFUND.{status}", "resource": {"id": rid, "status": status, "invoice_id": invoice, "amount": {"currency_code": "INR", "value": "100.00"}}}


def test_unverified_webhook_is_rejected_and_not_applied(client: TestClient, db) -> None:  # type: ignore[no-untyped-def]
    eid = f"WH-{uuid.uuid4()}"
    r = client.post("/api/paypal/webhooks", json=_refund_event(eid, "RFX", "RF-00000000"))
    assert r.status_code == 200
    assert r.json()["status"] == "REJECTED"
    assert r.json()["verification"] == "MISSING_HEADERS"


def test_verified_webhook_settles_unknown_refund_once(client: TestClient, db, no_real_paypal: StubTransport, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import httpx2

    from app.workflows.execution_engine import ExecutionEngine

    c = make_customer(db)
    order, pay = make_paid_order(db, c, "100.00")
    no_real_paypal.queue(token_response())
    no_real_paypal.fail_next_with(httpx2.ReadTimeout("no reply"))
    out = ExecutionEngine(db).request_refund(business_id=order.business_id, order=order, amount=None, reason="test", requested_by="test", idempotency_key=f"wh:{uuid.uuid4()}")
    assert out.summary["refund_status"] == "OUTCOME_UNKNOWN"
    refund_id = out.summary["refund_id"]
    monkeypatch.setattr("app.services.payments.verify_webhook", lambda headers, event: VerificationResult(True, "SUCCESS"))
    eid = f"WH-{uuid.uuid4()}"
    ev = _refund_event(eid, "RF-WEBHOOK-1", f"RF-{refund_id[:8]}")
    r = client.post("/api/paypal/webhooks", json=ev)
    assert r.json()["status"] == "PROCESSED", r.json()
    db.expire_all()
    refund = db.get(Refund, uuid.UUID(refund_id))
    assert refund.status == RefundStatus.COMPLETED
    assert refund.paypal_refund_id == "RF-WEBHOOK-1"
    p = db.get(Payment, pay.id)
    assert p.refunded_amount == Decimal("100.00")
    # duplicate delivery is a no-op
    r2 = client.post("/api/paypal/webhooks", json=ev)
    assert r2.json()["status"] == "PROCESSED"
    db.expire_all()
    assert db.get(Payment, pay.id).refunded_amount == Decimal("100.00")
    assert len(db.scalars(select(WebhookEvent).where(WebhookEvent.event_id == eid)).all()) == 1


def test_webhook_verification_calls_paypal_and_trusts_only_success(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    headers = {h: "x" for h in webhook_verify.REQUIRED_HEADERS}
    seen: list[dict] = []  # type: ignore[type-arg]

    def handler(status: str):  # type: ignore[no-untyped-def]
        def h(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/v1/oauth2/token"):
                return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
            import json

            seen.append(json.loads(request.content))
            return httpx.Response(200, json={"verification_status": status})

        return h

    monkeypatch.setattr(webhook_verify, "_tokens", webhook_verify._TokenCache())
    ok = verify_webhook(headers, {"id": "e1"}, http=httpx.Client(transport=httpx.MockTransport(handler("SUCCESS"))))
    assert ok.verified and ok.status == "SUCCESS"
    assert seen[-1]["webhook_id"] == "WH-TEST"
    bad = verify_webhook(headers, {"id": "e2"}, http=httpx.Client(transport=httpx.MockTransport(handler("FAILURE"))))
    assert not bad.verified and bad.status == "FAILURE"
    missing = verify_webhook({}, {"id": "e3"})
    assert not missing.verified and missing.status == "MISSING_HEADERS"


def test_webhook_for_unknown_resource_is_harmless(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("app.services.payments.verify_webhook", lambda headers, event: VerificationResult(True, "SUCCESS"))
    r = client.post("/api/paypal/webhooks", json={"id": f"WH-{uuid.uuid4()}", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {"id": "NOPE"}})
    assert r.json()["status"] == "PROCESSED"
    r2 = client.post("/api/paypal/webhooks", json={"id": f"WH-{uuid.uuid4()}", "event_type": "BILLING.PLAN.CREATED", "resource": {"id": "x"}})
    assert r2.json()["status"] == "IGNORED"
    assert WebhookStatus.IGNORED


def test_undecodable_error_on_write_is_treated_as_unknown(client: TestClient, db, no_real_paypal: StubTransport) -> None:  # type: ignore[no-untyped-def]
    """A capture error body we cannot decode never becomes success or a definitive failure."""
    h, order = new_customer_order(client, db)
    pid = f"PP{uuid.uuid4().hex[:15].upper()}"
    no_real_paypal.queue(token_response(), json_response(200, created_order_body(pid)))
    pay = client.post(f"/api/customer/orders/{order['id']}/pay", headers=h).json()
    no_real_paypal.queue(json_response(422, {"name": "UNPROCESSABLE_ENTITY"}))
    r = client.post(f"/api/customer/payments/{pay['id']}/capture", headers=h)
    assert r.status_code == 502
    assert r.json()["error"]["details"]["outcome"] == "unknown"
    db.expire_all()
    assert db.get(Payment, uuid.UUID(pay["id"])).status == PaymentStatus.CAPTURE_PENDING
    assert db.get(Order, uuid.UUID(order["id"])).status == OrderStatus.PENDING_PAYMENT


def test_paypal_issue_code_is_shown_to_user() -> None:
    from app.integrations.paypal.errors import PayPalError

    err = PayPalError(kind="api", message="The requested action could not be performed, semantically incorrect, or failed business validation.", outcome="rejected", status_code=422, name="UNPROCESSABLE_ENTITY", debug_id="abc", details=[{"issue": "CURRENCY_NOT_SUPPORTED", "description": "Currency code is not currently supported.", "field": None}])
    msg = err.user_message()
    assert "CURRENCY_NOT_SUPPORTED" in msg
    assert "DEMO_CURRENCY=USD" in msg
    assert "issue: CURRENCY_NOT_SUPPORTED" in str(err)
