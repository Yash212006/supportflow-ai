"""Configurable LLM + embedding provider abstraction (OpenAI or Gemini via LangChain).

When no provider is configured the agents still run: deterministic nodes (investigation, policy,
risk, execution) are unaffected, and language steps use transparent rule-based fallbacks. The mode is
recorded on every AgentExecution (`llm_mode`) and shown in the UI, so nothing pretends to be an LLM.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import time
from collections.abc import Callable
from contextvars import ContextVar
from functools import lru_cache
from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel

from app.core.config import get_settings

log = logging.getLogger("supportflow.llm")

# Records, per request, whether each LLM call succeeded, so the UI can say which mode was really used.
_calls: ContextVar[list[tuple[bool, str]] | None] = ContextVar("llm_calls", default=None)


def start_tracking() -> None:
    _calls.set([])


def tracked() -> list[tuple[bool, str]]:
    return list(_calls.get() or [])


def _record(ok: bool, detail: str = "") -> None:
    calls = _calls.get()
    if calls is not None:
        calls.append((ok, detail))


def _err(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc)[:200]}"
T = TypeVar("T", bound=BaseModel)


def llm_mode() -> str:
    s = get_settings()
    if not s.llm_configured:
        return "deterministic"
    if s.llm_provider == "openai":
        return f"openai:{s.openai_model}"[:30]
    names = [s.gemini_model] + ([s.gemini_fallback_model] if s.gemini_fallback_model and s.gemini_fallback_model != s.gemini_model else [])
    return f"gemini:{names[min(_preferred['index'], len(names) - 1)]}"[:30]


@lru_cache
def _gemini(model: str) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    s = get_settings()
    kwargs: dict[str, Any] = {"vertexai": True} if s.gemini_use_vertexai else {"api_version": s.gemini_api_version}
    return ChatGoogleGenerativeAI(model=model, google_api_key=s.gemini_api_key, temperature=0.2, timeout=s.llm_timeout_seconds, max_retries=1, **kwargs)  # type: ignore[call-arg]


# Index into _candidates() of the model that last worked, so a failing primary is not retried on every call.
_preferred = {"index": 0}


def _candidates() -> list[tuple[str, BaseChatModel]]:
    s = get_settings()
    if not s.llm_configured:
        return []
    if s.llm_provider == "openai":
        from langchain_openai import ChatOpenAI

        return [(s.openai_model, ChatOpenAI(model=s.openai_model, api_key=s.openai_api_key, temperature=0.1, timeout=s.llm_timeout_seconds, max_retries=2))]  # type: ignore[arg-type]
    names = [s.gemini_model] + ([s.gemini_fallback_model] if s.gemini_fallback_model and s.gemini_fallback_model != s.gemini_model else [])
    return [(n, _gemini(n)) for n in names]


def get_chat_model() -> BaseChatModel | None:
    """The model to use now: the configured one, or its fallback if the configured one has been failing."""
    c = _candidates()
    if not c:
        return None
    return c[min(_preferred["index"], len(c) - 1)][1]


def _ordered() -> list[tuple[int, BaseChatModel]]:
    """Models in the order to try them: the currently preferred one first, then the others."""
    primary = get_chat_model()
    if primary is None:
        return []
    out: list[tuple[int, BaseChatModel]] = [(_preferred["index"], primary)]
    for i, (_n, m) in enumerate(_candidates()):
        if m is not primary:
            out.append((i, m))
    return out


def _with_fallback(fn: Callable[[BaseChatModel], Any], what: str) -> Any:
    last: Exception | None = None
    for i, model in _ordered():
        try:
            out = fn(model)
            if i != _preferred["index"]:
                log.warning("switching to fallback model #%d after errors on the configured model", i)
                _preferred["index"] = i
            return out
        except Exception as exc:
            log.warning("%s failed on model #%d: %s", what, i, _err(exc))
            last = exc
    assert last is not None
    raise last


def structured(system: str, user: str, schema: type[T]) -> T | None:
    """Structured output call; returns None (caller falls back to rules) if every model fails."""
    if get_chat_model() is None:
        return None
    try:
        out = _with_fallback(lambda m: m.with_structured_output(schema).invoke([("system", system), ("human", user)]), "structured LLM call")
        result = out if isinstance(out, schema) else schema.model_validate(out)
        _record(True)
        return result
    except Exception as exc:  # provider/network/parse failure → deterministic fallback
        _record(False, _err(exc))
        return None


def _text(res: Any) -> str:
    content: Any = res.content
    if isinstance(content, list):
        content = "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    return str(content).strip()


def complete(system: str, user: str) -> str | None:
    if get_chat_model() is None:
        return None
    try:
        text = _text(_with_fallback(lambda m: m.invoke([("system", system), ("human", user)]), "LLM completion")) or None
        _record(text is not None, "" if text else "empty response")
        return text
    except Exception as exc:
        _record(False, _err(exc))
        return None


def test_connection() -> dict[str, Any]:
    """One tiny call to each configured model, returning the provider's own result or error text."""
    s = get_settings()
    if not s.llm_configured:
        return {"ok": False, "mode": "deterministic", "detail": "No LLM provider configured (LLM_PROVIDER / API key)."}
    results = []
    ok_any = False
    for i, (name, model) in enumerate(_candidates()):
        started = time.perf_counter()
        try:
            reply = _text(model.invoke([("human", "Reply with the single word: ok")]))
            results.append(f"{name}: OK in {time.perf_counter() - started:.1f}s ({reply[:20]!r})")
            if not ok_any:
                _preferred["index"] = i
            ok_any = True
        except Exception as exc:
            results.append(f"{name}: FAILED after {time.perf_counter() - started:.1f}s, {_err(exc)}")
    return {"ok": ok_any, "mode": llm_mode(), "detail": " | ".join(results)}


