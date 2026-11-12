from app.models.enums import ActionType, DecisionOutcome
from app.policies.engine import evaluate, validate_rules
from app.seed import refund_rules

RULES = refund_rules("INR")


def facts(**over):  # type: ignore[no-untyped-def]
    base = {
        "refund_amount": 500.0, "order_total": 500.0, "refund_ratio": 1.0, "refundable_amount": 500.0,
        "exceeds_refundable": False, "payment_status": "CAPTURED", "payment_captured": True, "order_status": "DELIVERED",
        "prior_refund_on_payment": False, "within_refund_window": True, "risk_level": "LOW",
        "customer_refunds_90d": 0, "customer_refund_requests_7d": 0, "conflicting_state": False,
    }
    base.update(over)
    return base


def run(**over):  # type: ignore[no-untyped-def]
    return evaluate(ActionType.INITIATE_REFUND, RULES, DecisionOutcome.REQUIRES_APPROVAL, facts(**over))


def test_small_refund_is_auto_executed() -> None:
    ev = run(refund_amount=999.0)
    assert ev.outcome == DecisionOutcome.AUTO_EXECUTE
    assert ev.matched_rule_id == "A-auto"


def test_threshold_boundaries() -> None:
    assert run(refund_amount=1000.0).outcome == DecisionOutcome.REQUIRES_APPROVAL
    assert run(refund_amount=5000.0).outcome == DecisionOutcome.REQUIRES_APPROVAL
    assert run(refund_amount=5000.01).outcome == DecisionOutcome.ESCALATED


def test_exceeding_refundable_amount_is_rejected_first() -> None:
    ev = run(refund_amount=700.0, exceeds_refundable=True)
    assert ev.outcome == DecisionOutcome.REJECTED
    assert ev.matched_rule_id == "R0-over-refundable"


def test_uncaptured_payment_is_rejected() -> None:
    assert run(payment_captured=False, payment_status="CREATED").outcome == DecisionOutcome.REJECTED


def test_high_risk_or_repeat_refunds_escalate() -> None:
    assert run(risk_level="HIGH").outcome == DecisionOutcome.ESCALATED
    assert run(customer_refunds_90d=3).outcome == DecisionOutcome.ESCALATED


def test_prior_refund_blocks_auto_execution() -> None:
    assert run(prior_refund_on_payment=True).outcome == DecisionOutcome.REQUIRES_APPROVAL


def test_outside_window_needs_approval() -> None:
    ev = run(within_refund_window=False)
    assert ev.outcome == DecisionOutcome.REQUIRES_APPROVAL
    assert ev.matched_rule_id == "W-window"


def test_missing_required_facts_need_more_information() -> None:
    ev = evaluate(ActionType.INITIATE_REFUND, RULES, DecisionOutcome.REQUIRES_APPROVAL, {"refund_amount": 10})
    assert ev.outcome == DecisionOutcome.NEEDS_MORE_INFORMATION
    assert "payment_status" in ev.missing_facts


def test_explanation_lists_evaluated_conditions() -> None:
    ev = run(refund_amount=2000.0)
    assert "1000" in ev.explanation
    rows = ev.evaluated_conditions()
    assert any(r["matched"] for r in rows)


def test_thresholds_are_configurable() -> None:
    rules = [dict(r) for r in RULES]
    for r in rules:
        if r["id"] == "A-auto":
            r["conditions"] = [dict(c) for c in r["conditions"]]  # type: ignore[arg-type]
            r["conditions"][0]["value"] = 3000  # type: ignore[index]
        if r["id"] == "B-approval":
            r["conditions"] = [{"field": "refund_amount", "op": "between", "value": [3000, 5000]}]
    ev = evaluate(ActionType.INITIATE_REFUND, rules, DecisionOutcome.REQUIRES_APPROVAL, facts(refund_amount=2500.0))
    assert ev.outcome == DecisionOutcome.AUTO_EXECUTE


def test_validate_rules_catches_bad_rules() -> None:
    problems = validate_rules([{"id": "x", "priority": 1, "conditions": [{"field": "nope", "op": "explode", "value": 1}], "outcome": "MAYBE"}])
    assert problems
    assert validate_rules(RULES) == []
