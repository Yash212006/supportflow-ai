from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config.settings import settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_path(url: str) -> None:
    if url.startswith("sqlite"):
        # sqlite:///./data/supportflow.db or sqlite:////abs
        path_part = url.split("///")[-1]
        if path_part and path_part != ":memory:":
            Path(path_part).parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_path(settings.database_url)

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from backend.models import (  # noqa: F401
        audit,
        customer,
        knowledge,
        order,
        refund,
        ticket,
        user,
    )

    Base.metadata.create_all(bind=engine)

    try:
        with SessionLocal() as db:
            from backend.services.order_service import sync_order_statuses

            sync_order_statuses(db)
    except Exception:
        pass
