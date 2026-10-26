def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_get_customer(client):
    r = client.get("/api/customers/CUST001")
    assert r.status_code == 200
    assert r.json()["customer"]["email"] == "rahul@example.com"


def test_get_order(client):
    r = client.get("/api/orders/ORD1001")
    assert r.status_code == 200
    assert r.json()["order"]["order_number"] == "ORD1001"


def test_tickets_list(client):
    r = client.get("/api/tickets", params={"status": "OPEN"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_invalid_order(client):
    r = client.get("/api/orders/ORD0000")
    assert r.status_code == 404


def test_login(client):
    r = client.post("/api/auth/login", json={"email": "exec@supportflow.local", "password": "demo123"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_refund_then_approve(client):
    created = client.post(
        "/api/refunds",
        json={"order_number": "ORD1002", "reason": "API test refund", "ticket_number": "TKT1024"},
    )
    if created.status_code == 409:
        return
    assert created.status_code == 200
    action_id = created.json()["pending_action"]
    approved = client.post(
        f"/api/approvals/{action_id}/approve",
        json={"reviewed_by": "pytest", "note": "ok"},
    )
    assert approved.status_code == 200
    assert approved.json()["ok"] is True


def test_high_value_refund_api(client):
    r = client.post(
        "/api/refunds",
        json={"order_number": "ORD8801", "reason": "High value"},
    )
    assert r.status_code == 400


def test_open_tickets_in_approvals_api(client):
    # Create an open ticket
    created = client.post(
        "/api/tickets",
        json={
            "customer_code": "CUST001",
            "subject": "Approvals test ticket",
            "description": "Testing approvals queue visibility",
            "priority": "HIGH",
            "category": "DELIVERY",
        },
    )
    assert created.status_code == 200
    t_num = created.json()["ticket_number"]

    # Verify approvals endpoint returns pending actions for open tickets
    resp = client.get("/api/approvals?status=PENDING_APPROVAL")
    assert resp.status_code == 200
    approvals = resp.json()
    assert len(approvals) > 0, "Open tickets should appear in approvals queue"

    match = next((a for a in approvals if a.get("ticket_number") == t_num), None)
    assert match is not None, f"Ticket {t_num} must appear in approvals"
    assert match.get("customer_name") is not None

    # Test approving an item from the queue
    action_id = match["action_id"]
    app_resp = client.post(
        f"/api/approvals/{action_id}/approve",
        json={"reviewed_by": "api_tester", "note": "Approved via test"},
    )
    assert app_resp.status_code == 200
    assert app_resp.json()["ok"] is True


