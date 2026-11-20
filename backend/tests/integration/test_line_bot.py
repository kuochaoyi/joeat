import base64
import hashlib
import hmac
import json
import os
import re

import pytest
from sqlalchemy import text

from app.core.security import hash_ref, verify_line_signature
from app.services.line_bot import format_progress, format_top3, parse_command


# ------------------------------------------------------------------ pure logic (no database)
@pytest.mark.parametrize("text_in,expected", [
    ("建立聚餐 高中同學聚餐 3人", ("create", {"title": "高中同學聚餐", "party_size": 3})),
    ("建立聚餐", ("create", {"title": "聚餐", "party_size": None})),
    ("建立聚餐 火鍋之夜", ("create", {"title": "火鍋之夜", "party_size": None})),
    ("分享", ("share", {})), ("進度", ("progress", {})), ("推薦", ("recommend", {"allow_partial": False})),
    ("強制推薦", ("recommend", {"allow_partial": True})), ("結果", ("result", {})), ("說明", ("help", {})), ("今天吃什麼", ("none", {})),
])
def test_parse_command(text_in, expected):
    assert parse_command(text_in) == expected


def test_signature_roundtrip():
    body = b'{"events":[]}'
    sig = base64.b64encode(hmac.new(b"secret", body, hashlib.sha256).digest()).decode()
    assert verify_line_signature(body, sig, "secret") and not verify_line_signature(body, sig, "other") and not verify_line_signature(body, "", "secret")


def test_hash_is_stable_and_not_the_raw_id():
    assert hash_ref("Uabc") == hash_ref("Uabc") != hash_ref("Uabd") and "Uabc" not in hash_ref("Uabc") and len(hash_ref("Uabc")) == 64


def test_top3_text_never_claims_safety():
    data = {"pool_size": 5, "excluded_count": 1, "top3": [{"rank": 1, "name": "鴨肉珍", "cuisines": ["台式"], "distance_m": 300, "score": {"total": 5},
                                                          "reasons": ["1/3 人偏好台式"], "warnings": [{"level": "critical", "text": "花生資訊不足，建議向店家確認"}]}]}
    out = format_progress  # noqa: F841 - imported for coverage of the module
    txt = format_top3("聚餐", data)
    assert "花生資訊不足" in txt and "不代表安全" in txt and "確認不含" not in txt


# ------------------------------------------------------------------ webhook (database + app)
def _event(text_msg, group="Cgroup1", user="Uuser1", token="rtok"):
    return {"events": [{"type": "message", "replyToken": token, "source": {"type": "group", "groupId": group, "userId": user}, "message": {"type": "text", "text": text_msg}}]}


