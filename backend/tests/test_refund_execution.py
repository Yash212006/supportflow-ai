"""Refund execution: policy routing, state machine, idempotency, PayPal failure handling.

PayPal is the APIMatic SDK client pointed at a stub transport; responses are shaped like the
documented Payments v2 refund resource. Nothing here represents a real PayPal transaction."""

from __future__ import annotations

import uuid
from decimal import Decimal

import httpx2
import pytest
from paypal.core import JsonBody
from sqlalchemy import select

from app.models import ApprovalRequest, PayPalTransaction, Refund, User
from app.models.enums import ActionState, ApprovalStatus, RefundStatus
from app.workflows.execution_engine import ExecutionEngine
from tests.conftest import make_customer, make_paid_order, northwind
from tests.paypal_stub import StubTransport, json_response, token_response


def refund_body(rid: str, status: str, value: str) -> dict:  # type: ignore[type-arg]
    return {"id": rid, "status": status, "amount": {"currency_code": "INR", "value": value}}


def request(db, order, amount: str | None, key: str | None = None):  # type: ignore[no-untyped-def]
    return ExecutionEngine(db).request_refund(
        business_id=order.business_id, order=order, amount=Decimal(amount) if amount else None, reason="Item arrived damaged",
        requested_by="test", idempotency_key=key or f"test:{uuid.uuid4()}",
    )


def manager(db) -> User:  # type: ignore[no-untyped-def]
    return db.scalars(select(User).where(User.email == "manager@supportflow.demo")).one()


def test_small_refund_auto_executes_via_paypal(db, no_real_paypal: StubTransport) -> None:  # type: ignore[no-untyped-def]
    c = make_customer(db)
    order, pay = make_paid_order(db, c, "800.00")
    no_real_paypal.queue(token_response(), json_response(201, refund_body("RF-OK-1", "COMPLETED", "800.00")))
    out = request(db, order, None)
    s = out.summary
    assert s["decision"] == "AUTO_EXECUTE"
    assert s["action_state"] == "SUCCEEDED"
    assert s["refund_status"] == "COMPLETED"
    assert s["paypal_refund_id"] == "RF-OK-1"
    db.refresh(pay)
    assert pay.refunded_amount == Decimal("800.00")
    req = no_real_paypal.operation_requests[-1]
    assert req.method == "POST" and req.url.endswith(f"/v2/payments/captures/{pay.paypal_capture_id}/refund")
    assert isinstance(req.body, JsonBody) and isinstance(req.body.value, dict)
    assert req.body.value["amount"] == {"currency_code": "INR", "value": "800.00"}
    assert req.headers["paypal-request-id"] == out.action.idempotency_key
    # sanitised PayPal transaction log, no secrets
    logs = db.scalars(select(PayPalTransaction).where(PayPalTransaction.payment_id == pay.id)).all()
    assert logs and "test-client-secret" not in str([lg.__dict__ for lg in logs])


def test_duplicate_request_does_not_refund_twice(db, no_real_paypal: StubTransport) -> None:  # type: ignore[no-untyped-def]
    c = make_customer(db)
    order, pay = make_paid_order(db, c, "300.00")
    no_real_paypal.queue(token_response(), json_response(201, refund_body("RF-DUP-1", "COMPLETED", "300.00")))
    key = f"dup:{uuid.uuid4()}"
    first = request(db, order, None, key)
    second = request(db, order, None, key)
    assert second.duplicate is True
    assert second.action.id == first.action.id
    assert len(no_real_paypal.operation_requests) == 1
    db.refresh(pay)
    assert pay.refunded_amount == Decimal("300.00")


def test_paypal_rejection_marks_failed_and_keeps_balance(db, no_real_paypal: StubTransport) -> None:  # type: ignore[no-untyped-def]
    c = make_customer(db)
    order, pay = make_paid_order(db, c, "400.00")
    no_real_paypal.queue(token_response(), json_response(422, {"name": "UNPROCESSABLE_ENTITY", "message": "The requested action could not be performed.", "debug_id": "dbg123", "details": [{"issue": "CAPTURE_FULLY_REFUNDED", "description": "already refunded"}]}))
    out = request(db, order, None)
    assert out.summary["action_state"] == "FAILED"
    assert out.summary["refund_status"] == "FAILED"
    assert out.summary["paypal_refund_id"] is None
    assert "could not be performed" in (out.summary["error"] or "")
    db.refresh(pay)
    assert pay.refunded_amount == Decimal("0")


