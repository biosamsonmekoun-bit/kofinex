"""Point d'entrée de l'API KOFINEX."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.db.session import engine

settings = get_settings()
logging.basicConfig(level=settings.log_level,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("kofinex.api")

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API REST de la plateforme KOFINEX (analyse financière SYSCOHADA / SYSCEBNL).",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url=f"{settings.api_v1_prefix}/docs" if settings.app_env != "production" else None,
    redoc_url=f"{settings.api_v1_prefix}/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,          # authentification par en-tête Bearer, pas par cookie
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = rid[:64]
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    logger.info("%s %s -> %s (%.0f ms) rid=%s user=%s", request.method, request.url.path,
                response.status_code, (time.perf_counter() - started) * 1000, request.state.request_id,
                getattr(request.state, "user_id", "-"))
    return response


register_error_handlers(app)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["Système"], include_in_schema=False)
def health() -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
