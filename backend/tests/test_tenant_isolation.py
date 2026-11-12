from fastapi.testclient import TestClient


def _first(client: TestClient, path: str, h: dict[str, str]) -> dict:  # type: ignore[type-arg]
    body = client.get(path, headers=h).json()
    items = body if isinstance(body, list) else body["items"]
    return items[0]


def test_other_tenant_sees_no_northwind_data(client: TestClient, manager_h: dict[str, str], contoso_h: dict[str, str]) -> None:
    order = _first(client, "/api/orders", manager_h)
    assert client.get(f"/api/orders/{order['id']}", headers=contoso_h).status_code == 404
    body = client.get("/api/orders", headers=contoso_h).json()
    items = body if isinstance(body, list) else body["items"]
    assert items == []
    ov = client.get("/api/analytics/overview", headers=contoso_h).json()
    assert ov["total_payments"] == 0


def test_other_tenant_cannot_act_on_approvals(client: TestClient, manager_h: dict[str, str], contoso_h: dict[str, str]) -> None:
    appr = _first(client, "/api/approvals", manager_h)
    assert client.post(f"/api/approvals/{appr['id']}/approve", headers=contoso_h, json={"note": "x"}).status_code == 404


def test_customer_cannot_see_another_customers_order(client: TestClient, manager_h: dict[str, str], priya_h: dict[str, str]) -> None:
    mine = {o["id"] for o in client.get("/api/customer/orders", headers=priya_h).json()}
    body = client.get("/api/orders?limit=200", headers=manager_h).json()
    items = body if isinstance(body, list) else body["items"]
    other = next(o for o in items if o["id"] not in mine)
    assert client.get(f"/api/customer/orders/{other['id']}", headers=priya_h).status_code == 404
    r = client.post("/api/customer/refunds", headers=priya_h, json={"order_id": other["id"], "reason": "not mine"})
    assert r.status_code == 404


def test_datasets_are_tenant_scoped(client: TestClient, contoso_h: dict[str, str]) -> None:
    body = client.get("/api/analytics/datasets", headers=contoso_h).json()
    sources = body["sources"] if isinstance(body, dict) and "sources" in body else body
    for s in sources:
        assert s["data"] == [], s["id"]
