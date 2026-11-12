"""Seed a fictional online retailer ("Northwind Living") with users for every role, policies,
knowledge documents and clearly-labelled SAMPLE history for analytics.

Sample payments use source=SEED_SAMPLE and never reach PayPal; the execution engine refuses to
refund them. Live PayPal Sandbox payments are created by checking out in the customer portal.

Usage:  python -m app.seed [--reset]
"""

from __future__ import annotations

import random
import sys
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine, utcnow
from app.core.security import hash_password
from app.knowledge.service import ingest_document
from app.models import (
    AgentExecution,
    ApprovalRequest,
    Business,
    BusinessPolicy,
    Customer,
    ExecutionAction,
    Order,
    OrderItem,
    Payment,
    PolicyDecision,
    PolicyVersion,
    Product,
    Refund,
    Shipment,
    SupportTicket,
    TicketEvent,
    User,
)
from app.models.enums import (
    ActionState,
    ActionType,
    ApprovalStatus,
    DecisionOutcome,
    ExecutionStatus,
    IssueCategory,
    OrderStatus,
    PaymentSource,
    PaymentStatus,
    RefundStatus,
    RiskLevel,
    Role,
    ShipmentStatus,
    TicketPriority,
    TicketStatus,
)

DEMO_PASSWORD_STAFF = "Demo@12345"
DEMO_PASSWORD_CUSTOMER = "Customer@123"


def refund_rules(currency: str) -> list[dict[str, object]]:
    small, large = (1000, 5000) if currency == "INR" else (50, 250)
    return [
        {"id": "R0-over-refundable", "name": "Refund exceeds refundable amount", "priority": 1, "match": "any",
         "conditions": [{"field": "exceeds_refundable", "op": "is_true"}], "outcome": "REJECTED",
         "explanation": "The requested amount is more than what remains refundable on the captured payment."},
        {"id": "R1-not-captured", "name": "Payment not captured", "priority": 2, "match": "all",
         "conditions": [{"field": "payment_captured", "op": "is_false"}], "outcome": "REJECTED",
         "explanation": "Only captured payments can be refunded."},
        {"id": "C-escalate", "name": "Policy C — escalate for manual review", "priority": 10, "match": "any",
         "conditions": [
             {"field": "refund_amount", "op": "gt", "value": large},
             {"field": "customer_refunds_90d", "op": "gte", "value": 3},
             {"field": "customer_refund_requests_7d", "op": "gte", "value": 3},
             {"field": "risk_level", "op": "eq", "value": "HIGH"},
             {"field": "conflicting_state", "op": "is_true"},
         ], "outcome": "ESCALATED",
         "explanation": "High value, repeated refunds, high risk or conflicting records require manual review."},
        {"id": "B-approval", "name": "Policy B — manager approval", "priority": 20, "match": "all",
         "conditions": [{"field": "refund_amount", "op": "between", "value": [small, large]}], "outcome": "REQUIRES_APPROVAL",
         "explanation": f"Refunds between {small} and {large} need a manager's approval."},
        {"id": "W-window", "name": "Outside refund window", "priority": 25, "match": "all",
         "conditions": [{"field": "within_refund_window", "op": "is_false"}], "outcome": "REQUIRES_APPROVAL",
         "explanation": "The order is outside the product refund window; a manager may grant an exception."},
        {"id": "A-auto", "name": "Policy A — automatic refund", "priority": 30, "match": "all",
         "conditions": [
             {"field": "refund_amount", "op": "lt", "value": small},
             {"field": "payment_captured", "op": "is_true"},
             {"field": "prior_refund_on_payment", "op": "is_false"},
             {"field": "within_refund_window", "op": "is_true"},
             {"field": "risk_level", "op": "ne", "value": "HIGH"},
         ], "outcome": "AUTO_EXECUTE",
         "explanation": f"Small refund (< {small}) on a captured payment with no prior refund and no high-risk flag."},
    ]