@pytest.fixture()
def line_env(database_url, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setenv("LINE_SKIP_SIGNATURE", "true")
    monkeypatch.setenv("LINE_DRY_RUN", "true")
    monkeypatch.setenv("LINE_CHANNEL_SECRET", "")
    monkeypatch.setenv("FRONTEND_URL", "http://liff.test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def say(client, msg, **kw):
    r = client.post("/line/webhook", json=_event(msg, **kw))
    assert r.status_code == 200
    return [m["text"] for res in r.json()["results"] for m in res["messages"]]


@pytest.mark.integration
def test_signature_is_enforced(database_url, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.main import create_app
    monkeypatch.setenv("LINE_SKIP_SIGNATURE", "false")
    monkeypatch.setenv("LINE_CHANNEL_SECRET", "topsecret")
    get_settings.cache_clear()
    try:
        c = TestClient(create_app())
        body = json.dumps(_event("說明")).encode()
        assert c.post("/line/webhook", content=body, headers={"x-line-signature": "bad"}).status_code == 403
        good = base64.b64encode(hmac.new(b"topsecret", body, hashlib.sha256).digest()).decode()
        r = c.post("/line/webhook", content=body, headers={"x-line-signature": good})
        assert r.status_code == 200 and r.json()["handled"] == 1
        monkeypatch.setenv("LINE_CHANNEL_SECRET", "")
        get_settings.cache_clear()
        assert c.post("/line/webhook", content=body, headers={"x-line-signature": good}).status_code == 503
    finally:
        get_settings.cache_clear()


@pytest.mark.integration
def test_group_flow_create_share_progress_recommend(client, db, line_env, uniq):
    group = "C" + uniq
    assert say(client, "今天吃什麼", group=group) == []                                   # not a command: silent
    assert "還沒有進行中的聚餐" in say(client, "進度", group=group)[0]
    created = say(client, "建立聚餐 高中同學聚餐 2人", group=group)[0]
    sid = re.search(r"/s/([0-9a-f-]{36})", created).group(1)
    assert created.count("http://liff.test/s/") == 1 and "高中同學聚餐" in created
    stored = db.scalar(text("SELECT line_group_ref FROM product.dining_session WHERE session_id = :s"), {"s": sid})
    assert stored == hash_ref(group) and group not in stored
    assert sid in say(client, "分享", group=group)[0]
    assert "已加入 0 人" in say(client, "進度", group=group)[0]

    for who in ("a", "b"):
        pid = client.post(f"/sessions/{sid}/participants", json={"line_user_id": f"{uniq}-{who}", "label": who}).json()["participant_id"]
        if who == "a":
            client.post(f"/participants/{pid}/constraints", json={"items": [{"attribute_code": "peanut"}]})
            client.post(f"/participants/{pid}/preferences", json={"items": [{"cuisine_tag": "台式", "stance": "love"}]})
            assert "還有" in say(client, "推薦", group=group)[0] or "沒填完" in say(client, "推薦", group=group)[0]
        else:
            client.post(f"/participants/{pid}/constraints", json={"items": []})
            client.post(f"/participants/{pid}/preferences", json={"items": []})
    prog = say(client, "進度", group=group)[0]
    assert "硬限制：2/2" in prog and "可以輸入「推薦」" in prog
    top = say(client, "推薦", group=group)[0]
    assert "推薦 Top 3" in top and "花生資訊不足" in top and "不代表安全" in top
    assert say(client, "結果", group=group)[0] == top
    assert "建立聚餐" in say(client, "說明", group=group)[0]


@pytest.mark.integration
def test_invalid_party_size_and_force_recommend(client, line_env, uniq):
    group = "C" + uniq
    assert "2 到 20" in say(client, "建立聚餐 太多人 21人", group=group)[0]
    assert "已建立聚餐" in say(client, "建立聚餐 大聚會 15人", group="C-big-" + uniq)[0]      # 11-20 people are fine now
    sid = re.search(r"/s/([0-9a-f-]{36})", say(client, "建立聚餐 小聚", group=group)[0]).group(1)
    pid = client.post(f"/sessions/{sid}/participants", json={"line_user_id": uniq}).json()["participant_id"]
    client.post(f"/participants/{pid}/constraints", json={"items": []})
    assert "沒填完" in say(client, "推薦", group=group)[0]
    assert "推薦 Top 3" in say(client, "強制推薦", group=group)[0]


@pytest.mark.integration
def test_one_to_one_chat_and_join_event(client, line_env, uniq):
    user = "U" + uniq
    ev = {"events": [{"type": "message", "replyToken": "t", "source": {"type": "user", "userId": user}, "message": {"type": "text", "text": "建立聚餐 兩人"}}]}
    r = client.post("/line/webhook", json=ev).json()
    assert r["handled"] == 1 and "已建立聚餐" in r["results"][0]["messages"][0]["text"]
    join = {"events": [{"type": "join", "replyToken": "t2", "source": {"type": "group", "groupId": "C" + uniq}}]}
    assert "揪呷 JOEAT 指令" in client.post("/line/webhook", json=join).json()["results"][0]["messages"][0]["text"]
    assert os.environ.get("LINE_DRY_RUN") == "true"
