from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_groq import ChatGroq

from backend.agent.prompts import SYSTEM_PROMPT
from backend.agent.state import get_session_memory
from backend.config.settings import settings
from backend.database.connection import SessionLocal
from backend.tools.registry import ToolRuntime, build_tools

logger = logging.getLogger("supportflow.agent")

INTENTS = {
    "ORDER_STATUS",
    "DELIVERY_DELAY",
    "REFUND_REQUEST",
    "CANCELLATION",
    "REPLACEMENT",
    "WARRANTY",
    "PAYMENT_ISSUE",
    "ACCOUNT_ISSUE",
    "GENERAL_INFORMATION",
    "ESCALATION",
}

MESSAGE_HISTORY: dict[str, list] = {}


def _llm(model_name: str | None = None) -> ChatGroq:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not configured.")
    m = model_name or settings.groq_model or "openai/gpt-oss-20b"
    return ChatGroq(
        api_key=settings.groq_api_key,
        model=m,
        temperature=0.1,
        max_retries=1,
    )


def _extract_json(text: str) -> dict | None:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    raw = match.group(1) if match else None
    if raw is None:
        match = re.search(r"(\{.*\"intent\".*\})", text, re.DOTALL)
        raw = match.group(1) if match else None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _guess_intent(message: str) -> str:
    q = message.lower()
    if "escalat" in q or "human" in q:
        return "ESCALATION"
    if "refund" in q:
        return "REFUND_REQUEST"
    if "cancel" in q:
        return "CANCELLATION"
    if "replac" in q:
        return "REPLACEMENT"
    if "warranty" in q:
        return "WARRANTY"
    if "payment" in q or "charged" in q:
        return "PAYMENT_ISSUE"
    if "account" in q:
        return "ACCOUNT_ISSUE"
    if "delay" in q or "late" in q:
        return "DELIVERY_DELAY"
    if "where" in q or "status" in q or "ord" in q:
        return "ORDER_STATUS"
    if "policy" in q:
        return "GENERAL_INFORMATION"
    return "GENERAL_INFORMATION"


def _update_memory(session_id: str, runtime: ToolRuntime, message: str) -> None:
    mem = get_session_memory(session_id)
    codes = re.findall(r"CUST\d+", message.upper())
    orders = re.findall(r"ORD\d+", message.upper())
    tickets = re.findall(r"TKT\d+", message.upper())
    if codes:
        mem.current_customer = codes[0]
    if orders:
        mem.current_order = orders[0]
    if tickets:
        mem.current_ticket = tickets[0]
    if runtime.last_order_number:
        mem.current_order = runtime.last_order_number
    if runtime.last_ticket_number:
        mem.current_ticket = runtime.last_ticket_number
    mem.current_issue = message[:400]


