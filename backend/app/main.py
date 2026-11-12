from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routes import auth, customer, manager, paypal, platform, studio_ai
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.core.rate_limit import api_limit
from app.integrations.paypal.client import close_paypal_client

logging.basicConfig(level=logging.INFO, format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("supportflow")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    if s.environment == "production" and (s.jwt_secret.startswith("change-me") or len(s.jwt_secret) < 32):
        raise RuntimeError("JWT_SECRET must be set to a long random value in production")
    log.info("starting SupportFlow AI env=%s paypal_configured=%s llm=%s", s.environment, s.paypal_configured, s.llm_provider)
    yield
    close_paypal_client()


settings = get_settings()
app = FastAPI(title="SupportFlow AI API", version="1.0.0", lifespan=lifespan, dependencies=[Depends(api_limit)])
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-Id"] = rid
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.path.startswith("/api"):
        log.info("%s %s %s %dms rid=%s", request.method, request.url.path, response.status_code, int((time.perf_counter() - start) * 1000), rid)
    return response


@app.exception_handler(AppError)
async def app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}})


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": {"code": "validation_failed", "message": "Request validation failed", "details": details}})


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error: %s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "Internal server error"}})


@app.get("/health")
def health() -> dict[str, object]:
    db_ok = True
    try:
        with SessionLocal() as s:
            s.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "paypal_configured": settings.paypal_configured, "llm_configured": settings.llm_configured}


for r in (auth.router, customer.router, manager.router, paypal.router, platform.router, studio_ai.router):
    app.include_router(r)
