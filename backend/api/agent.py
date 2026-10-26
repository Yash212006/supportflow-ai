from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.agent.executor import run_investigation
from backend.agent.state import clear_session_memory
from backend.schemas import ChatRequest, LoginRequest, LoginResponse
from backend.database.connection import SessionLocal, get_db
from backend.services.auth_service import verify_login
from backend.tools.registry import analytics_snapshot
from backend.services.approval_service import list_audit

router = APIRouter(prefix="/api", tags=["agent"])


@router.post("/chat")
def chat(payload: ChatRequest):
    return run_investigation(payload.message, payload.session_id, payload.requested_by)


@router.post("/agent/investigate")
def investigate(payload: ChatRequest):
    return run_investigation(payload.message, payload.session_id, payload.requested_by)


@router.post("/session/clear")
def clear_session(session_id: str = "default"):
    clear_session_memory(session_id)
    return {"ok": True}


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    db = SessionLocal()
    try:
        user = verify_login(db, payload.email, payload.password)
        if not user:
            return LoginResponse(ok=False, message="Invalid credentials.")
        return LoginResponse(ok=True, display_name=user.display_name, email=user.email)
    finally:
        db.close()


@router.get("/analytics")
def analytics(db: Session = Depends(get_db)):
    return analytics_snapshot(db=db)


@router.get("/audit")
def audit():
    db = SessionLocal()
    try:
        rows = list_audit(db)
        return [
            {
                "id": r.id,
                "action_id": r.action_id,
                "ticket_id": r.ticket_id,
                "action_type": r.action_type,
                "requested_by": r.requested_by,
                "agent_reason": r.agent_reason,
                "tool_name": r.tool_name,
                "parameters": r.parameters,
                "approval_status": r.approval_status,
                "executed_at": r.executed_at.isoformat() if r.executed_at else None,
                "result": r.result,
                "latency_ms": r.latency_ms,
            }
            for r in rows
        ]
    finally:
        db.close()
