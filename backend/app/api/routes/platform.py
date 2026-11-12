"""Agents, analytics, knowledge base, dashboards and integration status APIs."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import service as analytics
from app.api.serializers import message_out
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import Principal, require_customer, require_manager, require_staff
from app.core.errors import NotFound, ValidationFailed
from app.models import Conversation, DashboardPreference, KnowledgeDocument, Message
from app.models.enums import DocumentStatus
from app.services.audit import audit, jsonable

router = APIRouter(prefix="/api", tags=["platform"])


# ------------------------------------------------------------------------------------ agents
class SupportRunIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None


@router.post("/agents/support/run")
def support_run(body: SupportRunIn, p: Principal = Depends(require_customer), db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.api.routes.customer import ChatIn, chat

    return chat(ChatIn(message=body.message, conversation_id=body.conversation_id), p, db)


class CopilotIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None


@router.post("/agents/copilot/run")
def copilot_run(body: CopilotIn, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.agents.copilot import run_copilot

    return run_copilot(db, principal=p, message=body.message, conversation_id=body.conversation_id)


@router.get("/agents/copilot/conversations")
def copilot_conversations(p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Conversation).where(Conversation.user_id == p.user_id, Conversation.channel == "copilot").order_by(Conversation.updated_at.desc()).limit(30)).all()
    return [{"id": str(c.id), "title": c.title, "updated_at": c.updated_at.isoformat()} for c in rows]


@router.get("/agents/copilot/conversations/{conv_id}")
def copilot_conversation(conv_id: uuid.UUID, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    c = db.get(Conversation, conv_id)
    if c is None or c.user_id != p.user_id:
        raise NotFound("Conversation not found")
    return {"id": str(c.id), "title": c.title, "messages": [message_out(m) for m in db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at))]}


# ------------------------------------------------------------------------------------ analytics
@router.get("/analytics/overview")
def overview(days: int = 30, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    return analytics.overview(db, p.business_id, days=min(max(days, 1), 365))


def _ds(name: str, p: Principal, db: Session) -> list[dict[str, Any]]:
    return analytics.DATASETS[name][1](db, p.business_id)


@router.get("/analytics/payments")
def a_payments(p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return _ds("payments", p, db)


@router.get("/analytics/refunds")
def a_refunds(p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return _ds("refunds", p, db)


@router.get("/analytics/support")
def a_support(p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return _ds("tickets", p, db)


@router.get("/analytics/ai-operations")
def a_ai(p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return _ds("agent_executions", p, db)


@router.get("/analytics/risk")
def a_risk(p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    refunds = _ds("refunds", p, db)
    high = [r for r in refunds if r["risk_level"] == "HIGH"]
    from collections import Counter

    repeat = [{"customer": c, "refund_requests": n} for c, n in Counter(r["customer"] for r in refunds).most_common() if n >= 2]
    by_day = Counter(r["created_date"] for r in refunds)
    avg = (sum(by_day.values()) / len(by_day)) if by_day else 0
    spikes = [{"date": d, "refunds": n, "baseline": round(avg, 2)} for d, n in sorted(by_day.items()) if avg and n >= max(3, 2 * avg)]
    return {"high_risk_refunds": high, "repeat_requesters": repeat, "refund_spikes": spikes, "manual_review_queue": [r for r in refunds if r["status"] == "AWAITING_APPROVAL"]}


@router.get("/analytics/datasets")
def datasets(p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    """All AG Studio data sources in one call (authorised, tenant-scoped, fixed column sets)."""
    return {"sources": [{"id": key, "name": label, "data": fn(db, p.business_id)} for key, (label, fn) in analytics.DATASETS.items()]}


# ------------------------------------------------------------------------------------ dashboards (AG Studio state)
class DashboardIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    state: dict[str, Any]
    is_default: bool = False
    studio_version: str | None = None


@router.get("/dashboards")
def list_dashboards(p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(DashboardPreference).where(DashboardPreference.user_id == p.user_id).order_by(DashboardPreference.updated_at.desc())).all()
    return [jsonable({"id": d.id, "name": d.name, "is_default": d.is_default, "updated_at": d.updated_at, "studio_version": d.studio_version}) for d in rows]


@router.get("/dashboards/{dash_id}")
def get_dashboard(dash_id: uuid.UUID, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    d = db.get(DashboardPreference, dash_id)
    if d is None or d.user_id != p.user_id:
        raise NotFound("Dashboard not found")
    return jsonable({"id": d.id, "name": d.name, "is_default": d.is_default, "state": d.state, "updated_at": d.updated_at})


@router.post("/dashboards")
def save_dashboard(body: DashboardIn, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    import json

    if len(json.dumps(body.state)) > 2_000_000:
        raise ValidationFailed("Dashboard state too large")
    d = db.scalars(select(DashboardPreference).where(DashboardPreference.user_id == p.user_id, DashboardPreference.name == body.name)).first()
    if d is None:
        d = DashboardPreference(business_id=p.business_id, user_id=p.user_id, name=body.name, state=body.state)
        db.add(d)
    d.state = body.state
    d.studio_version = body.studio_version
    if body.is_default:
        for other in db.scalars(select(DashboardPreference).where(DashboardPreference.user_id == p.user_id)):
            other.is_default = False
        d.is_default = True
    db.commit()
    return jsonable({"id": d.id, "name": d.name, "is_default": d.is_default, "updated_at": d.updated_at})


@router.delete("/dashboards/{dash_id}")
def delete_dashboard(dash_id: uuid.UUID, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    d = db.get(DashboardPreference, dash_id)
    if d is None or d.user_id != p.user_id:
        raise NotFound("Dashboard not found")
    db.delete(d)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------------------------ knowledge
def _doc_out(d: KnowledgeDocument) -> dict[str, Any]:
    return jsonable({"id": d.id, "doc_key": d.doc_key, "version": d.version, "is_current": d.is_current, "title": d.title, "category": d.category, "filename": d.filename, "size_bytes": d.size_bytes, "status": d.status, "embedding_model": d.embedding_model, "chunk_count": d.chunk_count, "error": d.error, "created_at": d.created_at})


@router.post("/knowledge/upload")
async def upload(file: UploadFile = File(...), title: str = Form(...), category: str = Form(...), doc_key: str | None = Form(None), p: Principal = Depends(require_manager), db: Session = Depends(get_db)) -> dict[str, Any]:
    from starlette.concurrency import run_in_threadpool

    from app.knowledge.service import ingest_document

    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValidationFailed(f"File exceeds {get_settings().max_upload_mb} MB")
    name = (file.filename or "upload.txt").replace("/", "_").replace("\\", "_")[:200]

    def _do() -> dict[str, Any]:
        doc = ingest_document(db, business_id=p.business_id, title=title.strip()[:250], category=category, filename=name, data=data, uploaded_by=p.user_id, doc_key=doc_key)
        db.commit()
        return _doc_out(doc)

    return await run_in_threadpool(_do)


@router.get("/knowledge/documents")
def documents(include_history: bool = True, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.business_id == p.business_id)
    if not include_history:
        stmt = stmt.where(KnowledgeDocument.is_current.is_(True))
    return [_doc_out(d) for d in db.scalars(stmt.order_by(KnowledgeDocument.doc_key, KnowledgeDocument.version.desc()))]


@router.get("/knowledge/documents/{doc_id}")
def document(doc_id: uuid.UUID, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    d = db.get(KnowledgeDocument, doc_id)
    if d is None or d.business_id != p.business_id:
        raise NotFound("Document not found")
    out = _doc_out(d)
    out["chunks"] = [{"index": c.chunk_index, "content": c.content} for c in sorted(d.chunks, key=lambda c: c.chunk_index)]
    return out


@router.delete("/knowledge/documents/{doc_id}")
def delete_document(doc_id: uuid.UUID, p: Principal = Depends(require_manager), db: Session = Depends(get_db)) -> dict[str, Any]:
    d = db.get(KnowledgeDocument, doc_id)
    if d is None or d.business_id != p.business_id:
        raise NotFound("Document not found")
    was_current, key = d.is_current, d.doc_key
    audit(db, business_id=p.business_id, actor=p.actor, action="knowledge.deleted", entity_type="knowledge_document", entity_id=d.id, summary=f"Deleted '{d.title}' v{d.version}")
    db.delete(d)
    db.flush()
    if was_current:  # promote the previous version, if any
        prev = db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.business_id == p.business_id, KnowledgeDocument.doc_key == key).order_by(KnowledgeDocument.version.desc())).first()
        if prev is not None and prev.chunk_count:
            prev.is_current, prev.status = True, DocumentStatus.READY
    db.commit()
    return {"ok": True}


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    category: str | None = None


@router.post("/knowledge/search")
def kb_search(body: SearchIn, p: Principal = Depends(require_staff), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    from app.knowledge.service import search

    return [c.to_dict() for c in search(db, p.business_id, body.query, category=body.category, k=6)]


@router.post("/knowledge/reembed")
def reembed(p: Principal = Depends(require_manager), db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.knowledge.service import reembed_all

    n = reembed_all(db, p.business_id)
    db.commit()
    return {"reembedded_documents": n}


# ------------------------------------------------------------------------------------ integrations
@router.post("/integrations/test-llm")
def test_llm(p: Principal = Depends(require_manager)) -> dict[str, Any]:
    """Makes one tiny model call and returns the provider's own result or error text (never the key)."""
    from app.agents.llm import test_connection

    out = test_connection()
    key = get_settings().gemini_api_key or get_settings().openai_api_key
    if key and key in out["detail"]:
        out["detail"] = out["detail"].replace(key, "***")
    return out


@router.get("/integrations/status")
def integrations(p: Principal = Depends(require_staff)) -> dict[str, Any]:
    from app.agents.llm import embedding_model_name, llm_mode

    s = get_settings()
    redis_ok = True
    try:
        import redis

        redis.Redis.from_url(s.redis_url, socket_timeout=0.5).ping()
    except Exception:
        redis_ok = False
    return {
        "paypal": {"configured": s.paypal_configured, "webhook_configured": s.paypal_webhook_configured, "base_url": s.paypal_base_url, "mode": "sandbox" if "sandbox" in s.paypal_base_url else "live", "sdk": "APIMatic PayPal Server SDK (python) 2.29"},
        "llm": {"configured": s.llm_configured, "provider": s.llm_provider, "mode": llm_mode()},
        "embeddings": {"model": embedding_model_name(), "semantic": not embedding_model_name().startswith("local-hash")},
        "ag_studio": {"license_configured": bool(s.ag_license_key), "ai_enabled": s.llm_configured},
        "redis": {"connected": redis_ok},
    }
