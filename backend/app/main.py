"""JOEAT backend entry point:  uvicorn app.main:app --reload"""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

import app.models  # noqa: F401  (register mappers)
from app.api.line_webhook import router as line_router
from app.api.merchant import router as merchant_router
from app.api.ops import router as ops_router
from app.api.polls import router as polls_router
from app.api.routes import router
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_engine

log = logging.getLogger("joeat")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="JOEAT 揪呷 API", version="0.1.0", description="LINE Bot + LIFF group dining decision MVP")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["*"], allow_headers=["*"])
    if settings.allow_test_evidence:
        log.warning("ALLOW_TEST_EVIDENCE is on: test-fixture claims are visible to the engine. Never enable in production.")
    if settings.auth_mode != "line":
        log.warning("AUTH_MODE=dev: the client supplies its own line_user_id. Not for production.")

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": exc.message, **exc.extra})

    @app.get("/healthz")
    def healthz():
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    app.include_router(router)
    app.include_router(polls_router)
    app.include_router(line_router)
    app.include_router(ops_router)
    app.include_router(merchant_router)
    return app


app = create_app()
