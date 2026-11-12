from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models import AuditLog


def audit(
    db: Session,
    *,
    business_id: uuid.UUID | None,
    actor: str,
    action: str,
    summary: str,
    entity_type: str | None = None,
    entity_id: Any = None,
    data: dict[str, Any] | None = None,
    ip: str | None = None,
) -> AuditLog:
    """Append an audit record. `actor` is 'user:<id>', 'agent:<name>', 'system' or 'paypal'."""
    actor_type, _, actor_id = actor.partition(":")
    row = AuditLog(
        business_id=business_id,
        actor_type=actor_type or "system",
        actor_id=actor_id or None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        summary=summary,
        data=_jsonable(data or {}),
        ip_address=ip,
        created_at=utcnow(),
    )
    db.add(row)
    return row


def _jsonable(value: Any) -> Any:
    from datetime import datetime
    from decimal import Decimal
    from enum import Enum

    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


jsonable = _jsonable
