"""Test configuration.

Tests run against a dedicated Postgres database (supportflow_test) that is rebuilt with Alembic and
seeded once per session. PayPal is configured with dummy credentials, and every SDK request goes to a
stub transport (the APIMatic `custom_http_client` seam). No test ever reaches the real PayPal API.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

os.environ.update(
    ENVIRONMENT="test",
    DATABASE_URL=os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://supportflow:supportflow@localhost:5432/supportflow_test"),
    LLM_PROVIDER="none",
    OPENAI_API_KEY="",
    GEMINI_API_KEY="",
    PAYPAL_CLIENT_ID="test-client-id",
    PAYPAL_CLIENT_SECRET="test-client-secret",
    PAYPAL_WEBHOOK_ID="WH-TEST",
    PAYPAL_BASE_URL="https://api-m.sandbox.paypal.com",
    DEMO_CURRENCY="INR",
    JWT_SECRET="test-secret-not-for-production-0123456789",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from tests.paypal_stub import StubTransport  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    cwd = os.getcwd()
    os.chdir(BACKEND)
    from app.seed import reset_db, seed

    reset_db()
    seed()
    os.chdir(cwd)
    yield


@pytest.fixture(autouse=True)
def no_real_paypal() -> Iterator[StubTransport]:
    """Every test gets a stub transport with no queued responses: an unexpected PayPal call fails loudly."""
    from app.integrations.paypal.client import use_transport_for_tests

    t = StubTransport()
    use_transport_for_tests(t)
    yield t
    use_transport_for_tests(None)


@pytest.fixture()
def db():  # type: ignore[no-untyped-def]
    from app.core.database import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(scope="session")
def client() -> TestClient:
    from app.main import app

    return TestClient(app)


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def manager_h(client: TestClient) -> dict[str, str]:
    return login(client, "manager@supportflow.demo", "Demo@12345")


@pytest.fixture(scope="session")
def agent_h(client: TestClient) -> dict[str, str]:
    return login(client, "agent@supportflow.demo", "Demo@12345")


@pytest.fixture(scope="session")
def priya_h(client: TestClient) -> dict[str, str]:
    return login(client, "priya@customer.demo", "Customer@123")


@pytest.fixture(scope="session")
def contoso_h(client: TestClient) -> dict[str, str]:
    return login(client, "manager@contoso.demo", "Demo@12345")


def northwind(db):  # type: ignore[no-untyped-def]
    from sqlalchemy import select

    from app.models import Business

    return db.scalars(select(Business).where(Business.slug == "northwind")).one()


def make_customer(db, *, with_login: bool = False, password: str = "Customer@123"):  # type: ignore[no-untyped-def]
    """A fresh customer with no refund history (so risk signals don't leak between tests)."""
    from app.core.security import hash_password
    from app.models import Customer, User
    from app.models.enums import Role

    biz = northwind(db)
    tag = uuid.uuid4().hex[:8]
    email = f"t-{tag}@example.com"
    user = None
    if with_login:
        user = User(business_id=biz.id, email=email, full_name=f"Test {tag}", password_hash=hash_password(password), role=Role.CUSTOMER)
        db.add(user)
        db.flush()
    c = Customer(business_id=biz.id, user_id=user.id if user else None, email=email, full_name=f"Test {tag}")
    db.add(c)
    db.commit()
    return c


def make_paid_order(db, customer, amount: str, *, source: str = "PAYPAL_SANDBOX", days_ago: int = 3):  # type: ignore[no-untyped-def]
    """An order with a captured payment. PAYPAL_SANDBOX rows carry a fake capture id that only the stub transport knows."""
    from sqlalchemy import func, select

    from app.core.database import utcnow
    from app.models import Order, OrderItem, Payment, Product
    from app.models.enums import OrderStatus, PaymentSource, PaymentStatus

    biz = northwind(db)
    product = db.scalars(select(Product).where(Product.business_id == biz.id).order_by(Product.refundable_days.desc())).first()
    n = (db.scalar(select(func.max(Order.order_number)).where(Order.business_id == biz.id)) or 1000) + 1
    now = utcnow()
    o = Order(business_id=biz.id, customer_id=customer.id, order_number=n, status=OrderStatus.DELIVERED, currency="INR", total_amount=Decimal(amount), placed_at=now - timedelta(days=days_ago), delivered_at=now - timedelta(days=max(days_ago - 1, 0)))
    o.items.append(OrderItem(product_id=product.id, quantity=1, unit_price=Decimal(amount)))
    db.add(o)
    db.flush()
    cap = f"CAP{uuid.uuid4().hex[:14].upper()}"
    pay = Payment(business_id=biz.id, order_id=o.id, customer_id=customer.id, attempt=1, source=PaymentSource(source), status=PaymentStatus.CAPTURED, amount=Decimal(amount), currency="INR", paypal_order_id=f"ORD{uuid.uuid4().hex[:14].upper()}" if source == "PAYPAL_SANDBOX" else None, paypal_capture_id=cap if source == "PAYPAL_SANDBOX" else None, captured_at=now - timedelta(days=days_ago))
    db.add(pay)
    db.commit()
    return o, pay
