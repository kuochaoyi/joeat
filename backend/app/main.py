"""JOEAT backend entry point:  uvicorn app.main:app --reload"""
import logging

from a2wsgi import WSGIMiddleware
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text

import app.models  # noqa: F401  (register mappers)
from app.api.line_webhook import router as line_router
from app.api.merchant import router as merchant_router
from app.api.ops import DASH_COOKIE_NAME, public_router as ops_public_router, router as ops_router, verify_dash_cookie
from app.api.polls import router as polls_router
from app.api.routes import router
from app.core.config import get_settings
from app.core.errors import AppError
from app.dash_app import dash_app
from app.db.session import get_engine

log = logging.getLogger("joeat")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="JOEAT 揪呷 API", version="0.1.0", description="LINE Bot + LIFF group dining decision MVP")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if settings.allow_test_evidence:
        log.warning("ALLOW_TEST_EVIDENCE is on: test-fixture claims are visible to the engine. Never enable in production.")
    if settings.auth_mode != "line":
        log.warning("AUTH_MODE=dev: the client supplies its own line_user_id. Not for production.")

    @app.middleware("http")
    async def protect_ops_dash(request: Request, call_next):
        """保護 Python Dash 路徑（/ops/dash/*），須持有有效的管理員簽章 Cookie 方可存取。"""
        path = request.url.path
        if path == "/ops/dash" or path.startswith("/ops/dash/"):
            current = get_settings()
            if not current.ops_api_key:
                return JSONResponse(status_code=503, content={"error": "ops_disabled", "message": "審核後台尚未啟用（未設定 OPS_API_KEY）"})
            if not verify_dash_cookie(request.cookies.get(DASH_COOKIE_NAME)):
                accept = request.headers.get("accept", "")
                if "text/html" in accept:
                    login_url = f"{current.frontend_url.rstrip('/')}/ops/login?next=/ops/analytics"
                    return HTMLResponse(
                        status_code=401,
                        content=(
                            "<!doctype html><html lang='zh-Hant'><meta charset='utf-8'/>"
                            "<body style='font-family:sans-serif;background:#fffbf7;color:#1e293b;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;'>"
                            "<div style='background:#fff;border:1.5px solid #eadfd5;border-radius:18px;padding:28px;max-width:420px;text-align:center;'>"
                            "<h2 style='margin:0 0 8px;'>需要管理員登入</h2>"
                            "<p style='color:#64748b;font-size:14px;margin:0 0 18px;'>請先登入揪呷審核後台，才能檢視 Python Dash 數據分析儀表板。</p>"
                            f"<a href='{login_url}' target='_top' style='display:inline-block;background:#ff6b35;color:#fff;text-decoration:none;font-weight:700;padding:10px 20px;border-radius:12px;'>前往管理員登入</a>"
                            "</div></body></html>"
                        ),
                    )
                return JSONResponse(status_code=401, content={"error": "dash_unauthorized", "message": "請先登入審核後台"})
        return await call_next(request)

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
    app.include_router(ops_public_router)
    app.include_router(merchant_router)
    app.mount("/ops/dash", WSGIMiddleware(dash_app.server))
    return app


app = create_app()
