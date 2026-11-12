from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def enum_col(enum_cls: type[StrEnum], **kw: Any) -> Any:
    """Enum stored as VARCHAR with a CHECK constraint (portable, migration-friendly)."""
    return SAEnum(enum_cls, native_enum=False, length=40, validate_strings=True, values_callable=lambda e: [m.value for m in e], **kw)


def business_fk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
