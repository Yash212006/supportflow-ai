"""Customer-support multi-agent workflow (LangGraph).

  orchestrator ──► order_investigation ──► policy_intelligence ──► risk_assessment ──► resolution ──► respond
        │                                       ▲                                        ▲
        └──────────────(general / account)──────┘                    (non-refund) ────────┘

Each node is a distinct agent with its own restricted toolset (app.agents.tooling.AGENT_PERMISSIONS)
and a structured output written into the shared state. Financial authority never sits with an agent:
the resolution agent can only *request* a refund from the execution engine, where the deterministic
policy engine decides.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.llm import complete, llm_mode, start_tracking, structured, tracked
from app.agents.support_tools import SUPPORT_TOOLS
from app.agents.tooling import ToolContext, ToolRunner, Tracer
from app.core.database import utcnow
from app.core.deps import Principal
from app.models import AgentExecution, Business, Conversation, Message
from app.models.enums import (
    DecisionOutcome,
    ExecutionStatus,
    IssueCategory,
    MessageRole,
)

log = logging.getLogger("supportflow.support")

Intent = Literal[
    "ORDER_INQUIRY", "PAYMENT_FAILURE", "REFUND_REQUEST", "DELAYED_SHIPMENT", "CANCELLATION", "PRODUCT_ISSUE", "ACCOUNT_ISSUE", "GENERAL_SUPPORT"
]


class Classification(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0, le=1)
    order_number: int | None = Field(default=None, description="Order number the customer refers to, if any")
    refund_amount: float | None = Field(default=None, description="Explicit partial refund amount, if the customer stated one")
    reason: str = Field(default="", description="Short reason in the customer's words")
    wants_human: bool = Field(default=False, description="Customer explicitly asks for a human")
    summary: str = Field(default="", description="One-line issue summary")


class SupportState(TypedDict, total=False):
    message: str
    history: list[dict[str, str]]
    context: dict[str, Any]
    classification: dict[str, Any]
    order: dict[str, Any] | None
    payments: list[dict[str, Any]]
    shipments: list[dict[str, Any]]
    investigation: dict[str, Any]
    knowledge: list[dict[str, Any]]
    policy_context: dict[str, Any]
    risk: dict[str, Any] | None
    resolution: dict[str, Any]
    ticket: dict[str, Any] | None
    reply: str
    citations: list[dict[str, Any]]
    actions: list[dict[str, Any]]


ORDER_RE = re.compile(r"(?:order\s*(?:no\.?|number|#)?\s*#?|#)\s*(\d{4,6})\b", re.I)
AMOUNT_RE = re.compile(r"(?:₹|rs\.?|inr|\$|usd)\s*([\d,]+(?:\.\d{1,2})?)|([\d,]+(?:\.\d{1,2})?)\s*(?:₹|rs\.?|rupees|inr|dollars|usd)", re.I)


def rule_classify(message: str, context: dict[str, Any]) -> Classification:
    m = message.lower()
    rules: list[tuple[str, Intent]] = [
        (r"refund|money back|reimburs|return (it|this|the)|send it back", "REFUND_REQUEST"),
        (r"\bcancel", "CANCELLATION"),
        (r"payment (failed|declined|error)|declined|charged twice|double charge|card (failed|declined)|couldn'?t pay|payment issue", "PAYMENT_FAILURE"),
        (r"late|delay|not (yet )?(arrived|delivered|received)|hasn'?t arrived|still waiting|where is my", "DELAYED_SHIPMENT"),
        (r"broken|damaged|defective|wrong item|not working|faulty|missing part", "PRODUCT_ISSUE"),
        (r"password|log ?in|sign ?in|account|email address", "ACCOUNT_ISSUE"),
        (r"track|status|order|shipping|deliver", "ORDER_INQUIRY"),
    ]
    intent: Intent = "GENERAL_SUPPORT"
    conf = 0.45
    for pat, it in rules:
        if re.search(pat, m):
            intent, conf = it, 0.75
            break
    if intent in ("GENERAL_SUPPORT", "ORDER_INQUIRY") and context.get("pending") == "order_number_for_refund":
        intent, conf = "REFUND_REQUEST", 0.7
    om = ORDER_RE.search(message) or (re.fullmatch(r"\s*#?(\d{4,6})\s*", message) and re.match(r"\s*#?(\d{4,6})", message))
    order_number = int(om.group(1)) if om else None
    if order_number is None:  # a bare number that is one of the customer's orders ("delivery of 1121")
        known = {int(n) for n in context.get("known_orders", [])}
        for n in re.findall(r"\b(\d{4,6})\b", message):
            if int(n) in known:
                order_number = int(n)
                break
    if intent == "GENERAL_SUPPORT" and context.get("pending") and context.get("pending_intent"):
        # follow-up answer to "which order?" keeps the earlier intent
        intent, conf = context["pending_intent"], 0.7
    elif intent == "GENERAL_SUPPORT" and order_number is not None:
        intent, conf = "ORDER_INQUIRY", 0.6
    amount = None
    am = AMOUNT_RE.search(message)
    if am:
        try:
            amount = float((am.group(1) or am.group(2)).replace(",", ""))
        except (InvalidOperation, ValueError):
            amount = None
    return Classification(
        intent=intent,
        confidence=conf,
        order_number=order_number,
        refund_amount=amount,
        reason=message.strip()[:300],
        wants_human=bool(re.search(r"\b(human|real person|agent|manager|someone)\b", m) and re.search(r"talk|speak|connect|want|need", m)),
        summary=message.strip()[:120],
    )


CLASSIFY_SYSTEM = (
    "You are the Customer Support Orchestrator for an online retailer. Classify the customer's latest message "
    "into exactly one intent. Extract an order number only if the customer states one (or it is clearly the order "
    "under discussion in the provided context). Extract refund_amount only if the customer asks for a specific "
    "partial amount. Never invent values."
)


class SupportWorkflow:
    def __init__(self, db: Session, principal: Principal, conversation: Conversation, execution: AgentExecution):
        self.db = db
        self.principal = principal
        self.conversation = conversation
        self.execution = execution
        self.tracer = Tracer(db, execution)
        ctx = ToolContext(db=db, business_id=principal.business_id, user_id=principal.user_id, customer_id=principal.customer_id)
        self.tools = ToolRunner(ctx, self.tracer, SUPPORT_TOOLS)
        self.business = db.get(Business, principal.business_id)
        self.graph = self._build()

    # ------------------------------------------------------------------ graph
    def _build(self) -> Any:
        g: StateGraph[SupportState] = StateGraph(SupportState)
        g.add_node("orchestrator", self.orchestrator)
        g.add_node("order_investigation", self.order_investigation)
        g.add_node("policy_intelligence", self.policy_intelligence)
        g.add_node("risk_assessment", self.risk_assessment)
        g.add_node("resolution", self.resolution)
        g.add_node("respond", self.respond)
        g.set_entry_point("orchestrator")
        g.add_conditional_edges("orchestrator", self.route_after_orchestrator, {"investigate": "order_investigation", "policy": "policy_intelligence", "resolve": "resolution"})
        g.add_conditional_edges("order_investigation", self.route_after_investigation, {"policy": "policy_intelligence", "resolve": "resolution"})
        g.add_conditional_edges("policy_intelligence", self.route_after_policy, {"risk": "risk_assessment", "resolve": "resolution"})
        g.add_edge("risk_assessment", "resolution")
        g.add_edge("resolution", "respond")
        g.add_edge("respond", END)
        return g.compile()

    # ------------------------------------------------------------------ agent 1: orchestrator
    def orchestrator(self, state: SupportState) -> SupportState:
        ctx = state.get("context", {})
        hist = "\n".join(f"{h['role']}: {h['content']}" for h in state.get("history", [])[-8:])
        orders = self.tools.call("orchestrator", "list_customer_orders", limit=50)
        user = f"Conversation so far:\n{hist}\n\nContext: last order discussed = {ctx.get('last_order_number')}; pending = {ctx.get('pending')}\nCustomer's orders: {[o['order_number'] for o in orders[:20]]}\n\nLatest message: {state['message']}"
        cls = structured(CLASSIFY_SYSTEM, user, Classification)
        source = "llm"
        if cls is None:
            cls = rule_classify(state["message"], {**ctx, "known_orders": [o["order_number"] for o in orders]})
            source = "rules"
        if cls.order_number is None and ctx.get("last_order_number") and cls.intent not in ("GENERAL_SUPPORT", "ACCOUNT_ISSUE"):
            cls.order_number = int(ctx["last_order_number"])
        if cls.order_number is None and len(orders) == 1 and cls.intent not in ("GENERAL_SUPPORT", "ACCOUNT_ISSUE"):
            cls.order_number = int(orders[0]["order_number"])
        known = {int(o["order_number"]) for o in orders}
        if cls.order_number is not None and cls.order_number not in known:
            cls_note = f"order #{cls.order_number} not found among this customer's orders"
            cls.order_number = None
        else:
            cls_note = ""
        data = cls.model_dump()
        data["classified_by"] = source
        data["recent_orders"] = orders
        data["note"] = cls_note
        self.execution.intent = cls.intent
        # Ticket: one per conversation; created/updated by the orchestrator
        if cls.intent != "GENERAL_SUPPORT" or cls.wants_human or ctx.get("ticket_id"):
            order_id = next((o["order_id"] for o in orders if int(o["order_number"]) == cls.order_number), None) if cls.order_number else None
            ticket = self.tools.call(
                "orchestrator",
                "create_or_update_ticket",
                subject=cls.summary or state["message"][:80],
                description=state["message"],
                category=cls.intent,
                order_id=order_id,
                ticket_id=ctx.get("ticket_id"),
                confidence=cls.confidence,
                priority="HIGH" if cls.wants_human or cls.intent == "PAYMENT_FAILURE" else "MEDIUM",
            )
            state["ticket"] = ticket
            self.execution.ticket_id = uuid.UUID(ticket["ticket_id"])
        self.tracer.step("orchestrator", "classify", f"Intent {cls.intent} ({cls.confidence:.0%}, via {source}); order #{cls.order_number or '—'}" + (f"; {cls_note}" if cls_note else ""), intent=cls.intent, order_number=cls.order_number, wants_human=cls.wants_human)
        state["classification"] = data
        return state

    def route_after_orchestrator(self, state: SupportState) -> str:
        c = state["classification"]
        if c["wants_human"]:
            return "resolve"
        if c["intent"] in ("GENERAL_SUPPORT", "ACCOUNT_ISSUE"):
            return "policy"
        if c.get("order_number") is None:
            return "resolve"  # resolution agent asks for the missing order
        return "investigate"

    # ------------------------------------------------------------------ agent 2: order investigation
    def order_investigation(self, state: SupportState) -> SupportState:
        c = state["classification"]
        order = self.tools.call("order_investigation", "get_order_details", order_number=c["order_number"])
        payments = self.tools.call("order_investigation", "get_payment_records", order_id=order["order_id"])
        shipments = self.tools.call("order_investigation", "get_shipment_records", order_id=order["order_id"])
        findings: list[str] = []
        latest_pay = payments[-1] if payments else None
        if latest_pay is None:
            findings.append("No payment recorded for this order.")
        else:
            findings.append(f"Payment {latest_pay['status']} ({latest_pay['currency']} {latest_pay['amount']}, refundable {latest_pay['refundable']}).")
            if latest_pay["status"] in ("FAILED", "DECLINED"):
                findings.append(f"Payment failure reason: {latest_pay.get('failure_reason') or 'declined by PayPal'}.")
            if latest_pay["source"] == "SEED_SAMPLE":
                findings.append("This order's payment is labelled sample data (not a PayPal Sandbox capture).")
        if shipments:
            s = shipments[-1]
            findings.append(f"Shipment via {s['carrier']} ({s['tracking_number']}) is {s['status']}; last event: {s.get('last_event') or 'n/a'}.")
            if s["status"] == "DELAYED":
                findings.append(f"Shipment delayed; estimated delivery {s.get('estimated_delivery') or 'unknown'}.")
        else:
            findings.append("No shipment created yet.")
        state["order"], state["payments"], state["shipments"] = order, payments, shipments
        state["investigation"] = {"findings": findings, "ownership_verified": True}
        self.execution.order_id = uuid.UUID(order["order_id"])
        self.tracer.step("order_investigation", "investigate", " ".join(findings), order_number=order["order_number"], order_status=order["status"])
        return state

    def route_after_investigation(self, state: SupportState) -> str:
        return "policy"

    # ------------------------------------------------------------------ agent 3: policy intelligence
    def policy_intelligence(self, state: SupportState) -> SupportState:
        c = state["classification"]
        category = {"REFUND_REQUEST": "refund_policy", "CANCELLATION": "refund_policy", "DELAYED_SHIPMENT": "shipping", "PRODUCT_ISSUE": None, "PAYMENT_FAILURE": "payments"}.get(c["intent"])
        try:
            hits = self.tools.call("policy_intelligence", "search_knowledge_base", query=f"{c['intent'].replace('_', ' ').lower()}: {state['message']}", category=category, k=4)
            if not hits and category:
                hits = self.tools.call("policy_intelligence", "search_knowledge_base", query=state["message"], k=3)
        except Exception as exc:  # knowledge is supporting context: answer without citations rather than fail the turn
            log.warning("knowledge search failed: %s", type(exc).__name__)
            hits = []
        policy = self.tools.call("policy_intelligence", "get_active_policy", action_type="INITIATE_REFUND") if c["intent"] in ("REFUND_REQUEST", "CANCELLATION") else None
        decision_inputs: dict[str, Any] = {}
        if c["intent"] in ("REFUND_REQUEST", "CANCELLATION") and state.get("order"):
            pays = state.get("payments") or []
            pay = pays[-1] if pays else None
            amt = c.get("refund_amount")
            decision_inputs = {"refund_amount": str(amt) if amt else (pay["refundable"] if pay else None), "reason": c.get("reason"), "order_id": state["order"]["order_id"]}  # type: ignore[index]
        state["knowledge"] = hits
        seen: set[str] = set()
        cites: list[dict[str, Any]] = []
        for h in hits:  # one citation per document (best-scoring chunk first)
            if str(h["document_id"]) in seen:
                continue
            seen.add(str(h["document_id"]))
            cites.append({"title": h["title"], "version": h["version"], "category": h["category"], "document_id": h["document_id"], "score": h["score"], "excerpt": h["content"][:240]})
        state["citations"] = cites
        state["policy_context"] = {"policy": policy, "decision_inputs": decision_inputs}
        applicable = f"Applicable policy: {policy['policy']} v{policy['version']}." if policy else "No financial policy needed."
        self.tracer.step("policy_intelligence", "retrieve", f"{len(hits)} knowledge passage(s) retrieved. {applicable} Structured inputs prepared for the deterministic engine.", sources=[f"{h['title']} v{h['version']}" for h in hits], inputs=decision_inputs)
        return state

    def route_after_policy(self, state: SupportState) -> str:
        return "risk" if state["classification"]["intent"] in ("REFUND_REQUEST", "CANCELLATION") and state.get("order") else "resolve"

    # ------------------------------------------------------------------ agent 5: risk assessment
    def risk_assessment(self, state: SupportState) -> SupportState:
        inputs = state["policy_context"]["decision_inputs"]
        risk = self.tools.call("risk_assessment", "assess_refund_risk", order_id=state["order"]["order_id"], amount=inputs.get("refund_amount"))  # type: ignore[index]
        state["risk"] = risk
        sigs = "; ".join(s["description"] for s in risk["signals"]) or "no risk indicators"
        self.tracer.step("risk_assessment", "assess", f"Deterministic risk {risk['level']} (score {risk['score']}): {sigs}. This assessment is an input to the policy engine, not a decision.", level=risk["level"], score=risk["score"])
        return state

    # ------------------------------------------------------------------ agent 4: resolution
    def resolution(self, state: SupportState) -> SupportState:
        c = state["classification"]
        ticket = state.get("ticket")
        res: dict[str, Any] = {"type": "info"}
        actions: list[dict[str, Any]] = []
        ctx = state.setdefault("context", {})
        ctx.pop("pending", None)
        ctx.pop("pending_intent", None)
        if c["wants_human"] and ticket:
            self.tools.call("resolution", "escalate_ticket", ticket_id=ticket["ticket_id"], reason="Customer asked for a human agent")
            res = {"type": "escalated", "reason": "customer_request"}
            self.execution.required_human = True
        elif c["intent"] in ("REFUND_REQUEST", "CANCELLATION") and not state.get("order"):
            res = {"type": "need_order", "recent_orders": c.get("recent_orders", [])[:20]}
            ctx["pending"] = "order_number_for_refund"
            ctx["pending_intent"] = c["intent"]
            self.execution.decision_outcome = DecisionOutcome.NEEDS_MORE_INFORMATION
        elif c["intent"] == "CANCELLATION" and state["order"]["status"] == "PENDING_PAYMENT":  # type: ignore[index]
            out = self.tools.call("resolution", "cancel_unpaid_order", order_id=state["order"]["order_id"], reason=c.get("reason", ""))  # type: ignore[index]
            res = {"type": "cancelled" if out["cancelled"] else "cancel_failed", **out}
            if out["cancelled"] and ticket:
                self.tools.call("resolution", "resolve_ticket", ticket_id=ticket["ticket_id"], summary=f"Unpaid order #{out['order_number']} cancelled")
                self.execution.resolved_autonomously = True
        elif c["intent"] in ("REFUND_REQUEST", "CANCELLATION"):
            order = state["order"]
            assert order is not None
            if c["intent"] == "CANCELLATION" and order["status"] in ("SHIPPED", "DELIVERED"):
                res = {"type": "cannot_cancel_shipped", "status": order["status"]}
            else:
                inputs = state["policy_context"]["decision_inputs"]
                key = f"agent-refund:{order['order_id']}:{inputs.get('refund_amount') or 'full'}:{ticket['ticket_id'] if ticket else self.execution.id}"
                out = self.tools.call(
                    "resolution",
                    "request_refund_action",
                    order_id=order["order_id"],
                    amount=str(c["refund_amount"]) if c.get("refund_amount") else None,
                    reason=c.get("reason") or state["message"][:300],
                    ticket_id=ticket["ticket_id"] if ticket else None,
                    execution_id=str(self.execution.id),
                    idempotency_key=key,
                )
                res = {"type": "refund", **out}
                actions.append({"kind": "refund", **out})
                if out.get("decision"):
                    self.execution.decision_outcome = DecisionOutcome(out["decision"])
                if out.get("action_state") in ("SUCCEEDED", "PENDING_CONFIRMATION") and out.get("decision") == "AUTO_EXECUTE":
                    self.execution.resolved_autonomously = True
                if out.get("decision") in ("REQUIRES_APPROVAL", "ESCALATED") or out.get("action_state") == "FAILED":
                    self.execution.required_human = True
        elif c["intent"] == "PAYMENT_FAILURE" and state.get("order"):
            pays = state.get("payments") or []
            pay = pays[-1] if pays else None
            res = {"type": "payment_explained", "payment_status": pay["status"] if pay else None, "failure_reason": pay.get("failure_reason") if pay else None}
            if ticket and pay and pay["status"] in ("CAPTURED",):
                self.tools.call("resolution", "resolve_ticket", ticket_id=ticket["ticket_id"], summary="Payment confirmed as captured")
                self.execution.resolved_autonomously = True
        elif state.get("order"):
            res = {"type": "order_update"}
            if ticket and c["intent"] in ("ORDER_INQUIRY", "DELAYED_SHIPMENT"):
                summary = " ".join(state.get("investigation", {}).get("findings", []))[:400]
                self.tools.call("resolution", "resolve_ticket", ticket_id=ticket["ticket_id"], summary=f"Order update provided: {summary}")
                self.execution.resolved_autonomously = True
            if c["intent"] == "PRODUCT_ISSUE" and ticket:
                self.tools.call("resolution", "escalate_ticket", ticket_id=ticket["ticket_id"], reason="Product issue needs a specialist (photos / replacement)")
                res = {"type": "product_issue_escalated"}
                self.execution.required_human = True
        elif c["intent"] not in ("GENERAL_SUPPORT", "ACCOUNT_ISSUE"):
            res = {"type": "need_order", "recent_orders": c.get("recent_orders", [])[:20]}
            ctx["pending"] = "order_number"
            ctx["pending_intent"] = c["intent"]
        else:
            res = {"type": "knowledge_answer"}
            if c["intent"] == "ACCOUNT_ISSUE" and ticket:
                self.tools.call("resolution", "escalate_ticket", ticket_id=ticket["ticket_id"], reason="Account issues are handled by a support agent")
                res = {"type": "account_escalated"}
                self.execution.required_human = True
        if state.get("order"):
            ctx["last_order_number"] = state["order"]["order_number"]  # type: ignore[index]
        ctx["last_intent"] = c["intent"]
        if ticket:
            ctx["ticket_id"] = ticket["ticket_id"]
        state["resolution"] = res
        state["actions"] = actions
        self.tracer.step("resolution", "resolve", _resolution_summary(res), result_type=res["type"])
        self.db.commit()
        return state

    # ------------------------------------------------------------------ reply
    def respond(self, state: SupportState) -> SupportState:
        facts = {
            "intent": state["classification"]["intent"],
            "order": state.get("order"),
            "investigation": state.get("investigation"),
            "resolution": state.get("resolution"),
            "knowledge": [{"title": h["title"], "version": h["version"], "text": h["content"][:700]} for h in state.get("knowledge", [])],
            "ticket": state.get("ticket"),
            "currency": self.business.currency if self.business else "USD",
        }
        system = (
            "You are SupportFlow, a concise, warm customer-support assistant for an online store. Write the reply to the customer "
            "using ONLY the facts provided in JSON. Never claim a refund, payment or cancellation happened unless resolution says so; "
            "state statuses exactly (e.g. PayPal PENDING means 'submitted, being processed'). If knowledge passages are used, refer to "
            "them by title in square brackets like [Refund Policy v2]. Answer the customer's actual question conversationally and in context of the recent conversation; if facts are missing, ask one short clarifying question. Keep it under 120 words. Do not reveal internal reasoning, rule ids or risk scores."
        )
        import json

        hist = "\n".join(f"{h['role']}: {h['content'][:400]}" for h in state.get("history", [])[-6:])
        text = complete(system, f"Recent conversation:\n{hist or '(none)'}\n\nCustomer's latest message: {state['message']}\n\nFACTS:\n{json.dumps(facts, default=str)}")
        if not text:
            text = template_reply(state, facts["currency"])
        state["reply"] = text
        return state


def _resolution_summary(res: dict[str, Any]) -> str:
    t = res["type"]
    if t == "refund":
        return f"Refund requested via execution engine → policy {res.get('decision')}, action {res.get('action_state')}, refund {res.get('refund_status')}" + (f", PayPal {res.get('paypal_status')} ({res.get('paypal_refund_id')})" if res.get("paypal_refund_id") else "") + (f"; error: {res['error']}" if res.get("error") else "")
    return {"need_order": "Asked customer which order they mean", "escalated": "Escalated to a human agent", "cancelled": "Unpaid order cancelled", "order_update": "Provided order status update", "knowledge_answer": "Answered from knowledge base"}.get(t, t)


def _money(cur: str, v: Any) -> str:
    sym = "₹" if cur == "INR" else "$" if cur == "USD" else f"{cur} "
    try:
        return f"{sym}{Decimal(str(v)):,.2f}"
    except Exception:
        return f"{sym}{v}"


def template_reply(state: SupportState, cur: str) -> str:
    res = state.get("resolution", {})
    t = res.get("type")
    order = state.get("order")
    cites = state.get("citations") or []
    cite = ""  # sources are shown as citation chips beside the reply
    if t == "need_order":
        recent = res.get("recent_orders") or []
        intent = (state.get("classification") or {}).get("intent")
        if intent in ("REFUND_REQUEST", "PRODUCT_ISSUE"):
            recent = [o for o in recent if o["status"] in ("PAID", "PROCESSING", "SHIPPED", "DELIVERED", "PARTIALLY_REFUNDED")] or recent
        elif intent == "DELAYED_SHIPMENT":
            recent = [o for o in recent if o["status"] in ("PROCESSING", "SHIPPED", "DELAYED")] or recent
        elif intent == "CANCELLATION":
            recent = [o for o in recent if o["status"] in ("PENDING_PAYMENT", "PAID", "PROCESSING")] or recent
        note = (state.get("classification") or {}).get("note") or ""
        prefix = "I couldn't find that order on your account. " if "not found" in note else "I can help with that. "
        listing = ", ".join(f"#{o['order_number']} ({_money(o['currency'], o['total'])}, {o['status'].lower().replace('_', ' ')})" for o in recent[:4])
        return prefix + "Which order is this about?" + (f" Your recent orders: {listing}." if listing else " Please share your order number.")
    if t == "escalated":
        return "I've escalated this to our support team and marked it high priority. A specialist will reply here shortly."
    if t == "refund":
        d, st = res.get("decision"), res.get("action_state")
        amt = None
        if order:
            pays = state.get("payments") or []
            amt = state["classification"].get("refund_amount") or (pays[-1]["refundable"] if pays else order["total"])
        if d == "AUTO_EXECUTE" and st == "SUCCEEDED":
            return f"Done — your refund of {_money(cur, amt)} for order #{order['order_number']} was completed by PayPal (refund ID {res.get('paypal_refund_id')}). It should appear on your PayPal account shortly{cite}."  # type: ignore[index]
        if d == "AUTO_EXECUTE" and st == "PENDING_CONFIRMATION":
            return f"Your refund of {_money(cur, amt)} for order #{order['order_number']} has been submitted to PayPal (refund ID {res.get('paypal_refund_id') or 'pending'}). PayPal is still processing it; I'll notify you when it completes{cite}."  # type: ignore[index]
        if d == "ESCALATED":
            return f"I've checked order #{order['order_number']}. Your refund request of {_money(cur, amt)} has been passed to a senior team member for manual review under our refund policy{cite}. No refund has been issued yet; you'll be notified as soon as they decide."  # type: ignore[index]
        if d == "REQUIRES_APPROVAL":
            return f"I've checked order #{order['order_number']} and your refund request of {_money(cur, amt)} needs a quick review by our team under our refund policy{cite}. You'll be notified as soon as a manager decides."  # type: ignore[index]
        if d == "REJECTED":
            return f"I'm sorry — this refund request for order #{order['order_number']} isn't eligible under our current refund policy{cite}. If you think this is wrong, reply 'talk to a human' and I'll escalate it."  # type: ignore[index]
        if st == "FAILED":
            return f"I tried to process your refund for order #{order['order_number']}, but it could not be completed: {str(res.get('error') or 'unknown error').rstrip('.')}. I've flagged it for our team."  # type: ignore[index]
        return "I need a bit more information to process this refund. Could you confirm the order and amount?"
    if t == "cannot_cancel_shipped":
        return f"Order #{order['order_number']} has already {res['status'].lower()}, so it can't be cancelled. I can start a refund request instead if you'd like to return it{cite}."  # type: ignore[index]
    if t == "cancelled":
        return f"Order #{res.get('order_number')} has been cancelled. No payment was taken."
    if t == "payment_explained":
        st = res.get("payment_status")
        if st == "CAPTURED":
            return f"Good news: the payment for order #{order['order_number']} was captured successfully by PayPal, so the order is paid."  # type: ignore[index]
        if st in ("FAILED", "DECLINED"):
            return f"The payment for order #{order['order_number']} didn't go through ({res.get('failure_reason') or 'declined by PayPal'}). No money was taken. You can retry checkout from your order page{cite}."  # type: ignore[index]
        return f"The payment for order #{order['order_number']} is currently {str(st).lower().replace('_', ' ')}. If you approved it on PayPal, it should complete shortly{cite}."  # type: ignore[index]
    if t in ("order_update", "product_issue_escalated"):
        f = " ".join(state.get("investigation", {}).get("findings", []))
        extra = " I've passed this to a specialist who will help with a replacement or return." if t == "product_issue_escalated" else ""
        return f"Here's the latest on order #{order['order_number']}: {f}{extra}{cite}"  # type: ignore[index]
    if t == "account_escalated":
        return "For account security, a support agent will help you with this. I've opened a ticket and they'll reply here."
    if cites:
        return f"Here's what I found in our help centre [{cites[0]['title']} v{cites[0]['version']}]: {cites[0]['excerpt']}…"
    return "I can help with orders, payments, refunds, cancellations and delivery questions. What do you need help with?"


def run_support_turn(db: Session, *, principal: Principal, conversation: Conversation, message: str) -> Message:
    started = time.perf_counter()
    execution = AgentExecution(
        business_id=principal.business_id,
        workflow="support",
        status=ExecutionStatus.RUNNING,
        triggered_by_user_id=principal.user_id,
        conversation_id=conversation.id,
        ticket_id=conversation.ticket_id,
        llm_mode=llm_mode(),
        input_summary=message[:500],
    )
    db.add(execution)
    db.commit()
    history = [{"role": m.role.value.lower(), "content": m.content} for m in db.scalars(select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at)).all()][:-1]
    wf = SupportWorkflow(db, principal, conversation, execution)
    state: SupportState = {"message": message, "history": history, "context": dict(conversation.context or {})}
    start_tracking()
    try:
        final: SupportState = wf.graph.invoke(state)
        reply_text = final["reply"]
        calls = tracked()
        if execution.llm_mode != "deterministic" and calls and not any(ok for ok, _ in calls):
            # every model call failed: say so instead of claiming the LLM answered
            execution.llm_mode = "rules (LLM failed)"
            wf.tracer.step("orchestrator", "llm_unavailable", f"LLM calls failed, answered in rule-based mode: {next((d for ok, d in calls if not ok), '')[:200]}")
        meta = {"citations": final.get("citations", []), "actions": final.get("actions", []), "intent": final["classification"]["intent"], "ticket": final.get("ticket"), "execution_id": str(execution.id), "llm_mode": execution.llm_mode, "resolution": final.get("resolution", {}).get("type")}
        conversation.context = final.get("context", {})
        if final.get("ticket") and conversation.ticket_id is None:
            conversation.ticket_id = uuid.UUID(final["ticket"]["ticket_id"])  # type: ignore[index]
        wf.tracer.finish(outcome=_resolution_summary(final.get("resolution", {"type": "info"})))
    except Exception as exc:
        log.exception("support workflow failed (execution %s)", execution.id)
        db.rollback()
        execution = db.get(AgentExecution, execution.id)  # type: ignore[assignment]
        assert execution is not None
        wf.tracer.execution = execution
        wf.tracer.step("orchestrator", "error", f"Workflow failed: {type(exc).__name__}")
        wf.tracer.finish(status=ExecutionStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
        execution.required_human = True
        reply_text = "Sorry — something went wrong while I was looking into this. I've logged it and a support agent can pick it up. You can also reply 'talk to a human'."
        meta = {"execution_id": str(execution.id), "error": True, "llm_mode": execution.llm_mode}
    execution.duration_ms = int((time.perf_counter() - started) * 1000)
    reply = Message(conversation_id=conversation.id, role=MessageRole.ASSISTANT, content=reply_text, agent_execution_id=execution.id, meta=meta)
    db.add(reply)
    conversation.updated_at = utcnow()
    db.commit()
    return reply


_ = IssueCategory