def test_connection_refused_is_failed_not_unknown(db, no_real_paypal: StubTransport) -> None:  # type: ignore[no-untyped-def]
    c = make_customer(db)
    order, pay = make_paid_order(db, c, "200.00")
    no_real_paypal.queue(token_response())
    no_real_paypal.fail_next_with(httpx2.ConnectError("refused"))
    out = request(db, order, None)
    assert out.summary["action_state"] == "FAILED"
    db.refresh(pay)
    assert pay.refunded_amount == Decimal("0")


def test_timeout_is_outcome_unknown_then_reconciled(db, no_real_paypal: StubTransport) -> None:  # type: ignore[no-untyped-def]
    c = make_customer(db)
    order, pay = make_paid_order(db, c, "250.00")
    no_real_paypal.queue(token_response())
    no_real_paypal.fail_next_with(httpx2.ReadTimeout("no reply"))
    out = request(db, order, None)
    assert out.summary["action_state"] == "PENDING_CONFIRMATION"
    assert out.summary["refund_status"] == "OUTCOME_UNKNOWN"
    db.refresh(pay)
    assert pay.refunded_amount == Decimal("250.00")  # reserved so it cannot be refunded twice meanwhile
    # reconcile: same PayPal-Request-Id, PayPal returns the original refund
    no_real_paypal.queue(json_response(200, refund_body("RF-REC-1", "COMPLETED", "250.00")))
    rec = ExecutionEngine(db).reconcile(out.action, actor="test")
    assert rec.summary["action_state"] == "SUCCEEDED"
    assert rec.summary["refund_status"] == "COMPLETED"
    reqs = no_real_paypal.operation_requests
    assert reqs[-1].headers["paypal-request-id"] == reqs[-2].headers["paypal-request-id"]
    db.refresh(pay)
    assert pay.refunded_amount == Decimal("250.00")


def test_pending_refund_waits_for_confirmation(db, no_real_paypal: StubTransport) -> None:  # type: ignore[no-untyped-def]
    c = make_customer(db)
    order, _ = make_paid_order(db, c, "150.00")
    no_real_paypal.queue(token_response(), json_response(201, refund_body("RF-PEND-1", "PENDING", "150.00")))
    out = request(db, order, None)
    assert out.summary["action_state"] == "PENDING_CONFIRMATION"
    assert out.summary["refund_status"] == "PENDING"


def test_truncated_paypal_response_is_not_success(db, no_real_paypal: StubTransport) -> None:  # type: ignore[no-untyped-def]
    c = make_customer(db)
    order, _ = make_paid_order(db, c, "120.00")
    no_real_paypal.queue(token_response(), json_response(201, {}))
    out = request(db, order, None)
    assert out.summary["action_state"] != "SUCCEEDED"
    assert out.summary["refund_status"] in ("OUTCOME_UNKNOWN",)


def test_bad_paypal_credentials_fail_safely(db, no_real_paypal: StubTransport) -> None:  # type: ignore[no-untyped-def]
    c = make_customer(db)
    order, pay = make_paid_order(db, c, "100.00")
    no_real_paypal.queue(json_response(401, {"error": "invalid_client", "error_description": "Client Authentication failed"}))
    out = request(db, order, None)
    assert out.summary["action_state"] == "FAILED"
    assert "OAuth" in (out.summary["error"] or "")
    db.refresh(pay)
    assert pay.refunded_amount == Decimal("0")


