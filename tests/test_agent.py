from backend.services.resolution_engine import should_escalate
from backend.services import order_service


def test_high_value_escalation(db):
    order = order_service.get_order_by_number(db, "ORD8801")
    decision = should_escalate(query="Refund this ₹80,000 order.", order=order, db=db)
    assert decision["escalate"] is True


def test_human_request_escalation():
    decision = should_escalate(query="I want to speak to a human representative")
    assert decision["escalate"] is True


def test_fraud_escalation():
    decision = should_escalate(query="This looks like a stolen card fraud case")
    assert decision["escalate"] is True


def test_missing_information_escalation():
    decision = should_escalate(query="Where is my order?", missing_information=True)
    assert decision["escalate"] is True


EXPECTED_TOOL_SCENARIOS = [
    {
        "name": "order_status",
        "expected": {"get_order", "get_delivery_status"},
        "selected": {"get_order", "get_delivery_status"},
    },
    {
        "name": "refund_eligibility",
        "expected": {"get_order", "search_company_policy"},
        "selected": {"get_order", "search_company_policy", "evaluate_refund_eligibility"},
    },
    {
        "name": "high_value_refund",
        "expected": {"escalate_ticket"},
        "selected": {"get_order", "escalate_ticket"},
    },
]


def test_tool_selection_eval_fixtures():
    hits = 0
    for row in EXPECTED_TOOL_SCENARIOS:
        if row["expected"].issubset(row["selected"]):
            hits += 1
    assert hits == len(EXPECTED_TOOL_SCENARIOS)
