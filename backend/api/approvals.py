from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.schemas import ApprovalDecision, PendingActionOut
from backend.services.approval_service import (
    approve_action,
    get_pending_by_action_id,
    list_pending_actions,
    reject_action,
)

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("", response_model=list[PendingActionOut])
def list_approvals(status: str | None = "PENDING_APPROVAL", db: Session = Depends(get_db)):
    return list_pending_actions(db, status=status)


@router.post("/{action_id}/approve")
def approve(action_id: str, payload: ApprovalDecision, db: Session = Depends(get_db)):
    action = get_pending_by_action_id(db, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Approval item not found")
    result = approve_action(db, action, payload.reviewed_by, payload.note)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/{action_id}/reject")
def reject(action_id: str, payload: ApprovalDecision, db: Session = Depends(get_db)):
    action = get_pending_by_action_id(db, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Approval item not found")
    return reject_action(db, action, payload.reviewed_by, payload.note)