PRODUCTS = [
    ("NW-LAMP-01", "Arc Floor Lamp", "Lighting", 4499, 30),
    ("NW-BULB-04", "Smart LED Bulb (4-pack)", "Lighting", 899, 30),
    ("NW-MUG-02", "Stoneware Mug Set", "Kitchen", 749, 30),
    ("NW-KNF-07", "Chef Knife 8\"", "Kitchen", 2199, 15),
    ("NW-BLN-03", "Pro Blender 1200W", "Appliances", 6999, 15),
    ("NW-KTL-05", "Electric Kettle", "Appliances", 1599, 30),
    ("NW-SHT-08", "Cotton Bedsheet Set", "Bedding", 1899, 30),
    ("NW-PIL-09", "Memory Foam Pillow", "Bedding", 1299, 30),
    ("NW-SPK-10", "Bluetooth Speaker", "Electronics", 3499, 15),
    ("NW-EBD-11", "Wireless Earbuds", "Electronics", 2799, 7),
    ("NW-PLT-12", "Ceramic Planter", "Decor", 599, 30),
    ("NW-CLK-13", "Wall Clock", "Decor", 999, 30),
]

CUSTOMERS = [
    ("Priya Sharma", "priya@customer.demo", "Mumbai", "loyal"),
    ("Arjun Mehta", "arjun@customer.demo", "Bengaluru", "standard"),
    ("Meera Iyer", "meera@customer.demo", "Chennai", "standard"),
    ("Rohan Gupta", "rohan@example.com", "Delhi", "standard"),
    ("Ananya Rao", "ananya@example.com", "Hyderabad", "loyal"),
    ("Vikram Singh", "vikram@example.com", "Jaipur", "standard"),
    ("Kavya Nair", "kavya@example.com", "Kochi", "new"),
    ("Aditya Joshi", "aditya@example.com", "Pune", "standard"),
    ("Sneha Kulkarni", "sneha@example.com", "Pune", "loyal"),
    ("Rahul Verma", "rahul@example.com", "Lucknow", "standard"),
    ("Ishita Bose", "ishita@example.com", "Kolkata", "new"),
    ("Karan Malhotra", "karan@example.com", "Chandigarh", "standard"),
    ("Neha Kapoor", "neha@example.com", "Delhi", "standard"),
    ("Siddharth Jain", "siddharth@example.com", "Indore", "new"),
]

