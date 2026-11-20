"""Python Dash 存取保護與簽章 Cookie 單元測試（無須資料庫）。"""
from fastapi.testclient import TestClient

from app.api.ops import DASH_COOKIE_NAME, sign_dash_cookie, verify_dash_cookie
from app.core.config import get_settings
from app.main import create_app


def test_dash_cookie_sign_and_verify(monkeypatch):
    monkeypatch.setenv("OPS_API_KEY", "unit-test-ops-key")
    get_settings.cache_clear()
    try:
        token = sign_dash_cookie("審核員小明")
        assert verify_dash_cookie(token) == "審核員小明"
        # 竄改簽章應失敗
        assert verify_dash_cookie(token + "x") is None
        # 過期應失敗
        expired = sign_dash_cookie("審核員小明", ttl_seconds=-10)
        assert verify_dash_cookie(expired) is None
        # 更換 OPS_API_KEY 後舊權杖應立即失效
        monkeypatch.setenv("OPS_API_KEY", "rotated-ops-key")
        get_settings.cache_clear()
        assert verify_dash_cookie(token) is None
    finally:
        monkeypatch.delenv("OPS_API_KEY", raising=False)
        get_settings.cache_clear()


def test_dash_mount_requires_valid_cookie(monkeypatch):
    monkeypatch.setenv("OPS_API_KEY", "unit-test-ops-key")
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        # 未登入存取 /ops/dash/ 應回傳 401
        res_unauth = client.get("/ops/dash/", headers={"Accept": "text/html"})
        assert res_unauth.status_code == 401
        assert "需要管理員登入" in res_unauth.text

        # 以正確標頭換取 Dash Cookie
        res_session = client.post(
            "/ops/dash-session",
            headers={"X-Ops-Key": "unit-test-ops-key", "X-Ops-User": "%E5%AF%A9%E6%A0%B8%E5%93%A1%E5%B0%8F%E6%98%8E"},
        )
        assert res_session.status_code == 200
        assert res_session.json()["user"] == "審核員小明"
        assert DASH_COOKIE_NAME in res_session.cookies

        # 帶有效 Cookie 應能存取 Python Dash 頁面與版面 JSON
        res_dash = client.get("/ops/dash/")
        assert res_dash.status_code == 200
        assert "揪呷 JOEAT" in res_dash.text

        res_layout = client.get("/ops/dash/_dash-layout")
        assert res_layout.status_code == 200

        # 登出後應清除 Cookie 並再次被阻擋
        res_logout = client.post("/ops/dash-logout")
        assert res_logout.status_code == 200
        assert client.get("/ops/dash/").status_code == 401
    finally:
        monkeypatch.delenv("OPS_API_KEY", raising=False)
        get_settings.cache_clear()
