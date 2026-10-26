from sqlalchemy.orm import Session

from backend.models.order import Order
from backend.models.ticket import Ticket
from backend.rules.business_rules import get_business_rules
from backend.services.refund_service import evaluate_refund_eligibility


def should_escalate(
    *,
    query: str = "",
    order: Order | None = None,
    ticket: Ticket | None = None,
    db: Session | None = None,
    missing_information: bool = False,
    policy_ambiguous: bool = False,
    failed_attempts: int = 0,
) -> dict:
    rules = get_business_rules()
    reasons: list[str] = []
    q = query.lower()

    if ticket and ticket.priority == "CRITICAL":
        reasons.append("Ticket priority is CRITICAL.")
    if any(k in q for k in rules.escalate_on_fraud_keywords):
        reasons.append("Fraud-related language detected.")
    if any(k in q for k in rules.escalate_on_human_request_keywords):
        reasons.append("Customer requested a human representative.")
    if missing_information:
        reasons.append("Required business information is missing.")
    if policy_ambiguous:
        reasons.append("Policy guidance is ambiguous.")
    if failed_attempts >= rules.max_auto_resolution_attempts:
        reasons.append("Maximum automated resolution attempts exceeded.")
    if order and order.amount >= rules.high_value_threshold:
        reasons.append(
            f"High-value transaction ₹{order.amount:,.0f} exceeds "
            f"₹{rules.high_value_threshold:,.0f}."
        )
    if db is not None and order is not None:
        eval_result = evaluate_refund_eligibility(db, order)
        if eval_result.get("high_value"):
            if "High-value" not in " ".join(reasons):
                reasons.append("Refund request is above the high-value threshold.")

    return {
        "escalate": bool(reasons),
        "reasons": reasons,
        "message": (
            "This case exceeds automated handling rules. Escalating to a human support specialist."
            if reasons
            else "No escalation required by current business rules."
        ),
    }