def _knowledge(currency: str) -> list[tuple]:
    sym, small, large = ("₹", "1,000", "5,000") if currency == "INR" else ("$", "50", "250")
    return [
    ("Refund Policy", "refund_policy", "refund-policy", """# Northwind Living Refund Policy (v1 — superseded)

Refunds are accepted within 14 days of delivery for all products. All refunds require manager review.
""", True),
    ("Refund Policy", "refund_policy", "refund-policy", f"""# Northwind Living Refund Policy

Effective 1 October 2026. This version replaces all earlier refund policies.

## Eligibility
- Most products can be refunded within 30 days of delivery. Kitchen knives, blenders and audio products have a 15-day window; earbuds have a 7-day window for hygiene reasons.
- Refunds are issued to the original PayPal payment. We never refund to a different account.
- Only orders whose payment has been captured can be refunded.

## How refunds are decided
- Small refunds (under {sym}{small}) on a captured payment with no previous refund are processed automatically.
- Refunds between {sym}{small} and {sym}{large} are reviewed and approved by a support manager, usually within one business day.
- Refunds above {sym}{large}, repeated refund requests, or orders with inconsistent records are escalated for manual review.

## Partial refunds
Partial refunds are available for missing items or minor damage. The total refunded can never exceed the amount paid.

## Timing
Once PayPal accepts a refund it typically appears in the buyer's PayPal account within minutes; card-funded refunds can take 3–5 business days.
""", False),
    ("Shipping & Delivery", "shipping", "shipping", """# Shipping & Delivery

- Standard delivery: 3–6 business days in metro cities, 5–9 days elsewhere.
- Every order ships with a tracking number from BlueDart, Delhivery or DTDC.
- If your shipment is marked DELAYED, the carrier has reported an exception (weather, address issue, or hub backlog). Most delays resolve within 48 hours.
- If an order hasn't arrived 5 days after the estimated delivery date you may request a full refund or a free replacement.
- Orders can be cancelled free of charge before they are shipped. Once shipped, use the return and refund process instead.
""", False),
    ("Payments FAQ", "payments", "payments-faq", """# Payments FAQ

## Which payment methods do you accept?
We accept PayPal, including cards funded through PayPal.

## My payment failed. Was I charged?
No. If PayPal declines a payment, no money is captured. Common reasons: insufficient balance, card expired, or PayPal risk checks. You can retry checkout from the order page.

## I see a pending charge
A PayPal order that has been approved but not yet captured may show as a pending authorisation. If the order is not captured it is released automatically.

## Duplicate charges
Each order can be captured only once. If you see two charges, contact support with both PayPal transaction IDs and we will investigate.
""", False),
    ("Customer Service Procedures", "procedures", "cs-procedures", """# Customer Service Procedures

1. Verify the customer owns the order before sharing any details.
2. Classify the issue: order inquiry, payment failure, refund request, delayed shipment, cancellation, product issue, account issue or general support.
3. Product issues (damaged, defective, wrong item) are escalated to a specialist who arranges a replacement or return pickup.
4. Account and login issues are always handled by a human support agent for security.
5. Never promise a refund outcome before the refund policy engine has decided.
""", False),
    ("Product Care Guide", "product", "product-care", """# Product Care

- Stoneware mugs are dishwasher and microwave safe.
- The Pro Blender 1200W has a 2-year warranty; the jar is dishwasher safe, the base is not.
- Smart LED bulbs pair with the Northwind app over Wi-Fi 2.4 GHz.
- Memory foam pillows should be spot-cleaned only; the cover is machine washable.
""", False),
]


def reset_db() -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