def run_investigation(
    message: str,
    session_id: str = "default",
    requested_by: str = "support_executive",
) -> dict[str, Any]:
    started = time.perf_counter()
    logger.info("agent_start session=%s query=%s", session_id, message[:300])
    db = SessionLocal()
    runtime = ToolRuntime(db, requested_by=requested_by)
    mem = get_session_memory(session_id)
    _update_memory(session_id, runtime, message)

    fallback = {
        "session_id": session_id,
        "intent": _guess_intent(message),
        "answer": "",
        "facts": [],
        "policy": [],
        "recommendation": None,
        "proposed_action": None,
        "requires_approval": False,
        "customer_response": None,
        "tools_used": [],
        "sources": [],
        "latency_ms": 0,
        "error": None,
    }

    try:
        tools = build_tools(runtime)
        tool_map = {t.name: t for t in tools}

        candidate_models = [settings.groq_model]
        for m in ["openai/gpt-oss-20b", "qwen/qwen3.8-27b", "openai/gpt-oss-120b"]:
            if m not in candidate_models:
                candidate_models.append(m)

        def invoke_with_retry_and_fallback(msgs: list) -> AIMessage:
            last_err: Exception | None = None
            for model_name in candidate_models:
                try:
                    llm = _llm(model_name).bind_tools(tools)
                except Exception as e:
                    last_err = e
                    logger.warning("Could not bind tools for model=%s: %s", model_name, e)
                    continue

                for attempt in range(2):
                    try:
                        return llm.invoke(msgs)
                    except Exception as e:
                        last_err = e
                        err_str = str(e).lower()
                        if "429" in err_str or "rate limit" in err_str or "too many requests" in err_str:
                            logger.warning(
                                "Groq rate limit on model=%s attempt=%s. %s",
                                model_name,
                                attempt,
                                "Waiting for rate limit window to clear (3s)..." if attempt == 0 else "Switching to fallback model...",
                            )
                            time.sleep(3.0)
                        else:
                            logger.warning("Model invocation error on %s attempt=%s: %s", model_name, attempt, e)
                            break

            if last_err is not None:
                raise last_err
            raise RuntimeError("All candidate LLM models failed to process the request.")

        history = MESSAGE_HISTORY.setdefault(session_id, [])
        # Only take recent history to avoid consuming excessive tokens
        recent_history = history[-4:] if len(history) > 4 else history
        user_block = (
            f"Support session context:\n"
            f"Current customer: {mem.current_customer}\n"
            f"Current order: {mem.current_order}\n"
            f"Current ticket: {mem.current_ticket}\n\n"
            f"Executive request:\n{message}"
        )
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + recent_history + [HumanMessage(content=user_block)]

        final_text = ""
        for _ in range(settings.agent_max_iterations):
            ai: AIMessage = invoke_with_retry_and_fallback(messages)
            messages.append(ai)
            if not getattr(ai, "tool_calls", None):
                final_text = ai.content if isinstance(ai.content, str) else str(ai.content)
                break
            for call in ai.tool_calls:
                name = call["name"]
                args = call.get("args") or {}
                tool = tool_map.get(name)
                if tool is None:
                    output = json.dumps({"ok": False, "error": f"Tool {name} is not allowlisted."})
                    runtime.record(name, "unauthorized", {"error": "not allowlisted"}, 0)
                else:
                    try:
                        output = tool.invoke(args)
                    except Exception as exc:
                        output = json.dumps({"ok": False, "error": "Invalid tool arguments or tool failure.", "detail": str(exc)})
                out_str = str(output)
                if len(out_str) > 1200:
                    out_str = out_str[:1200] + "... [truncated]"
                messages.append(ToolMessage(content=out_str, tool_call_id=call["id"]))
        else:
            final_text = "I reached the investigation step limit without a complete answer. Please retry with a more specific request."

        parsed = _extract_json(final_text) or {}
        prose = re.sub(r"```json.*?```", "", final_text, flags=re.DOTALL).strip()
        if prose.startswith("{") and prose.endswith("}"):
            prose = ""
        if not prose and parsed:
            prose = parsed.get("recommendation") or parsed.get("customer_response") or "Investigation completed."

        history.append(HumanMessage(content=message))
        history.append(AIMessage(content=prose or final_text))
        if len(history) > 8:
            MESSAGE_HISTORY[session_id] = history[-8:]

        _update_memory(session_id, runtime, message)
        latency = int((time.perf_counter() - started) * 1000)
        intent = parsed.get("intent") if parsed.get("intent") in INTENTS else _guess_intent(message)
        logger.info(
            "agent_done session=%s tools=%s latency_ms=%s",
            session_id,
            [t["tool_name"] for t in runtime.traces],
            latency,
        )
        return {
            "session_id": session_id,
            "intent": intent,
            "answer": prose or final_text,
            "facts": parsed.get("facts") or [],
            "policy": parsed.get("policy") or [],
            "recommendation": parsed.get("recommendation"),
            "proposed_action": parsed.get("proposed_action"),
            "requires_approval": bool(parsed.get("requires_approval")),
            "customer_response": parsed.get("customer_response"),
            "tools_used": runtime.traces,
            "sources": runtime.sources,
            "latency_ms": latency,
            "error": None,
        }
    except RuntimeError as exc:
        fallback["error"] = str(exc)
        fallback["answer"] = (
            "The language model is not configured. Set GROQ_API_KEY in your .env file. "
            "Business lookups still work from the Tickets, Customers, and Orders pages."
        )
        fallback["tools_used"] = runtime.traces
        fallback["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return fallback
    except Exception as exc:
        logger.exception("agent_failure")
        err_str = str(exc)
        is_rate_limit = "429" in err_str or "rate limit" in err_str.lower() or "too many requests" in err_str.lower()
        fallback["error"] = "Rate limit reached" if is_rate_limit else "LLM failure"
        if is_rate_limit:
            fallback["answer"] = (
                "The AI service rate limit was reached (tokens per minute/day on the free tier). "
                "Please wait a few seconds and try again, or click 'New Session' to start with a fresh context."
            )
        else:
            fallback["answer"] = (
                "I could not complete the investigation because the model or a tool failed. "
                "Please verify identifiers and try again. I will not invent missing records."
            )
        fallback["tools_used"] = runtime.traces
        fallback["sources"] = runtime.sources
        fallback["latency_ms"] = int((time.perf_counter() - started) * 1000)
        fallback["detail"] = str(exc)
        return fallback
    finally:
        db.close()
