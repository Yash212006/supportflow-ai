import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.agent import router as agent_router
from backend.api.approvals import router as approvals_router
from backend.api.customers import router as customers_router
from backend.api.knowledge import router as knowledge_router
from backend.api.orders import router as orders_router
from backend.api.refunds import router as refunds_router
from backend.api.tickets import router as tickets_router
from backend.config.settings import settings
from backend.database.connection import SessionLocal, init_db
from backend.database.seed import seed_database

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("supportflow")


def bootstrap() -> None:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.knowledge_base_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.chroma_persist_directory).mkdir(parents=True, exist_ok=True)
    init_db()
    seed_database()
    kb_dir = Path(settings.knowledge_base_dir)
    if not any(kb_dir.glob("*.pdf")):
        from backend.rag.generate_policies import generate_knowledge_pdfs

        generate_knowledge_pdfs(kb_dir)
    try:
        db = SessionLocal()
        from backend.models.knowledge import KnowledgeDocument
        from backend.rag.ingestion import ingest_directory

        if db.query(KnowledgeDocument).count() == 0:
            ingest_directory(kb_dir, db=db)
        db.close()
    except Exception:
        logger.exception("Knowledge indexing skipped (embeddings may still download on first use).")


def create_app(*, run_bootstrap: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if run_bootstrap:
            bootstrap()
        yield

    application = FastAPI(
        title="SupportFlow AI",
        description="Investigate. Reason. Recommend. Act — with Human Approval.",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(customers_router)
    application.include_router(orders_router)
    application.include_router(tickets_router)
    application.include_router(approvals_router)
    application.include_router(refunds_router)
    application.include_router(knowledge_router)
    application.include_router(agent_router)

    @application.get("/health")
    def health():
        return {"status": "ok", "service": "supportflow-ai"}

    return application


app = create_app(run_bootstrap=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host=settings.api_host, port=settings.api_port, reload=True)
