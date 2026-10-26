import json

from backend.services import customer_service, order_service, refund_service
from backend.services.approval_service import (
    approve_action,
    create_pending_action,
    get_pending_by_action_id,
    reject_action,
)
from tests.conftest import parse_tool


def test_get_customer_valid(tools):
    _, mapping = tools
    result = parse_tool(mapping["get_customer"].invoke({"customer_id": "CUST001"}))
    assert result["ok"] is True
    assert result["customer"]["name"] == "Rahul Sharma"


def test_get_customer_invalid(tools):
    _, mapping = tools
    result = parse_tool(mapping["get_customer"].invoke({"customer_id": "CUST9999"}))
    assert result["ok"] is False


def test_get_order_valid(tools):
    _, mapping = tools
    result = parse_tool(mapping["get_order"].invoke({"order_number": "ORD1001"}))
    assert result["ok"] is True
    assert result["order"]["status"] == "DELAYED"
    assert result["order"]["delay_days"] >= 5


def test_get_order_invalid(tools):
    _, mapping = tools
    result = parse_tool(mapping["get_order"].invoke({"order_number": "ORD0000"}))
    assert result["ok"] is False


def test_delivery_status(tools):
    _, mapping = tools
    result = parse_tool(mapping["get_delivery_status"].invoke({"order_number": "ORD1001"}))
    assert result["ok"] is True
    assert result["status"] == "DELAYED"


def test_eligible_refund_evaluation(db):
    from backend.models.refund import Refund

    order = order_service.get_order_by_number(db, "ORD1001")
    db.query(Refund).filter(Refund.order_id == order.id).delete()
    db.commit()
    evaluation = refund_service.evaluate_refund_eligibility(db, order)
    assert evaluation["eligible"] is True
    assert evaluation["high_value"] is False
    assert evaluation["requires_human_approval"] is True


def test_ineligible_refund_on_time_delivery(db):
    order = order_service.get_order_by_number(db, "ORD1002")
    evaluation = refund_service.evaluate_refund_eligibility(db, order)
    assert evaluation["eligible"] is False


def test_high_value_refund_blocked(tools, db):
    _, mapping = tools
    order = order_service.get_order_by_number(db, "ORD8801")
    evaluation = refund_service.evaluate_refund_eligibility(db, order)
    assert evaluation["high_value"] is True
    result = parse_tool(
        mapping["create_refund_request"].invoke(
            {"order_number": "ORD8801", "reason": "Customer wants ₹80,000 refund"}
        )
    )
    assert result["ok"] is False
    assert "threshold" in result["error"].lower() or "escalat" in result["error"].lower()


def test_duplicate_refund(tools, db):
    from backend.models.refund import Refund

    order = order_service.get_order_by_number(db, "ORD1001")
    db.query(Refund).filter(Refund.order_id == order.id).delete()
    db.commit()
    _, mapping = tools
    first = parse_tool(
        mapping["create_refund_request"].invoke(
            {"order_number": "ORD1001", "reason": "Delayed delivery", "ticket_number": "TKT1023"}
        )
    )
    assert first["ok"] is True
    second = parse_tool(
        mapping["create_refund_request"].invoke(
            {"order_number": "ORD1001", "reason": "Duplicate"}
        )
    )
    assert second["ok"] is False
    assert "duplicate" in second["error"].lower()


def test_approval_rejection_does_not_process(db):
    from backend.models.refund import Refund

    order = order_service.get_order_by_number(db, "ORD1003")
    db.query(Refund).filter(Refund.order_id == order.id).delete()
    db.commit()
    customer = customer_service.get_customer_by_id(db, order.customer_id)
    refund, err = refund_service.create_refund_request(
        db, order=order, customer=customer, reason="test"
    )
    assert err is None
    action = create_pending_action(
        db,
        action_type="REFUND",
        agent_reason="test",
        order_id=order.id,
        customer_id=customer.id,
        refund_id=refund.refund_id,
        amount=refund.amount,
    )
    result = reject_action(db, action, "reviewer", "not appropriate")
    assert result["status"] == "REJECTED"
    refreshed = refund_service.get_refund_by_id_str(db, refund.refund_id)
    assert refreshed.status == "REJECTED"


