import json
from pathlib import Path

import pytest

from backend.database.connection import SessionLocal, init_db
from backend.database.seed import seed_database
from backend.main import create_app
from backend.rag.generate_policies import generate_knowledge_pdfs
from backend.tools.registry import ToolRuntime, build_tools

from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def seeded_db():
    init_db()
    seed_database()
    kb = Path(__file__).resolve().parents[1] / "knowledge_base"
    if not any(kb.glob("*.pdf")):
        generate_knowledge_pdfs(kb)
    yield
    SessionLocal().close()


@pytest.fixture
def db(seeded_db):
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def tools(db):
    runtime = ToolRuntime(db, requested_by="pytest")
    mapping = {t.name: t for t in build_tools(runtime)}
    return runtime, mapping


@pytest.fixture
def client(seeded_db):
    app = create_app(run_bootstrap=False)
    with TestClient(app) as test_client:
        yield test_client


def parse_tool(result) -> dict:
    if isinstance(result, dict):
        return result
    return json.loads(result)
