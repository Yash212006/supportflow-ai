"""Policies API, approvals API, knowledge base, analytics datasets, dashboards."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_policy_versioning_and_dry_run(client: TestClient, manager_h: dict[str, str]) -> None:
    pols = client.get("/api/policies", headers=manager_h).json()
    refund = next(p for p in pols["items"] if p["key"] == "refund_policy")
    assert [v["version"] for v in refund["versions"]] and refund["active_version"] == 2
    r = client.post("/api/policies/evaluate", headers=manager_h, json={"facts": {"refund_amount": 400, "payment_status": "CAPTURED", "order_status": "DELIVERED", "payment_captured": True, "prior_refund_on_payment": False, "within_refund_window": True, "risk_level": "LOW", "exceeds_refundable": False, "customer_refunds_90d": 0, "customer_refund_requests_7d": 0, "conflicting_state": False}})
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "AUTO_EXECUTE"
    bad = client.put(f"/api/policies/{refund['id']}", headers=manager_h, json={"rules": [{"id": "x", "priority": 1, "conditions": [{"field": "refund_amount", "op": "explode", "value": 1}], "outcome": "AUTO_EXECUTE"}]})
    assert bad.status_code == 422


def test_audit_log_records_financial_events(client: TestClient, manager_h: dict[str, str]) -> None:
    r = client.get("/api/audit-logs", headers=manager_h)
    assert r.status_code == 200
    body = r.json()
    rows = body if isinstance(body, list) else body["items"]
    assert rows
    text = str(rows)
    assert "test-client-secret" not in text and "password" not in text.lower()


def test_knowledge_upload_and_search(client: TestClient, manager_h: dict[str, str], agent_h: dict[str, str]) -> None:
    content = b"# Gift cards\n\nGift cards are non-refundable and expire after 12 months. Lost gift cards cannot be replaced."
    r = client.post("/api/knowledge/upload", headers=manager_h, files={"file": ("gift-cards.md", content, "text/markdown")}, data={"title": "Gift card policy", "category": "faq"})
    assert r.status_code == 200, r.text
    s = client.post("/api/knowledge/search", headers=agent_h, json={"query": "are gift cards refundable", "k": 3})
    assert s.status_code == 200
    hits = s.json()
    hits = hits["results"] if isinstance(hits, dict) else hits
    assert any("Gift" in h["title"] for h in hits)
    exe = client.post("/api/knowledge/upload", headers=manager_h, files={"file": ("x.exe", b"MZ", "application/octet-stream")}, data={"title": "bad", "category": "faq"})
    assert exe.status_code == 422
    assert client.post("/api/knowledge/upload", headers=agent_h, files={"file": ("a.md", b"hello world text", "text/markdown")}, data={"title": "a", "category": "faq"}).status_code == 403


def test_datasets_have_data_origin_labels(client: TestClient, manager_h: dict[str, str]) -> None:
    body = client.get("/api/analytics/datasets", headers=manager_h).json()
    sources = body["sources"] if isinstance(body, dict) and "sources" in body else body
    ids = {s["id"] for s in sources}
    assert {"orders", "payments", "refunds", "tickets"} <= ids
    payments = next(s for s in sources if s["id"] == "payments")
    assert payments["data"] and all("data_origin" in row for row in payments["data"])
    assert {row["data_origin"] for row in payments["data"]} <= {"sample", "live", "paypal_sandbox"}


def test_dashboard_save_and_restore(client: TestClient, manager_h: dict[str, str]) -> None:
    cfg = {"pages": [{"id": "p1", "title": "Mine"}]}
    r = client.post("/api/dashboards", headers=manager_h, json={"name": "Test", "state": cfg})
    assert r.status_code == 200, r.text
    lst = client.get("/api/dashboards", headers=manager_h).json()
    lst = lst if isinstance(lst, list) else lst["items"]
    d = next(x for x in lst if x.get("name") == "Test")
    full = client.get(f"/api/dashboards/{d['id']}", headers=manager_h).json()
    assert full["state"] == cfg


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.json()["database"] is True
