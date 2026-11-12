"""Deterministic policy rule evaluation. Pure functions, no I/O, no LLM.

A policy version holds an ordered rule list. Rules are evaluated by ascending `priority`; the first
rule whose conditions match decides the outcome. If none match, `default_outcome` applies.
If a condition references a fact that is missing (None), the rule cannot match; if a fact listed in
REQUIRED_FACTS for the action is missing, the outcome is NEEDS_MORE_INFORMATION before any rule runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.models.enums import ActionType, DecisionOutcome

OPERATORS = ("eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in", "is_true", "is_false", "between")

REQUIRED_FACTS: dict[ActionType, tuple[str, ...]] = {
    ActionType.INITIATE_REFUND: ("refund_amount", "payment_status", "order_status"),
    ActionType.CANCEL_ORDER: ("order_status",),
}

FACT_CATALOG: dict[str, str] = {
    "refund_amount": "Requested refund amount (business currency)",
    "order_total": "Order total amount",
    "refund_ratio": "Refund amount / order total (0-1)",
    "refundable_amount": "Captured amount minus refunds already issued",
    "exceeds_refundable": "Requested amount is greater than refundable amount",
    "payment_status": "Internal payment status (CAPTURED, PARTIALLY_REFUNDED, …)",
    "payment_captured": "Payment has been captured (true/false)",
    "payment_source": "PAYPAL_SANDBOX or SEED_SAMPLE",
    "order_status": "Internal order status",
    "prior_refund_on_payment": "A refund was already issued on this payment",
    "customer_refunds_90d": "Number of refunds for this customer in the last 90 days",
    "customer_refund_requests_7d": "Refund requests by this customer in the last 7 days",
    "days_since_order": "Days since the order was placed",
    "days_since_delivery": "Days since delivery (null if not delivered)",
    "within_refund_window": "Order is inside the product refund window",
    "risk_level": "Deterministic risk level LOW/MEDIUM/HIGH",
    "risk_score": "Deterministic risk score 0-100",
    "conflicting_state": "Order/payment/refund records disagree",
    "shipment_status": "Latest shipment status",
}


@dataclass
class ConditionResult:
    field: str
    op: str
    expected: Any
    actual: Any
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "op": self.op, "expected": _plain(self.expected), "actual": _plain(self.actual), "passed": self.passed}


@dataclass
class RuleResult:
    rule_id: str
    name: str
    outcome: str
    matched: bool
    conditions: list[ConditionResult] = field(default_factory=list)


@dataclass
class Evaluation:
    outcome: DecisionOutcome
    matched_rule_id: str | None
    matched_rule_name: str | None
    explanation: str
    rules: list[RuleResult]
    missing_facts: list[str] = field(default_factory=list)

    def evaluated_conditions(self) -> list[dict[str, Any]]:
        return [
            {
                "rule_id": r.rule_id,
                "rule_name": r.name,
                "rule_outcome": r.outcome,
                "matched": r.matched,
                "conditions": [c.to_dict() for c in r.conditions],
            }
            for r in self.rules
        ]


def _plain(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v


def _num(v: Any) -> Decimal | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def check(op: str, actual: Any, expected: Any) -> bool:
    if op not in OPERATORS:
        raise ValueError(f"unknown operator {op}")
    if op == "is_true":
        return actual is True
    if op == "is_false":
        return actual is False
    if actual is None:
        return False
    if op in ("eq", "ne"):
        a, e = _num(actual), _num(expected)
        same = (a == e) if (a is not None and e is not None) else (str(actual) == str(expected))
        return same if op == "eq" else not same
    if op in ("in", "not_in"):
        values = [str(x) for x in (expected or [])]
        inside = str(actual) in values
        return inside if op == "in" else not inside
    a = _num(actual)
    if a is None:
        return False
    if op == "between":
        lo, hi = _num(expected[0]), _num(expected[1])
        return lo is not None and hi is not None and lo <= a <= hi
    e = _num(expected)
    if e is None:
        return False
    return {"lt": a < e, "lte": a <= e, "gt": a > e, "gte": a >= e}[op]


def validate_rules(rules: list[dict[str, Any]]) -> list[str]:
    """Return a list of validation problems (empty list = valid)."""
    problems: list[str] = []
    ids: set[str] = set()
    for i, r in enumerate(rules):
        rid = str(r.get("id") or "")
        if not rid:
            problems.append(f"rule #{i + 1}: missing id")
        elif rid in ids:
            problems.append(f"rule {rid}: duplicate id")
        ids.add(rid)
        if r.get("outcome") not in DecisionOutcome.__members__:
            problems.append(f"rule {rid}: invalid outcome {r.get('outcome')}")
        if r.get("match", "all") not in ("all", "any"):
            problems.append(f"rule {rid}: match must be 'all' or 'any'")
        conds = r.get("conditions") or []
        if not conds:
            problems.append(f"rule {rid}: needs at least one condition")
        for c in conds:
            if c.get("field") not in FACT_CATALOG:
                problems.append(f"rule {rid}: unknown fact '{c.get('field')}'")
            if c.get("op") not in OPERATORS:
                problems.append(f"rule {rid}: unknown operator '{c.get('op')}'")
            if c.get("op") == "between" and not (isinstance(c.get("value"), list) and len(c["value"]) == 2):
                problems.append(f"rule {rid}: 'between' needs [low, high]")
    return problems


def evaluate(action_type: ActionType, rules: list[dict[str, Any]], default_outcome: DecisionOutcome, facts: dict[str, Any]) -> Evaluation:
    missing = [f for f in REQUIRED_FACTS.get(action_type, ()) if facts.get(f) is None]
    if missing:
        return Evaluation(
            outcome=DecisionOutcome.NEEDS_MORE_INFORMATION,
            matched_rule_id=None,
            matched_rule_name=None,
            explanation=f"Cannot evaluate policy: missing required information ({', '.join(missing)}).",
            rules=[],
            missing_facts=missing,
        )
    results: list[RuleResult] = []
    ordered = sorted(rules, key=lambda r: (int(r.get("priority", 100)), str(r.get("id"))))
    for r in ordered:
        if r.get("enabled", True) is False:
            continue
        conds = [
            ConditionResult(c["field"], c["op"], c.get("value"), facts.get(c["field"]), check(c["op"], facts.get(c["field"]), c.get("value")))
            for c in r.get("conditions", [])
        ]
        matched = all(c.passed for c in conds) if r.get("match", "all") == "all" else any(c.passed for c in conds)
        rr = RuleResult(str(r["id"]), str(r.get("name", r["id"])), str(r["outcome"]), matched, conds)
        results.append(rr)
        if matched:
            reasons = [(f"{c.field} {c.op.replace('_', ' ')}" if c.op in ("is_true", "is_false") else f"{c.field} {c.op} {_plain(c.expected)}") + f" (actual: {_plain(c.actual)})" for c in conds if c.passed]
            explanation = r.get("explanation") or f"Rule '{rr.name}' matched."
            return Evaluation(
                outcome=DecisionOutcome(r["outcome"]),
                matched_rule_id=rr.rule_id,
                matched_rule_name=rr.name,
                explanation=f"{explanation} Matched because: {'; '.join(reasons)}.",
                rules=results,
            )
    return Evaluation(
        outcome=default_outcome,
        matched_rule_id=None,
        matched_rule_name=None,
        explanation=f"No rule matched; policy default outcome {default_outcome.value} applies.",
        rules=results,
    )
