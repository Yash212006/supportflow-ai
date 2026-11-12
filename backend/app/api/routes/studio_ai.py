"""Backend LLM proxy for the AG Studio Agent Framework.

AG Studio ships no LLM: its harness calls an `AgLlmAdapter.executeTurn(request)` that we implement in
the frontend (`frontend/src/integrations/ag-studio/supportflowAdapter.ts`). That adapter POSTs the
AgLlmRequest here, so model credentials never reach the browser.

Safety:
- staff only, rate-limited, size-limited
- the only tools offered to the model are the ones AG Studio declares (client-side dashboard tools:
  widgets, pages, data views). No SupportFlow business tool is ever exposed here, so the dashboard
  agent cannot read beyond the analytics data already loaded into Studio and cannot trigger refunds,
  payments or any other financial operation.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.llm import get_chat_model, llm_mode
from app.core.database import get_db
from app.core.deps import Principal, require_staff
from app.core.errors import IntegrationUnavailable, ValidationFailed
from app.models import AgentExecution, AgentToolCall
from app.models.enums import ExecutionStatus

router = APIRouter(prefix="/api/studio-ai", tags=["ag-studio"])

MAX_BODY = 1_500_000
FORBIDDEN_TOOL_PREFIXES = ("refund", "payment", "paypal", "approve", "execute_")


class TurnIn(BaseModel):
    input: list[dict[str, Any]] = Field(default_factory=list)
    instructions: str | None = None
    tools: list[dict[str, Any]] | None = None
    toolChoice: Any = "auto"  # noqa: N815 (AG wire name)
    responseFormat: dict[str, Any] = Field(default_factory=lambda: {"type": "text"})  # noqa: N815
    model: dict[str, Any] | None = None
    trace: dict[str, Any] | None = None


def _text(content: list[dict[str, Any]] | None) -> str:
    parts = []
    for c in content or []:
        if c.get("type") == "text":
            parts.append(str(c.get("text", "")))
        elif c.get("type") == "refusal":
            parts.append(str(c.get("refusal", "")))
    return "\n".join(parts)


def to_langchain(items: list[dict[str, Any]], instructions: str | None) -> list[BaseMessage]:
    msgs: list[BaseMessage] = []
    if instructions:
        msgs.append(SystemMessage(content=instructions))
    pending_ai: AIMessage | None = None
    for it in items:
        t = it.get("type")
        if t == "message" and it.get("role") in ("user", "system"):
            pending_ai = None
            text = _text(it.get("content"))
            msgs.append(SystemMessage(content=text) if it["role"] == "system" else HumanMessage(content=text))
        elif t == "message" and it.get("role") == "assistant":
            pending_ai = AIMessage(content=_text(it.get("content")))
            msgs.append(pending_ai)
        elif t == "function_call":
            try:
                args = json.loads(it.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            call = {"id": it.get("callId") or it.get("id"), "name": it.get("name"), "args": args, "type": "tool_call"}
            if pending_ai is None:
                pending_ai = AIMessage(content="", tool_calls=[call])
                msgs.append(pending_ai)
            else:
                pending_ai.tool_calls = [*pending_ai.tool_calls, call]  # type: ignore[list-item]
        elif t == "function_call_output":
            pending_ai = None
            msgs.append(ToolMessage(content=str(it.get("output", "")), tool_call_id=str(it.get("callId"))))
        # reasoning items are not replayed
    return msgs


@router.get("/config")
def config(p: Principal = Depends(require_staff)) -> dict[str, Any]:
    model = get_chat_model()
    return {"enabled": model is not None, "mode": llm_mode(), "models": [{"id": llm_mode(), "label": llm_mode()}] if model is not None else []}


@router.post("/turn")
async def turn(request: Request, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise ValidationFailed("AI request too large")
    body = TurnIn.model_validate_json(raw)
    model = get_chat_model()
    if model is None:
        raise IntegrationUnavailable("No LLM provider is configured. Set LLM_PROVIDER and an API key to enable AG Studio AI.", code="llm_not_configured")
    tools = body.tools or []
    for tdef in tools:
        if str(tdef.get("name", "")).lower().startswith(FORBIDDEN_TOOL_PREFIXES):
            raise ValidationFailed("Financial tools are not permitted in the analytics agent")
    if len(tools) > 128:
        raise ValidationFailed("Too many tools")

    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(_execute, db, p, body, tools)


def _execute(db: Session, p: Principal, body: TurnIn, tools: list[dict[str, Any]]) -> dict[str, Any]:
    started = time.perf_counter()
    model = get_chat_model()
    assert model is not None
    msgs = to_langchain(body.input, body.instructions)
    rid = f"resp_{uuid.uuid4().hex[:20]}"
    output: list[dict[str, Any]] = []
    error: dict[str, str] | None = None
    usage: dict[str, Any] | None = None
    try:
        rf = body.responseFormat or {"type": "text"}
        if rf.get("type") == "json" and not tools:
            structured = model.with_structured_output(rf.get("schema") or {}, include_raw=False)
            data = structured.invoke(msgs)
            output.append(_message(json.dumps(data)))
        else:
            runnable: Any = model
            if tools:
                lc_tools = [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("parameters") or {"type": "object", "properties": {}}}} for t in tools]
                choice = body.toolChoice
                tc: Any = None
                if isinstance(choice, dict) and choice.get("name"):
                    tc = choice["name"]
                elif choice in ("required",):
                    tc = "any" if "Google" in type(model).__name__ else "required"
                elif choice == "none":
                    tc = None
                    lc_tools = []
                if lc_tools:
                    runnable = model.bind_tools(lc_tools, tool_choice=tc) if tc else model.bind_tools(lc_tools)
            res = runnable.invoke(msgs)
            text = res.content if isinstance(res.content, str) else "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in res.content)
            if text:
                output.append(_message(text))
            for call in getattr(res, "tool_calls", []) or []:
                cid = call.get("id") or f"call_{uuid.uuid4().hex[:16]}"
                output.append({"id": f"fc_{uuid.uuid4().hex[:16]}", "kind": "output", "type": "function_call", "callId": cid, "name": call["name"], "arguments": json.dumps(call.get("args") or {}), "status": "completed"})
            um = getattr(res, "usage_metadata", None)
            if um:
                usage = {"inputTokens": um.get("input_tokens"), "outputTokens": um.get("output_tokens"), "totalTokens": um.get("total_tokens")}
    except Exception as exc:
        error = {"code": "provider_error", "message": f"{type(exc).__name__}: {str(exc)[:300]}"}
    # observability: record as an agent execution of the dashboard agent
    ex = AgentExecution(
        business_id=p.business_id,
        workflow="dashboard",
        status=ExecutionStatus.FAILED if error else ExecutionStatus.COMPLETED,
        triggered_by_user_id=p.user_id,
        llm_mode=llm_mode(),
        intent="DASHBOARD_TURN",
        input_summary=_last_user_text(body.input)[:500],
        outcome_summary=(f"{sum(1 for o in output if o['type'] == 'function_call')} dashboard tool call(s)" if not error else None),
        error=error["message"] if error else None,
        duration_ms=int((time.perf_counter() - started) * 1000),
        steps=[{"agent": "dashboard_agent", "step": "turn", "summary": f"AG Studio turn with {len(tools)} studio tools offered", "at": ""}],
    )
    db.add(ex)
    db.flush()
    for o in output:
        if o["type"] == "function_call":
            db.add(AgentToolCall(execution_id=ex.id, agent="dashboard_agent", tool=o["name"], arguments={"arguments": o["arguments"][:2000]}, result_summary="executed client-side by AG Studio", success=True, authorized=True))
    db.commit()
    return {"id": rid, "createdAt": int(time.time() * 1000), "status": "failed" if error else "completed", "output": output, "error": error, "usage": usage, "model": llm_mode()}


def _message(text: str) -> dict[str, Any]:
    return {"id": f"msg_{uuid.uuid4().hex[:16]}", "kind": "output", "type": "message", "role": "assistant", "status": "completed", "content": [{"type": "text", "text": text, "annotations": []}]}


def _last_user_text(items: list[dict[str, Any]]) -> str:
    for it in reversed(items):
        if it.get("type") == "message" and it.get("role") == "user":
            return _text(it.get("content"))
    return ""
