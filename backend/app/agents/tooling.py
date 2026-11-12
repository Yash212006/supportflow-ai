"""Agent tool registry with per-agent permissions and observable execution traces.

Each agent can only call the tools listed for it in AGENT_PERMISSIONS. Every call (allowed or not)
is recorded as an AgentToolCall row. Tools receive a ToolContext that carries the tenant and, for
customer-facing workflows, the customer id: tools cannot reach data outside that scope.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models import AgentExecution, AgentToolCall
from app.models.enums import ExecutionStatus
from app.services.audit import jsonable

AGENT_PERMISSIONS: dict[str, set[str]] = {
    "orchestrator": {"list_customer_orders", "get_conversation_context", "create_or_update_ticket"},
    "order_investigation": {"list_customer_orders", "get_order_details", "get_payment_records", "get_shipment_records"},
    "policy_intelligence": {"search_knowledge_base", "get_active_policy"},
    "risk_assessment": {"assess_refund_risk"},
    "resolution": {"request_refund_action", "cancel_unpaid_order", "escalate_ticket", "resolve_ticket", "notify_customer"},
    "manager_copilot": {
        "search_orders",
        "get_order",
        "search_customers",
        "search_payments",
        "search_refunds",
        "search_tickets",
        "list_pending_approvals",
        "get_policies",
        "explain_decision",
        "get_analytics_summary",
        "summarize_agent_executions",
        "top_complaints",
        "refund_rate_by_product",
        "autonomy_trend",
        "prepare_refund_proposal",
        "search_knowledge_base",
    },
    "dashboard_agent": set(),  # AG Studio agent: no business tools, analytics data only, never actions
}


class ToolNotPermitted(Exception):
    pass


@dataclass
class ToolContext:
    db: Session
    business_id: uuid.UUID
    user_id: uuid.UUID
    customer_id: uuid.UUID | None = None  # set for customer workflows: hard scope


@dataclass
class Tracer:
    db: Session
    execution: AgentExecution
    started: float = field(default_factory=time.perf_counter)

    def step(self, agent: str, title: str, summary: str, **data: Any) -> None:
        steps = list(self.execution.steps or [])
        steps.append({"agent": agent, "step": title, "summary": summary[:1000], "at": utcnow().isoformat(), "data": jsonable(data) if data else {}})
        self.execution.steps = steps

    def finish(self, *, status: ExecutionStatus = ExecutionStatus.COMPLETED, outcome: str | None = None, error: str | None = None) -> None:
        self.execution.status = status
        self.execution.finished_at = utcnow()
        self.execution.duration_ms = int((time.perf_counter() - self.started) * 1000)
        if outcome:
            self.execution.outcome_summary = outcome[:2000]
        if error:
            self.execution.error = error[:2000]


class ToolRunner:
    def __init__(self, ctx: ToolContext, tracer: Tracer, registry: Mapping[str, Callable[..., Any]]):
        self.ctx = ctx
        self.tracer = tracer
        self.registry = registry

    def call(self, agent: str, tool: str, **kwargs: Any) -> Any:
        allowed = tool in AGENT_PERMISSIONS.get(agent, set())
        start = time.perf_counter()
        if not allowed or tool not in self.registry:
            self.ctx.db.add(AgentToolCall(execution_id=self.tracer.execution.id, agent=agent, tool=tool, arguments=jsonable(kwargs), result_summary="DENIED: tool not permitted for this agent", success=False, authorized=False, duration_ms=0))
            raise ToolNotPermitted(f"Agent '{agent}' is not permitted to call '{tool}'")
        try:
            result = self.registry[tool](self.ctx, **kwargs)
            summary = _summarise(result)
            ok = True
        except Exception as exc:
            summary, ok, result = f"error: {type(exc).__name__}: {exc}"[:500], False, None
            self.ctx.db.add(AgentToolCall(execution_id=self.tracer.execution.id, agent=agent, tool=tool, arguments=jsonable(kwargs), result_summary=summary, success=False, authorized=True, duration_ms=int((time.perf_counter() - start) * 1000)))
            raise
        self.ctx.db.add(AgentToolCall(execution_id=self.tracer.execution.id, agent=agent, tool=tool, arguments=jsonable(kwargs), result_summary=summary, success=ok, authorized=True, duration_ms=int((time.perf_counter() - start) * 1000)))
        return result


def _summarise(result: Any) -> str:
    if result is None:
        return "none"
    if isinstance(result, list):
        return f"{len(result)} record(s)"
    if isinstance(result, dict):
        keys = list(result.keys())[:8]
        return "fields: " + ", ".join(keys)
    return str(result)[:300]
