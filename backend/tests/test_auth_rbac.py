from fastapi.testclient import TestClient

from tests.conftest import login


def test_login_and_me(client: TestClient, manager_h: dict[str, str]) -> None:
    r = client.get("/api/auth/me", headers=manager_h)
    assert r.status_code == 200
    body = r.json().get("user", r.json())
    assert body["role"] == "SUPPORT_MANAGER"
    assert "password_hash" not in str(body)


def test_bad_password_rejected(client: TestClient) -> None:
    r = client.post("/api/auth/login", json={"email": "manager@supportflow.demo", "password": "wrong"})
    assert r.status_code == 401


def test_missing_and_garbage_tokens(client: TestClient) -> None:
    assert client.get("/api/orders").status_code == 401
    assert client.get("/api/orders", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_refresh_token_cannot_be_used_as_access(client: TestClient) -> None:
    r = client.post("/api/auth/login", json={"email": "agent@supportflow.demo", "password": "Demo@12345"})
    refresh = r.json()["refresh_token"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh}"}).status_code == 401
    r2 = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 200 and r2.json()["access_token"]


def test_customer_cannot_reach_staff_apis(client: TestClient, priya_h: dict[str, str]) -> None:
    for path in ("/api/orders", "/api/approvals", "/api/policies", "/api/analytics/overview", "/api/audit-logs"):
        assert client.get(path, headers=priya_h).status_code == 403, path


def test_agent_cannot_approve_or_edit_policy(client: TestClient, agent_h: dict[str, str]) -> None:
    assert client.get("/api/orders", headers=agent_h).status_code == 200
    import uuid

    assert client.post(f"/api/approvals/{uuid.uuid4()}/approve", headers=agent_h, json={}).status_code == 403
    assert client.post("/api/policies", headers=agent_h, json={"key": "x_y", "name": "x", "action_type": "INITIATE_REFUND", "rules": []}).status_code == 403


def test_staff_cannot_use_customer_portal(client: TestClient, manager_h: dict[str, str]) -> None:
    assert client.get("/api/customer/orders", headers=manager_h).status_code == 403


def test_register_creates_customer_only(client: TestClient) -> None:
    import uuid

    email = f"new-{uuid.uuid4().hex[:6]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "Secret@1234", "full_name": "New Person", "role": "ADMIN"})
    assert r.status_code in (200, 201), r.text
    h = login(client, email, "Secret@1234")
    me = client.get("/api/auth/me", headers=h).json()
    assert me.get("user", me)["role"] == "CUSTOMER"