def seed() -> None:
    s = get_settings()
    currency = s.demo_currency.upper()
    scale = Decimal("1") if currency == "INR" else Decimal("0.05")
    rnd = random.Random(42)
    db = SessionLocal()
    existing = db.scalars(select(Business).where(Business.slug == "northwind")).first()
    if existing:
        if existing.currency != currency:
            print(f"Seed data already present in {existing.currency}, but DEMO_CURRENCY={currency}. Nothing changed.")
            print("Re-seed with: python -m app.seed --reset   (Docker: docker compose run --rm seed python -m app.seed --reset)")
            sys.exit(1)
        print("Seed data already present (use --reset to rebuild).")
        return
    now = utcnow()
    biz = Business(name="Northwind Living", slug="northwind", currency=currency, settings={"brand_color": "#2563eb"})
    db.add(biz)
    db.flush()

    staff = {
        "admin": User(business_id=biz.id, email="admin@supportflow.demo", full_name="Asha Admin", password_hash=hash_password(DEMO_PASSWORD_STAFF), role=Role.ADMIN),
        "manager": User(business_id=biz.id, email="manager@supportflow.demo", full_name="Maya Manager", password_hash=hash_password(DEMO_PASSWORD_STAFF), role=Role.SUPPORT_MANAGER),
        "agent": User(business_id=biz.id, email="agent@supportflow.demo", full_name="Sam Support", password_hash=hash_password(DEMO_PASSWORD_STAFF), role=Role.SUPPORT_AGENT),
    }
    db.add_all(staff.values())
    # second tenant to demonstrate isolation
    other = Business(name="Contoso Outfitters", slug="contoso", currency=currency)
    db.add(other)
    db.flush()
    db.add(User(business_id=other.id, email="manager@contoso.demo", full_name="Omar Other", password_hash=hash_password(DEMO_PASSWORD_STAFF), role=Role.SUPPORT_MANAGER))

    products = []
    for sku, name, cat, price, days in PRODUCTS:
        p = Product(business_id=biz.id, sku=sku, name=name, category=cat, price=(Decimal(price) * scale).quantize(Decimal("0.01")), refundable_days=days, description=f"{name} by Northwind Living")
        products.append(p)
    db.add_all(products)

    customers = []
    for i, (name, email, city, seg) in enumerate(CUSTOMERS):
        user = None
        if email.endswith("@customer.demo"):
            user = User(business_id=biz.id, email=email, full_name=name, password_hash=hash_password(DEMO_PASSWORD_CUSTOMER), role=Role.CUSTOMER)
            db.add(user)
            db.flush()
        c = Customer(business_id=biz.id, user_id=user.id if user else None, email=email, full_name=name, city=city, segment=seg, phone=f"+91 98{rnd.randint(10000000, 99999999)}")
        customers.append(c)
    db.add_all(customers)
    db.flush()

    # ------------------------------------------------------------------ policies
    refund_policy = BusinessPolicy(business_id=biz.id, key="refund_policy", name="Refund Policy", action_type=ActionType.INITIATE_REFUND, description="Governs which refunds the AI may execute automatically, which need approval, and which are escalated.", current_version=2)
    db.add(refund_policy)
    db.flush()
    v1_rules = [r for r in refund_rules(currency) if r["id"] != "A-auto"]
    db.add(PolicyVersion(policy_id=refund_policy.id, version=1, rules=v1_rules, default_outcome=DecisionOutcome.REQUIRES_APPROVAL, effective_from=now - timedelta(days=75), effective_to=now - timedelta(days=40), change_note="Initial policy: all refunds need approval", created_by_user_id=staff["manager"].id))
    v2 = PolicyVersion(policy_id=refund_policy.id, version=2, rules=refund_rules(currency), default_outcome=DecisionOutcome.REQUIRES_APPROVAL, effective_from=now - timedelta(days=40), change_note="Enable automatic small refunds (Policy A)", created_by_user_id=staff["manager"].id)
    db.add(v2)
    cancel_policy = BusinessPolicy(business_id=biz.id, key="cancellation_policy", name="Cancellation Policy", action_type=ActionType.CANCEL_ORDER, description="Unpaid orders may be cancelled automatically; shipped orders cannot be cancelled.", current_version=1)
    db.add(cancel_policy)
    db.flush()
    db.add(PolicyVersion(policy_id=cancel_policy.id, version=1, rules=[
        {"id": "X-shipped", "name": "Already shipped", "priority": 1, "match": "any", "conditions": [{"field": "order_status", "op": "in", "value": ["SHIPPED", "DELIVERED"]}], "outcome": "REJECTED", "explanation": "Shipped orders cannot be cancelled; use a return instead."},
        {"id": "X-unpaid", "name": "Unpaid order", "priority": 5, "match": "all", "conditions": [{"field": "order_status", "op": "eq", "value": "PENDING_PAYMENT"}], "outcome": "AUTO_EXECUTE", "explanation": "Unpaid orders can be cancelled immediately."},
    ], default_outcome=DecisionOutcome.REQUIRES_APPROVAL, effective_from=now - timedelta(days=75), change_note="Initial", created_by_user_id=staff["manager"].id))
    db.flush()

    # ------------------------------------------------------------------ sample order history
    order_no = 1000
    carriers = ["BlueDart", "Delhivery", "DTDC"]
    ticket_no = 5000
    subjects = {
        IssueCategory.DELAYED_SHIPMENT: ["Order hasn't arrived yet", "Delivery is late", "Where is my package?"],
        IssueCategory.REFUND_REQUEST: ["Requesting a refund", "Item not as described, want money back", "Refund for damaged mug"],
        IssueCategory.PRODUCT_ISSUE: ["Blender stopped working", "Received wrong colour", "Lamp arrived damaged"],
        IssueCategory.PAYMENT_FAILURE: ["Payment failed at checkout", "Charged but order shows unpaid", "PayPal declined my payment"],
        IssueCategory.ORDER_INQUIRY: ["Order status?", "Can I change my address?", "Invoice request"],
        IssueCategory.CANCELLATION: ["Please cancel my order", "Ordered by mistake"],
        IssueCategory.ACCOUNT_ISSUE: ["Can't log in", "Change my email"],
        IssueCategory.GENERAL_SUPPORT: ["Do you ship to Goa?", "Gift wrapping available?"],
    }
    for day in range(60, 0, -1):
        for _ in range(rnd.choice([1, 1, 2, 2, 3])):
            cust = rnd.choice(customers)
            placed = now - timedelta(days=day, hours=rnd.randint(0, 20))
            lines = rnd.sample(products, rnd.choice([1, 1, 2, 3]))
            qtys = [rnd.choice([1, 1, 1, 2]) for _ in lines]
            total = sum((p.price * q for p, q in zip(lines, qtys)), Decimal("0"))
            order_no += 1
            failed = rnd.random() < 0.08
            delivered = not failed and day > 6 and rnd.random() < 0.9
            status = OrderStatus.CANCELLED if failed else (OrderStatus.DELIVERED if delivered else (OrderStatus.SHIPPED if day > 2 else OrderStatus.PROCESSING))
            o = Order(business_id=biz.id, customer_id=cust.id, order_number=order_no, status=status, currency=currency, total_amount=total, is_sample=True, placed_at=placed, delivered_at=placed + timedelta(days=rnd.randint(3, 6)) if delivered else None, created_at=placed)
            db.add(o)
            db.flush()
            for p, q in zip(lines, qtys):
                db.add(OrderItem(order_id=o.id, product_id=p.id, quantity=q, unit_price=p.price))
            pay = Payment(business_id=biz.id, order_id=o.id, customer_id=cust.id, attempt=1, source=PaymentSource.SEED_SAMPLE, method="paypal", status=PaymentStatus.FAILED if failed else PaymentStatus.CAPTURED, amount=total, currency=currency, failure_reason="INSTRUMENT_DECLINED (sample)" if failed else None, captured_at=None if failed else placed + timedelta(minutes=2), created_at=placed)
            db.add(pay)
            db.flush()
            if not failed:
                sstatus = ShipmentStatus.DELIVERED if delivered else (ShipmentStatus.DELAYED if rnd.random() < 0.3 else ShipmentStatus.IN_TRANSIT)
                db.add(Shipment(order_id=o.id, carrier=rnd.choice(carriers), tracking_number=f"NW{order_no}{rnd.randint(100, 999)}", status=sstatus, estimated_delivery=placed + timedelta(days=5), delivered_at=o.delivered_at, last_event={"DELIVERED": "Delivered to customer", "DELAYED": "Shipment held at hub — weather exception", "IN_TRANSIT": "In transit to destination city"}[sstatus.value], created_at=placed + timedelta(hours=8)))
            # tickets
            if rnd.random() < 0.35:
                cat = rnd.choice(list(subjects.keys()) + [IssueCategory.DELAYED_SHIPMENT, IssueCategory.REFUND_REQUEST])
                ticket_no += 1
                created = placed + timedelta(days=rnd.randint(1, 4))
                if created > now:
                    created = now - timedelta(hours=2)
                resolved = rnd.random() < 0.75 and day > 3
                by_ai = resolved and rnd.random() < (0.45 if day > 40 else 0.62)
                t = SupportTicket(business_id=biz.id, ticket_number=ticket_no, customer_id=cust.id, order_id=o.id, subject=rnd.choice(subjects[cat]), description="(sample ticket)", status=TicketStatus.RESOLVED if resolved else rnd.choice([TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.ESCALATED]), priority=rnd.choice(list(TicketPriority)), category=cat, ai_classification_confidence=round(rnd.uniform(0.6, 0.98), 2), resolved_by=("AI" if by_ai else "HUMAN") if resolved else None, resolved_at=created + timedelta(hours=rnd.uniform(0.05, 2) if by_ai else rnd.uniform(2, 40)) if resolved else None, satisfaction_score=rnd.choice([3, 4, 4, 5, 5]) if resolved and rnd.random() < 0.6 else None, assigned_to_user_id=staff["agent"].id if not by_ai else None, is_sample=True, created_at=created)
                if t.status == TicketStatus.ESCALATED:
                    t.escalated_at = created + timedelta(minutes=5)
                db.add(t)
                db.flush()
                db.add(TicketEvent(ticket_id=t.id, actor="system", event="created", detail="sample", created_at=created))
                ex = AgentExecution(business_id=biz.id, workflow="support", status=ExecutionStatus.FAILED if rnd.random() < 0.04 else ExecutionStatus.COMPLETED, ticket_id=t.id, order_id=o.id, intent=cat.value, llm_mode="sample", input_summary=t.subject, resolved_autonomously=by_ai, required_human=not by_ai, duration_ms=rnd.randint(900, 6500), is_sample=True, created_at=created, finished_at=created + timedelta(seconds=4), steps=[{"agent": a, "step": "sample", "summary": "sample execution"} for a in ("orchestrator", "order_investigation", "policy_intelligence", "resolution")])
                db.add(ex)
                # sample refunds tied to refund tickets
                if cat == IssueCategory.REFUND_REQUEST and not failed:
                    ratio = rnd.choice([Decimal("1"), Decimal("0.5"), Decimal("0.3")])
                    amt = (total * ratio).quantize(Decimal("0.01"))
                    small, large = (Decimal(1000), Decimal(5000)) if currency == "INR" else (Decimal(50), Decimal(250))
                    outcome = DecisionOutcome.AUTO_EXECUTE if (amt < small and day <= 40) else (DecisionOutcome.ESCALATED if amt > large else DecisionOutcome.REQUIRES_APPROVAL)
                    rstatus = RefundStatus.COMPLETED if outcome == DecisionOutcome.AUTO_EXECUTE or rnd.random() < 0.7 else rnd.choice([RefundStatus.REJECTED, RefundStatus.AWAITING_APPROVAL])
                    if day < 5 and outcome != DecisionOutcome.AUTO_EXECUTE:
                        rstatus = RefundStatus.AWAITING_APPROVAL
                    dec = PolicyDecision(business_id=biz.id, policy_id=refund_policy.id, policy_version=2 if day <= 40 else 1, action_type=ActionType.INITIATE_REFUND, outcome=outcome, matched_rule_id={"AUTO_EXECUTE": "A-auto", "REQUIRES_APPROVAL": "B-approval", "ESCALATED": "C-escalate"}[outcome.value], inputs={"refund_amount": str(amt), "order_total": str(total), "sample": True}, evaluated_conditions=[], explanation=f"(sample) {outcome.value} for {currency} {amt}", customer_id=cust.id, order_id=o.id, payment_id=pay.id, risk_level=RiskLevel.HIGH if outcome == DecisionOutcome.ESCALATED else RiskLevel.LOW, is_sample=True, created_at=created)
                    db.add(dec)
                    db.flush()
                    ex.decision_outcome = outcome
                    act = ExecutionAction(business_id=biz.id, action_type=ActionType.INITIATE_REFUND, state={RefundStatus.COMPLETED: ActionState.SUCCEEDED, RefundStatus.REJECTED: ActionState.REJECTED, RefundStatus.AWAITING_APPROVAL: ActionState.REQUIRES_APPROVAL if outcome != DecisionOutcome.ESCALATED else ActionState.ESCALATED}[rstatus], idempotency_key=f"sample-{o.id}", payload={"sample": True, "amount": str(amt)}, requested_by="agent:resolution", policy_decision_id=dec.id, order_id=o.id, payment_id=pay.id, ticket_id=t.id, is_sample=True, created_at=created, history=[{"to": "REQUESTED", "note": "sample"}])
                    db.add(act)
                    db.flush()
                    r = Refund(business_id=biz.id, payment_id=pay.id, order_id=o.id, customer_id=cust.id, ticket_id=t.id, amount=amt, currency=currency, reason=t.subject, status=rstatus, is_sample=True, policy_decision_id=dec.id, execution_action_id=act.id, paypal_status="COMPLETED (sample)" if rstatus == RefundStatus.COMPLETED else None, created_at=created, completed_at=created + timedelta(minutes=3) if rstatus == RefundStatus.COMPLETED else None)
                    db.add(r)
                    if rstatus == RefundStatus.COMPLETED:
                        pay.refunded_amount = amt
                        pay.status = PaymentStatus.REFUNDED if amt >= total else PaymentStatus.PARTIALLY_REFUNDED
                        o.status = OrderStatus.REFUNDED if amt >= total else OrderStatus.PARTIALLY_REFUNDED
                    if rstatus == RefundStatus.AWAITING_APPROVAL:
                        db.add(ApprovalRequest(business_id=biz.id, execution_action_id=act.id, policy_decision_id=dec.id, status=ApprovalStatus.PENDING, title=f"(Sample) Approve refund of {currency} {amt} — order #{o.order_number}", reason=dec.explanation, proposed_by="agent:resolution", risk_level=dec.risk_level, risk_summary={"level": dec.risk_level.value if dec.risk_level else "LOW", "signals": [], "sample": True}, is_sample=True, created_at=created))
                    if rstatus == RefundStatus.REJECTED:
                        db.add(ApprovalRequest(business_id=biz.id, execution_action_id=act.id, policy_decision_id=dec.id, status=ApprovalStatus.REJECTED, title=f"(Sample) Refund {currency} {amt} — order #{o.order_number}", reason=dec.explanation, proposed_by="agent:resolution", decided_by_user_id=staff["manager"].id, decided_at=created + timedelta(hours=3), manager_note="Item used beyond return condition (sample)", is_sample=True, created_at=created))

    # Unpaid orders for the live PayPal Sandbox demo (Priya)
    priya = customers[0]
    for prods in ([products[2]], [products[1], products[10]], [products[5]], [products[0]]):
        order_no += 1
        total = sum((p.price for p in prods), Decimal("0"))
        o = Order(business_id=biz.id, customer_id=priya.id, order_number=order_no, status=OrderStatus.PENDING_PAYMENT, currency=currency, total_amount=total, is_sample=False, placed_at=now - timedelta(hours=1), notes="Created for the live PayPal Sandbox demo")
        db.add(o)
        db.flush()
        for p in prods:
            db.add(OrderItem(order_id=o.id, product_id=p.id, quantity=1, unit_price=p.price))
    db.commit()

    # ------------------------------------------------------------------ knowledge base
    for title, cat, key, body, _old in _knowledge(currency):
        ingest_document(db, business_id=biz.id, title=title, category=cat, filename=f"{key}.md", data=body.encode(), uploaded_by=staff["manager"].id, doc_key=key)
        db.commit()
    db.close()
    print(f"Seeded Northwind Living ({currency}). Last order #{order_no}.")
    print(f"  Staff:     admin@ / manager@ / agent@supportflow.demo  password {DEMO_PASSWORD_STAFF}")
    print(f"  Customers: priya@ / arjun@ / meera@customer.demo        password {DEMO_PASSWORD_CUSTOMER}")


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset_db()
    seed()
    _ = Base
