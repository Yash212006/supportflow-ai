"""Agents: tool permissions, deterministic support flow, copilot, and the AG Studio LLM proxy guard."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agents.support_graph import rule_classify
from app.agents.tooling import AGENT_PERMISSIONS, ToolNotPermitted


def test_rule_classifier() -> None:
    c = rule_classify("I want a refund for order #1054, it arrived broken", {})
    assert c.intent == "REFUND_REQUEST" and c.order_number == 1054
    assert rule_classify("talk to a human please", {}).wants_human
    assert rule_classify("where is my order 1047?", {}).intent == "DELAYED_SHIPMENT"
    assert rule_classify("refund ₹500 please", {}).refund_amount == 500.0


def test_permission_matrix_keeps_money_tools_away_from_read_agents() -> None:
    assert "request_refund_action" in AGENT_PERMISSIONS["resolution"]
    for agent in ("orchestrator", "order_investigation", "policy_intelligence", "risk_assessment", "manager_copilot", "dashboard_agent"):
        assert "request_refund_action" not in AGENT_PERMISSIONS[agent], agent
    assert AGENT_PERMISSIONS["dashboard_agent"] == set() or not AGENT_PERMISSIONS["dashboard_agent"]


def test_tool_runner_denies_unpermitted_calls(db) -> None:  # type: ignore[no-untyped-def]
    from app.agents.tooling import ToolContext, ToolRunner, Tracer
    from app.models import AgentExecution, AgentToolCall
    from tests.conftest import northwind

    biz = northwind(db)
    ex = AgentExecution(business_id=biz.id, workflow="test", status="RUNNING", llm_mode="deterministic", steps=[])
    db.add(ex)
    db.commit()
    from app.agents.support_tools import SUPPORT_TOOLS

    ctx = ToolContext(db=db, business_id=biz.id, user_id=None, customer_id=None)
    runner = ToolRunner(ctx, Tracer(db, ex), SUPPORT_TOOLS)
    with pytest.raises(ToolNotPermitted):
        runner.call("order_investigation", "request_refund_action", order_number=1, amount=1)
    db.commit()
    denied = [t for t in db.query(AgentToolCall).filter(AgentToolCall.execution_id == ex.id) if not t.authorized]
    assert denied


def test_support_chat_refund_flow_is_policy_gated(client: TestClient, priya_h: dict[str, str]) -> None:
    orders = client.get("/api/customer/orders", headers=priya_h).json()
    target = next(o for o in orders if o["status"] == "DELIVERED" and 1000 <= float(o["total_amount"]) <= 5000)
    r = client.post("/api/customer/chat", headers=priya_h, json={"message": f"I want a refund for order #{target['order_number']}"})
    assert r.status_code == 200, r.text
    reply = r.json()["reply"]
    meta = reply["meta"]
    assert meta["intent"] == "REFUND_REQUEST"
    assert meta["llm_mode"] == "deterministic"
    actions = meta["actions"]
    assert actions and actions[0]["decision"] in ("REQUIRES_APPROVAL", "ESCALATED")
    assert actions[0]["action_state"] != "SUCCEEDED"
    assert "refunded" not in reply["content"].lower() or "not" in reply["content"].lower()


def test_chat_never_leaks_other_customers_orders(client: TestClient, priya_h: dict[str, str], manager_h: dict[str, str]) -> None:
    mine = {o["order_number"] for o in client.get("/api/customer/orders", headers=priya_h).json()}
    body = client.get("/api/orders?limit=200", headers=manager_h).json()
    items = body if isinstance(body, list) else body["items"]
    other = next(o for o in items if o["order_number"] not in mine)
    r = client.post("/api/customer/chat", headers=priya_h, json={"message": f"refund order #{other['order_number']}"})
    reply = r.json()["reply"]
    assert "couldn't find" in reply["content"].lower()
    assert other["customer_name"] not in reply["content"]
    assert not reply["meta"]["actions"]


def test_copilot_answers_with_tool_cards(client: TestClient, manager_h: dict[str, str], priya_h: dict[str, str]) -> None:
    r = client.post("/api/agents/copilot/run", headers=manager_h, json={"message": "Show pending approvals"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"]
    assert any(c["tool"] == "list_pending_approvals" for c in body["cards"])
    assert client.post("/api/agents/copilot/run", headers=priya_h, json={"message": "hi"}).status_code == 403


def test_copilot_refund_proposal_is_dry_run(client: TestClient, manager_h: dict[str, str]) -> None:
    before = client.get("/api/refunds?limit=200", headers=manager_h).json()
    n_before = before["total"] if isinstance(before, dict) and "total" in before else len(before.get("items", before))
    client.post("/api/agents/copilot/run", headers=manager_h, json={"message": "Prepare a refund proposal for order #1054"})
    after = client.get("/api/refunds?limit=200", headers=manager_h).json()
    n_after = after["total"] if isinstance(after, dict) and "total" in after else len(after.get("items", after))
    assert n_after == n_before


def test_studio_ai_proxy_rejects_financial_tools(client: TestClient, manager_h: dict[str, str]) -> None:
    body = {"input": [{"type": "message", "role": "user", "content": [{"type": "text", "text": "hi"}]}], "tools": [{"name": "refund_order", "description": "x", "parameters": {}}]}
    r = client.post("/api/studio-ai/turn", headers=manager_h, json=body)
    assert r.status_code in (422, 503)


def test_studio_ai_proxy_requires_llm_and_staff(client: TestClient, manager_h: dict[str, str], priya_h: dict[str, str]) -> None:
    body = {"input": [{"type": "message", "role": "user", "content": [{"type": "text", "text": "build a chart"}]}], "tools": []}
    assert client.post("/api/studio-ai/turn", headers=priya_h, json=body).status_code == 403
    r = client.post("/api/studio-ai/turn", headers=manager_h, json=body)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "llm_not_configured"
    assert client.get("/api/studio-ai/config", headers=manager_h).json()["enabled"] is False


def test_chat_survives_a_broken_llm_provider(client: TestClient, priya_h: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    """A configured but failing provider (bad key, retired model, quota) must degrade to rule-based mode,
    including knowledge search, instead of failing the customer's turn."""
    from app.agents import llm
    from app.core.config import get_settings

    class Boom:
        def invoke(self, *_a, **_k):  # type: ignore[no-untyped-def]
            raise RuntimeError("404 model not found")

        def with_structured_output(self, *_a, **_k):  # type: ignore[no-untyped-def]
            return self

        def bind_tools(self, *_a, **_k):  # type: ignore[no-untyped-def]
            return self

    def broken_embed(_texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding model retired")

    s = get_settings()
    monkeypatch.setattr(s, "llm_provider", "gemini")
    monkeypatch.setattr(s, "gemini_api_key", "test-key")
    monkeypatch.setattr(llm, "_candidates", lambda: [("boom", Boom())])
    monkeypatch.setattr(llm, "embed_provider", broken_embed)
    import app.knowledge.service as kb

    monkeypatch.setattr(kb, "embed_provider", broken_embed)
    r = client.post("/api/customer/chat", headers=priya_h, json={"message": "What is your refund policy for damaged items?"})
    assert r.status_code == 200, r.text
    reply = r.json()["reply"]
    assert not reply["meta"].get("error"), reply["content"]
    assert "something went wrong" not in reply["content"]
    assert reply["meta"]["llm_mode"] == "rules (LLM failed)"  # never claims the LLM answered when it did not


def test_rule_mode_understands_follow_ups(client: TestClient, priya_h: dict[str, str]) -> None:
    orders = client.get("/api/customer/orders", headers=priya_h).json()
    items = orders["items"] if isinstance(orders, dict) else orders
    num = items[0]["order_number"]
    r1 = client.post("/api/customer/chat", headers=priya_h, json={"message": "delivery update please"}).json()
    conv = r1["conversation_id"]
    r2 = client.post("/api/customer/chat", headers=priya_h, json={"message": f"#{num}", "conversation_id": conv}).json()
    assert f"#{num}" in r2["reply"]["content"]
    assert "What do you need help with" not in r2["reply"]["content"]
    r3 = client.post("/api/customer/chat", headers=priya_h, json={"message": f"delivery of {num}"}).json()
    assert f"#{num}" in r3["reply"]["content"] and "Which order" not in r3["reply"]["content"]


def test_working_llm_drives_classification_and_reply(client: TestClient, priya_h: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from app.agents import llm
    from app.agents.support_graph import Classification
    from app.core.config import get_settings

    orders = client.get("/api/customer/orders", headers=priya_h).json()
    num = (orders["items"] if isinstance(orders, dict) else orders)[0]["order_number"]
    seen: dict[str, str] = {}

    class Structured:
        def invoke(self, msgs):  # type: ignore[no-untyped-def]
            seen["classify_prompt"] = msgs[-1][1]
            return Classification(intent="ORDER_INQUIRY", confidence=0.9, order_number=num, summary="status check")

    class Fake:
        def with_structured_output(self, _schema):  # type: ignore[no-untyped-def]
            return Structured()

        def invoke(self, msgs):  # type: ignore[no-untyped-def]
            seen["reply_prompt"] = msgs[-1][1]
            return SimpleNamespace(content=f"Good news! Order #{num} is on its way.")

    s = get_settings()
    monkeypatch.setattr(s, "llm_provider", "gemini")
    monkeypatch.setattr(s, "gemini_api_key", "test-key")
    monkeypatch.setattr(llm, "_candidates", lambda: [("fake", Fake())])
    first = client.post("/api/customer/chat", headers=priya_h, json={"message": "hi there"}).json()
    r = client.post("/api/customer/chat", headers=priya_h, json={"message": "and that one?", "conversation_id": first["conversation_id"]}).json()["reply"]
    assert r["content"] == f"Good news! Order #{num} is on its way."
    assert r["meta"]["llm_mode"].startswith("gemini:")
    assert "hi there" in seen["classify_prompt"] and "hi there" in seen["reply_prompt"]  # conversation memory reaches the model


def test_llm_falls_back_to_second_model_and_sticks(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from app.agents import llm
    from app.core.config import get_settings

    calls: list[str] = []

    class M:
        def __init__(self, name: str, ok: bool) -> None:
            self.name, self.ok = name, ok

        def invoke(self, _msgs):  # type: ignore[no-untyped-def]
            calls.append(self.name)
            if not self.ok:
                raise RuntimeError("504 DEADLINE_EXCEEDED")
            return SimpleNamespace(content="hello")

    s = get_settings()
    monkeypatch.setattr(s, "llm_provider", "gemini")
    monkeypatch.setattr(s, "gemini_api_key", "test-key")
    models = [("primary", M("primary", False)), ("fallback", M("fallback", True))]
    monkeypatch.setattr(llm, "_candidates", lambda: models)
    monkeypatch.setitem(llm._preferred, "index", 0)
    assert llm.complete("sys", "hi") == "hello"
    assert llm.complete("sys", "again") == "hello"
    assert calls == ["primary", "fallback", "fallback"]  # the failing model is not retried on every call