# ------------------------------------------------------------------------------------ embeddings
def embedding_model_name() -> str:
    s = get_settings()
    if s.llm_provider == "openai" and s.openai_api_key:
        return f"openai:{s.openai_embedding_model}@{s.embedding_dimensions}"
    if s.llm_provider == "gemini" and s.gemini_api_key:
        return f"gemini:{s.gemini_embedding_model}"
    return f"local-hash@{s.embedding_dimensions}"


_TOKEN = re.compile(r"[a-z0-9]+")


def _hash_embed(text: str, dim: int) -> list[float]:
    """Deterministic lexical embedding (feature hashing of unigrams+bigrams). Not semantic; used
    only when no embedding provider is configured, and labelled as such."""
    vec = [0.0] * dim
    toks = _TOKEN.findall(text.lower())
    feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
    for f in feats:
        h = int(hashlib.md5(f.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0 if (h >> 8) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


LOCAL_PREFIX = "local-hash@"


def local_model_name() -> str:
    return f"{LOCAL_PREFIX}{get_settings().embedding_dimensions}"


def embed_provider(texts: list[str]) -> list[list[float]]:
    """Embed with the configured provider. Raises on provider failure; callers decide the fallback."""
    s = get_settings()
    dim = s.embedding_dimensions
    if s.llm_provider == "openai" and s.openai_api_key:
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=s.openai_embedding_model, api_key=s.openai_api_key, dimensions=dim).embed_documents(texts)  # type: ignore[arg-type]
    if s.llm_provider == "gemini" and s.gemini_api_key:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        ekw: dict[str, Any] = {"vertexai": True} if s.gemini_use_vertexai else {"api_version": s.gemini_api_version}
        emb = GoogleGenerativeAIEmbeddings(model=s.gemini_embedding_model, google_api_key=s.gemini_api_key, **ekw)  # type: ignore[call-arg]
        vecs = emb.embed_documents(texts, output_dimensionality=dim)
        return [v[:dim] + [0.0] * max(0, dim - len(v)) for v in vecs]
    return [_hash_embed(t, dim) for t in texts]


def embed_local(texts: list[str]) -> list[list[float]]:
    dim = get_settings().embedding_dimensions
    return [_hash_embed(t, dim) for t in texts]


def embed_with_fallback(texts: list[str]) -> tuple[list[list[float]], str]:
    """Embed with the provider; if it fails, use the local lexical embedding and say so in the model name.
    Each document records the model it was embedded with, so vectors from different spaces are never compared."""
    model = embedding_model_name()
    if model.startswith(LOCAL_PREFIX):
        return embed_local(texts), model
    try:
        return embed_provider(texts), model
    except Exception as exc:
        log.warning("embedding provider failed (%s: %s); using local lexical embedding", type(exc).__name__, str(exc)[:200])
        return embed_local(texts), local_model_name()