def test_mid_value_refund_needs_approval_then_executes(db, no_real_paypal: StubTransport) -> None:  # type: ignore[no-untyped-def]
    c = make_customer(db)
    order, pay = make_paid_order(db, c, "2500.00")
    out = request(db, order, None)
    assert out.summary["decision"] == "REQUIRES_APPROVAL"
    assert out.summary["action_state"] == "REQUIRES_APPROVAL"
    assert no_real_paypal.operation_requests == []  # nothing sent before approval
    appr = db.get(ApprovalRequest, uuid.UUID(out.summary["approval_id"]))
    no_real_paypal.queue(token_response(), json_response(201, refund_body("RF-APP-1", "COMPLETED", "2500.00")))
    done = ExecutionEngine(db).approve(appr, manager=manager(db), note="Verified photos")
    assert done.summary["action_state"] == "SUCCEEDED"
    db.refresh(appr)
    assert appr.status == ApprovalStatus.APPROVED
    with pytest.raises(Exception):
        ExecutionEngine(db).approve(appr, manager=manager(db), note="again")


def test_rejected_approval_never_calls_paypal(db, no_real_paypal: StubTransport) -> None:  # type: ignore[no-untyped-def]
    c = make_customer(db)
    order, pay = make_paid_order(db, c, "3000.00")
    out = request(db, order, None)
    appr = db.get(ApprovalRequest, uuid.UUID(out.summary["approval_id"]))
    res = ExecutionEngine(db).reject(appr, manager=manager(db), note="No evidence")
    assert res.summary["refund_status"] == "REJECTED"
    assert no_real_paypal.operation_requests == []


def test_high_value_refund_is_escalated(db, no_real_paypal: StubTransport) -> None:  # type: ignore[no-untyped-def]
    c = make_customer(db)
    order, _ = make_paid_order(db, c, "9000.00")
    out = request(db, order, None)
    assert out.summary["decision"] == "ESCALATED"
    assert no_real_paypal.operation_requests == []


def test_amount_above_refundable_is_rejected(db, no_real_paypal: StubTransport) -> None:  # type: ignore[no-untyped-def]
    c = make_customer(db)
    order, _ = make_paid_order(db, c, "500.00")
    out = request(db, order, "800.00")
    assert out.summary["decision"] == "REJECTED"
    assert out.summary["action_state"] == "REJECTED"
    assert no_real_paypal.operation_requests == []


def test_sample_payments_are_never_refunded_through_paypal(db, no_real_paypal: StubTransport) -> None:  # type: ignore[no-untyped-def]
    c = make_customer(db)
    order, pay = make_paid_order(db, c, "300.00", source="SEED_SAMPLE")
    out = request(db, order, None)
    assert out.summary["action_state"] == "FAILED"
    assert "sample" in (out.summary["error"] or "").lower()
    assert no_real_paypal.operation_requests == []
    db.refresh(pay)
    assert pay.refunded_amount == Decimal("0")


def test_partial_refunds_track_remaining_balance(db, no_real_paypal: StubTransport) -> None:  # type: ignore[no-untyped-def]
    c = make_customer(db)
    order, pay = make_paid_order(db, c, "900.00")
    no_real_paypal.queue(token_response(), json_response(201, refund_body("RF-P1", "COMPLETED", "400.00")))
    first = request(db, order, "400.00")
    assert first.summary["action_state"] == "SUCCEEDED"
    db.refresh(pay)
    assert pay.refunded_amount == Decimal("400.00") and pay.refundable_amount == Decimal("500.00")
    # a second refund on the same capture is no longer auto-eligible (prior refund) and cannot exceed the balance
    second = request(db, order, "600.00")
    assert second.summary["decision"] == "REJECTED"
    refunds = db.scalars(select(Refund).where(Refund.order_id == order.id)).all()
    assert sum(r.amount for r in refunds if r.status == RefundStatus.COMPLETED) == Decimal("400.00")


def test_state_machine_rejects_illegal_transitions(db) -> None:  # type: ignore[no-untyped-def]
    from app.models import ExecutionAction
    from app.workflows.execution_engine import transition

    a = ExecutionAction(business_id=northwind(db).id, action_type="INITIATE_REFUND", state=ActionState.SUCCEEDED, idempotency_key=f"sm:{uuid.uuid4()}", requested_by="test", payload={}, history=[])
    with pytest.raises(Exception):
        transition(a, ActionState.EXECUTING, actor="test")