def test_approval_approve_processes_refund(db):
    from backend.models.order import Order
    from backend.models.refund import Refund

    order = db.query(Order).filter(Order.order_number == "ORD5501").one()
    db.query(Refund).filter(Refund.order_id == order.id).delete()
    order.status = "DELIVERED"
    order.payment_status = "PAID"
    db.commit()
    customer = customer_service.get_customer_by_id(db, order.customer_id)
    refund, err = refund_service.create_refund_request(
        db, order=order, customer=customer, reason="goodwill delay"
    )
    assert err is None
    action = create_pending_action(
        db,
        action_type="REFUND",
        agent_reason="eligible",
        order_id=order.id,
        customer_id=customer.id,
        refund_id=refund.refund_id,
        amount=refund.amount,
    )
    result = approve_action(db, action, "reviewer")
    assert result["ok"] is True
    refreshed = refund_service.get_refund_by_id_str(db, refund.refund_id)
    assert refreshed.status == "PROCESSED"
    db.refresh(order)
    assert order.status == "REFUNDED"
    assert order.payment_status == "REFUNDED"


def test_agent_tools_do_not_include_process_or_approve(tools):
    _, mapping = tools
    assert "approve_refund" not in mapping
    assert "process_refund" not in mapping
    assert "create_refund_request" in mapping


def test_refund_processed_updates_order_status_and_blocks_further_refunds(db, tools):
    import uuid
    from backend.models.order import Order
    from backend.models.refund import Refund
    from backend.models.ticket import Ticket

    order = db.query(Order).filter(Order.order_number == "ORD1001").one()
    # Clean previous refunds and open tickets for clean test
    db.query(Refund).filter(Refund.order_id == order.id).delete()
    order.status = "DELAYED"
    order.payment_status = "PAID"
    ticket_num = f"TKT-TEST-{uuid.uuid4().hex[:6]}"
    ticket = Ticket(
        ticket_number=ticket_num,
        customer_id=order.customer_id,
        order_id=order.id,
        subject="Delayed delivery refund",
        description="Delivery is delayed",
        status="OPEN",
    )
    db.add(ticket)
    db.commit()

    try:
        customer = customer_service.get_customer_by_id(db, order.customer_id)
        refund, err = refund_service.create_refund_request(
            db, order=order, customer=customer, reason="Late order", ticket=ticket
        )
        assert err is None

        action = create_pending_action(
            db,
            action_type="REFUND",
            agent_reason="Delayed past 5 days",
            order_id=order.id,
            ticket_id=ticket.id,
            customer_id=customer.id,
            refund_id=refund.refund_id,
            amount=refund.amount,
        )

        # Approve action
        res = approve_action(db, action, reviewed_by="manager_jane")
        assert res["ok"] is True

        # Order must now be REFUNDED with 0 delay days
        db.refresh(order)
        db.refresh(ticket)
        assert order.status == "REFUNDED"
        assert order.payment_status == "REFUNDED"
        assert ticket.status == "RESOLVED"
        assert order_service.delay_days(order) == 0

        order_dict = order_service.order_to_dict(order)
        assert order_dict["is_refunded"] is True
        assert order_dict["refund_status"] == "PROCESSED"
        assert order_dict["delay_days"] == 0

        # Eligibility evaluation must now reject any new refund
        eval_res = refund_service.evaluate_refund_eligibility(db, order)
        assert eval_res["eligible"] is False
        assert "Order has already been refunded." in eval_res["blockers"]

        # Delivery status tool should reflect REFUNDED status
        _, mapping = tools
        delivery_tool_res = parse_tool(
            mapping["get_delivery_status"].invoke({"order_number": "ORD1001"})
        )
        assert delivery_tool_res["ok"] is True
        assert delivery_tool_res["status"] == "REFUNDED"
        assert delivery_tool_res["is_refunded"] is True
        assert delivery_tool_res["delay_days"] == 0
    finally:
        # Reset state so other tests run against clean DELAYED order
        db.query(Refund).filter(Refund.order_id == order.id).delete()
        db.query(Ticket).filter(Ticket.ticket_number == ticket_num).delete()
        order.status = "DELAYED"
        order.payment_status = "PAID"
        db.commit()
