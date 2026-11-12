# Policy engine

`app/policies/engine.py` is pure Python: no I/O, no LLM. Given an action type, a fact dictionary and a policy
version, it returns an outcome and a full trace. The AI can request actions but cannot change a decision: the
execution engine calls the policy engine itself and refuses to execute anything the decision does not allow.

## Evaluation

1. If a **required fact** is missing (`refund_amount`, `payment_status`, `order_status` for refunds;
   `order_status` for cancellations), the outcome is `NEEDS_MORE_INFORMATION` before any rule runs.
2. Rules are evaluated by ascending `priority`. A rule matches when **all** (`match: all`) or **any**
   (`match: any`) of its conditions pass. A condition on a missing fact never passes.
3. The first matching rule decides. If none match, the version's `default_outcome` applies.
4. The decision is stored in `policy_decisions` with the inputs, policy id and version, matched rule, and every
   condition's expected value, actual value and result. Approvals and the execution detail page show this trace.

## Outcomes

| Outcome | Effect |
| --- | --- |
| `AUTO_EXECUTE` | Execution engine revalidates and calls PayPal |
| `REQUIRES_APPROVAL` | Approval request for a manager; nothing is sent to PayPal until approved |
| `ESCALATED` | Approval request marked high risk; ticket escalated |
| `REJECTED` | Action rejected with the rule's explanation |
| `NEEDS_MORE_INFORMATION` | The agent asks the customer for what is missing |

## Operators

`eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `in`, `not_in`, `is_true`, `is_false`, `between` (inclusive, value is
`[low, high]`). Numbers are compared as `Decimal`.

## Facts

| Fact | Meaning |
| --- | --- |
| `refund_amount` | Requested refund amount (business currency) |
| `order_total` | Order total |
| `refund_ratio` | Refund amount / order total |
| `refundable_amount` | Captured amount minus refunds already issued or reserved |
| `exceeds_refundable` | Requested amount is greater than the refundable amount |
| `payment_status` | Internal payment status |
| `payment_captured` | Payment has been captured |
| `payment_source` | `PAYPAL_SANDBOX` or `SEED_SAMPLE` |
| `order_status` | Internal order status |
| `prior_refund_on_payment` | A refund was already issued on this payment |
| `customer_refunds_90d` | Refunds for this customer in the last 90 days |
| `customer_refund_requests_7d` | Refund requests by this customer in the last 7 days |
| `days_since_order`, `days_since_delivery` | Age of the order / delivery |
| `within_refund_window` | Inside the product's refund window |
| `risk_level`, `risk_score` | From the deterministic risk scorer |
| `conflicting_state` | Order, payment and refund records disagree |
| `shipment_status` | Latest shipment status |

Facts are built from the database by `app/policies/facts.py`, never from model output.

### Risk scorer

Weighted signals: `REPEATED_REQUESTS` (critical), `MULTIPLE_REQUESTS`, `FREQUENT_REFUNDS`,
`MULTIPLE_REFUNDS_SAME_CAPTURE`, `EXCEEDS_REFUNDABLE` (critical), `REPEATED_FAILED_PAYMENTS`,
`AMOUNT_ABOVE_ORDER` (critical), `INCONSISTENT_STATE` (critical), `HIGH_VALUE`. Level is HIGH if any critical
signal fires or score ≥ 50, MEDIUM at ≥ 20, otherwise LOW.

## Default refund policy (seeded, version 2)

INR thresholds shown; with `DEMO_CURRENCY=USD` they are $50 and $250.

| Priority | Rule | Conditions | Outcome |
| --- | --- | --- | --- |
| 1 | Refund exceeds refundable amount | `exceeds_refundable` is true | REJECTED |
| 2 | Payment not captured | `payment_captured` is false | REJECTED |
| 10 | Policy C: escalate | any of: amount > 5,000; ≥ 3 refunds in 90 days; ≥ 3 requests in 7 days; risk HIGH; conflicting state | ESCALATED |
| 20 | Policy B: manager approval | amount between 1,000 and 5,000 | REQUIRES_APPROVAL |
| 25 | Outside refund window | `within_refund_window` is false | REQUIRES_APPROVAL |
| 30 | Policy A: automatic refund | amount < 1,000, captured, no prior refund on the payment, within window, risk not HIGH | AUTO_EXECUTE |
| — | default | | REQUIRES_APPROVAL |

Version 1 (all refunds need approval) is kept for history. The cancellation policy rejects shipped orders and
auto-cancels unpaid ones.

## Versioning

Editing rules in **Policies** (managers) or `PUT /api/policies/{id}` creates a new immutable version; older
decisions keep pointing at the version they used. Before executing an approved or automatic refund, the execution
engine compares the decision's version with the active one; an automatic action under an outdated version is
failed with `POLICY_CHANGED` and must be re-evaluated. Rules are validated on save (known facts, known operators,
correct value shapes).

## Dry run

`POST /api/policies/evaluate` and the **Dry run** panel evaluate an order and amount against the active version
and return the trace without recording a decision or executing anything. The copilot's `prepare_refund_proposal`
uses the same call.
