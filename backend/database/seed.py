"""Generate fictional seed data and a demo support user."""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config.settings import settings
from backend.database.connection import SessionLocal, init_db
from backend.models.customer import Customer
from backend.models.order import Order
from backend.models.refund import Refund
from backend.models.ticket import Ticket
from backend.models.user import SupportUser

FIRST = [
    "Rahul", "Priya", "Amit", "Neha", "Vikram", "Ananya", "Karan", "Meera",
    "Arjun", "Isha", "Rohan", "Sana", "Dev", "Pooja", "Nikhil", "Kavya",
    "Harsh", "Diya", "Aditya", "Tara", "Siddharth", "Naina", "Yash", "Ritika",
    "Manish",
]
LAST = [
    "Sharma", "Patel", "Reddy", "Iyer", "Khan", "Nair", "Gupta", "Das",
    "Mehta", "Joshi", "Singh", "Kapoor", "Verma", "Rao", "Malhotra",
]
CITIES = [
    "Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Pune", "Chennai", "Kolkata", "Jaipur",
]
PRODUCTS = [
    "Aurora Wireless Headphones",
    "Nimbus Smartwatch",
    "Lumen Desk Lamp",
    "Harbor Backpack",
    "PixelFrame 27 Monitor",
    "Cascade Water Bottle",
    "Northwind Jacket",
    "Orbit Bluetooth Speaker",
    "Cedar Office Chair",
    "Summit Running Shoes",
]
CATEGORIES = [
    "DELIVERY", "REFUND", "CANCELLATION", "REPLACEMENT", "WARRANTY",
    "PAYMENT", "ACCOUNT", "GENERAL", "PRODUCT",
]
PRIORITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
TICKET_STATUSES = [
    "OPEN", "IN_PROGRESS", "WAITING_FOR_CUSTOMER", "ESCALATED", "RESOLVED", "CLOSED",
]
ORDER_STATUSES = [
    "PLACED", "PROCESSING", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED", "DELAYED", "CANCELLED",
]


def _seed_user(db: Session) -> None:
    existing = db.scalar(select(SupportUser).where(SupportUser.email == settings.demo_user_email))
    if existing:
        return
    db.add(
        SupportUser(
            email=settings.demo_user_email,
            display_name="Support Executive",
            password_hash=settings.demo_user_password,
            role="executive",
        )
    )


