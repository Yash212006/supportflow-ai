"""Persists sanitised PayPal API exchanges into paypal_transactions."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal, utcnow
from app.models import PayPalTransaction


def recorder_for(db: Session, *, business_id: uuid.UUID, payment_id: uuid.UUID | None = None, refund_id: uuid.UUID | None = None) -> Callable[[dict[str, Any]], None]:
    """Records go through a separate short session so they survive a rollback of the caller's
    transaction (a failed refund must still leave its PayPal exchange on record)."""

    def _record(row: dict[str, Any]) -> None:
        bind = db.get_bind()
        with Session(bind=bind) if bind is not None else SessionLocal() as s:
            s.add(
                PayPalTransaction(
                    business_id=business_id,
                    payment_id=payment_id,
                    refund_id=refund_id,
                    created_at=utcnow(),
                    **{k: v for k, v in row.items() if k in _FIELDS},
                )
            )
            s.commit()

    return _record


_FIELDS = {"operation", "request_id", "http_status", "paypal_debug_id", "resource_id", "resource_status", "outcome", "response_summary", "error_message", "duration_ms"}