def seed_database(db: Session | None = None) -> dict:
    close = False
    if db is None:
        init_db()
        db = SessionLocal()
        close = True
    try:
        if db.scalar(select(Customer).limit(1)):
            return {"seeded": False, "message": "Database already contains customers."}

        rng = random.Random(42)
        today = date.today()
        customers: list[Customer] = []

        demo = Customer(
            customer_code="CUST001",
            name="Rahul Sharma",
            email="rahul@example.com",
            phone="+919800000001",
            status="active",
        )
        customers.append(demo)

        used_emails = {demo.email}
        for i in range(2, 51):
            fn, ln = rng.choice(FIRST), rng.choice(LAST)
            email = f"{fn.lower()}.{ln.lower()}{i}@example.com"
            while email in used_emails:
                email = f"{fn.lower()}.{ln.lower()}{i}.{rng.randint(10,99)}@example.com"
            used_emails.add(email)
            customers.append(
                Customer(
                    customer_code=f"CUST{i:03d}",
                    name=f"{fn} {ln}",
                    email=email,
                    phone=f"+9198{i:08d}",
                    status="active" if rng.random() > 0.06 else "inactive",
                )
            )
        db.add_all(customers)
        db.flush()

        orders: list[Order] = []

        def add_order(
            number: str,
            customer: Customer,
            status: str,
            amount: float,
            delay: int | None,
            payment: str = "PAID",
            product: str | None = None,
        ) -> Order:
            actual = None
            if status == "DELIVERED":
                order_date = today - timedelta(days=rng.randint(6, 45))
                expected = order_date + timedelta(days=rng.randint(3, 5))
                actual = expected + timedelta(days=delay or 0)
            elif status == "DELAYED":
                delay_val = delay if (delay and delay > 0) else rng.randint(3, 10)
                expected = today - timedelta(days=delay_val)
                order_date = expected - timedelta(days=rng.randint(4, 7))
                actual = None
            elif status == "CANCELLED":
                order_date = today - timedelta(days=rng.randint(3, 30))
                expected = order_date + timedelta(days=5)
                actual = None
            elif status == "OUT_FOR_DELIVERY":
                order_date = today - timedelta(days=rng.randint(2, 4))
                expected = today
                actual = None
            elif status == "SHIPPED":
                order_date = today - timedelta(days=rng.randint(2, 4))
                expected = today + timedelta(days=rng.randint(1, 3))
                actual = None
            elif status == "PROCESSING":
                order_date = today - timedelta(days=rng.randint(1, 2))
                expected = today + timedelta(days=rng.randint(2, 4))
                actual = None
            elif status == "PLACED":
                order_date = today - timedelta(days=rng.choice([0, 1]))
                expected = today + timedelta(days=rng.randint(3, 5))
                actual = None
            else:
                order_date = today - timedelta(days=5)
                expected = today + timedelta(days=2)
                actual = None

            o = Order(
                order_number=number,
                customer_id=customer.id,
                order_date=order_date,
                expected_delivery=expected,
                actual_delivery=actual,
                status=status,
                amount=amount,
                payment_status=payment,
                shipping_address=f"{rng.randint(10, 99)} MG Road, {rng.choice(CITIES)}",
                product_name=product or rng.choice(PRODUCTS),
            )
            orders.append(o)
            return o

        add_order("ORD1001", demo, "DELAYED", 2499.0, 6, product="Aurora Wireless Headphones")
        add_order("ORD1002", demo, "DELIVERED", 1299.0, 0, product="Cascade Water Bottle")
        add_order("ORD1003", demo, "DELIVERED", 899.0, 1, product="Lumen Desk Lamp")
        add_order("ORD8801", customers[1], "DELAYED", 80000.0, 7, product="PixelFrame 27 Monitor")
        add_order("ORD5501", customers[2], "DELIVERED", 1999.0, 0)
        add_order("ORD5502", customers[2], "CANCELLED", 3499.0, None, payment="REFUNDED")

        n = 1004
        while len(orders) < 150:
            cust = rng.choice(customers)
            status = rng.choices(
                ORDER_STATUSES,
                weights=[8, 10, 15, 10, 35, 12, 10],
            )[0]
            amount = round(rng.choice([499, 799, 1299, 2499, 3999, 5999, 14999, 24999, 80000 if rng.random() < 0.04 else 1999]) + rng.random(), 2)
            delay = rng.choice([0, 0, 1, 2, 6, 7, 10]) if status in {"DELAYED", "DELIVERED"} else None
            add_order(f"ORD{n}", cust, status, amount, delay)
            n += 1

        db.add_all(orders)
        db.flush()
        by_number = {o.order_number: o for o in orders}

        tickets: list[Ticket] = []

        def add_ticket(
            number: str,
            customer: Customer,
            order: Order | None,
            subject: str,
            description: str,
            priority: str,
            status: str,
            category: str,
            resolution: str | None = None,
        ) -> Ticket:
            t = Ticket(
                ticket_number=number,
                customer_id=customer.id,
                order_id=order.id if order else None,
                subject=subject,
                description=description,
                priority=priority,
                status=status,
                category=category,
                assigned_to="SupportFlow AI",
                resolution=resolution,
            )
            tickets.append(t)
            return t

        # Seed only a few historical resolved tickets for analytics SLA baselines.
        # Active orders (like ORD1001 and ORD8801) start clean so agent/user actions generate tickets on demand.
        add_ticket(
            "TKT1001",
            demo,
            by_number["ORD1002"],
            "Damaged packaging",
            "Customer complained about packaging but item was usable.",
            "LOW",
            "RESOLVED",
            "DELIVERY",
            "No replacement required. Customer confirmed item works.",
        )
        add_ticket(
            "TKT1002",
            demo,
            by_number["ORD1003"],
            "Product inquiry",
            "Customer asked about setup instructions for desk lamp.",
            "LOW",
            "RESOLVED",
            "GENERAL",
            "Provided digital manual to customer.",
        )
        add_ticket(
            "TKT1024",
            demo,
            by_number["ORD1002"],
            "Packaging follow-up",
            "Follow-up on packaging condition.",
            "LOW",
            "RESOLVED",
            "DELIVERY",
            "Closed after customer confirmation.",
        )

        db.add_all(tickets)
        db.flush()

        refunds: list[Refund] = []
        rfd_n = 2001
        processed_orders = [o for o in orders if o.status in {"DELIVERED", "CANCELLED"}][:20]
        for o in processed_orders:
            if o.order_number in {"ORD1001", "ORD8801"}:
                continue
            cust = next(c for c in customers if c.id == o.customer_id)
            refunds.append(
                Refund(
                    refund_id=f"RFD{rfd_n}",
                    order_id=o.id,
                    customer_id=cust.id,
                    amount=o.amount,
                    reason="Processed historical refund from seed data.",
                    status=rng.choice(["PROCESSED", "PROCESSED", "REJECTED", "APPROVED"]),
                )
            )
            rfd_n += 1
        while len(refunds) < 30:
            o = rng.choice(orders)
            if o.order_number in {"ORD1001", "ORD8801"}:
                continue
            if any(r.order_id == o.id for r in refunds):
                continue
            cust = next(c for c in customers if c.id == o.customer_id)
            refunds.append(
                Refund(
                    refund_id=f"RFD{rfd_n}",
                    order_id=o.id,
                    customer_id=cust.id,
                    amount=min(o.amount, 1999),
                    reason="Partial goodwill refund.",
                    status=rng.choice(["PROCESSED", "REJECTED", "PENDING_APPROVAL"]),
                )
            )
            rfd_n += 1

        db.add_all(refunds)
        _seed_user(db)
        db.commit()

        from backend.services.approval_service import sync_tickets_and_approvals
        sync_tickets_and_approvals(db)

        _write_csv(customers, orders, tickets, refunds)
        return {
            "seeded": True,
            "customers": len(customers),
            "orders": len(orders),
            "tickets": len(tickets),
            "refunds": len(refunds),
        }
    finally:
        if close:
            db.close()


def _write_csv(
    customers: list[Customer],
    orders: list[Order],
    tickets: list[Ticket],
    refunds: list[Refund],
) -> None:
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "seed_data.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["entity", "code", "related", "status", "amount", "notes"])
        for c in customers:
            w.writerow(["customer", c.customer_code, c.email, c.status, "", c.name])
        for o in orders:
            w.writerow(["order", o.order_number, o.customer_id, o.status, o.amount, o.product_name])
        for t in tickets:
            w.writerow(["ticket", t.ticket_number, t.customer_id, t.status, "", t.subject])
        for r in refunds:
            w.writerow(["refund", r.refund_id, r.order_id, r.status, r.amount, r.reason])


if __name__ == "__main__":
    print(seed_database())
