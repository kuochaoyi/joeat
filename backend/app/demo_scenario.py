"""The fixed demo: 「高中同學聚餐」 with three friends, driven entirely through the public REST API.

  A: no beef, prefers Japanese        B: peanut allergy, prefers hotpot        C: "I'm fine with anything"

`client` is anything with .post/.get returning objects that have .status_code and .json() (httpx.Client or FastAPI's TestClient).
"""
from __future__ import annotations

from typing import Any

CUISINES = ["台式", "中式", "日式", "韓式", "火鍋", "燒肉", "熱炒", "小吃", "義式", "美式", "東南亞", "印度料理", "甜點", "咖啡廳"]


def _ok(resp, expected=(200, 201)) -> Any:
    if resp.status_code not in expected:
        raise RuntimeError(f"{resp.request.method} {resp.request.url} -> {resp.status_code}: {resp.text}")
    return resp.json()


def run_demo(client, user_prefix: str = "demo", include_excluded: bool = True) -> dict:
    session = _ok(client.post("/sessions", json={
        "title": "高中同學聚餐", "date": "2026-11-14", "time": "18:30", "location_preset": "yancheng_pu", "party_size": 3}))
    sid = session["session_id"]

    def join(label: str) -> str:
        return _ok(client.post(f"/sessions/{sid}/participants", json={"line_user_id": f"{user_prefix}-{label}", "label": label}))["participant_id"]

    a, b, c = join("A"), join("B"), join("C")

    _ok(client.post(f"/participants/{a}/constraints", json={"items": [{"attribute_code": "beef"}]}))
    _ok(client.post(f"/participants/{a}/preferences", json={"items": [{"cuisine_tag": "日式", "stance": "love"}]}))
    _ok(client.post(f"/participants/{b}/constraints", json={"items": [{"attribute_code": "peanut", "reason": "allergy"}]}))
    _ok(client.post(f"/participants/{b}/preferences", json={"items": [{"cuisine_tag": "火鍋", "stance": "love"}]}))
    _ok(client.post(f"/participants/{c}/constraints", json={"items": []}))                                   # nothing to declare
    _ok(client.post(f"/participants/{c}/preferences", json={"items": [{"cuisine_tag": t, "stance": "any"} for t in CUISINES]}))   # 我都好

    progress = _ok(client.get(f"/sessions/{sid}/progress"))
    result = _ok(client.post(f"/sessions/{sid}/recommendations", params={"include_excluded": str(include_excluded).lower()}))
    return {"session": session, "participants": {"A": a, "B": b, "C": c}, "progress": progress, "result": result}


def render(demo: dict) -> str:
    r = demo["result"]
    out = [f"聚餐：{demo['session']['title']}　地點：{demo['session']['location_label']}　成員 {r['participants']} 人",
           f"候選 {r['pool_size']} 家 → 排除 {r['excluded_count']} 家 → 可推薦 {r['eligible_count']} 家", ""]
    for it in r["top3"]:
        sc = it["score"]
        dist = f"{it['distance_m']} m" if it["distance_m"] is not None else "距離未知"
        out.append(f"#{it['rank']} {it['name']}（{'、'.join(it['cuisines']) or '類型未知'}）  {dist}")
        out.append(f"    分數：料理 {sc['cuisine']:g} + 距離 {sc['distance']:g} + 資料可信度 {sc['data_confidence']:g} = {sc['total']:g}")
        out.append(f"    硬限制：{it['hard_constraint']['note']}")
        for reason in it["reasons"]:
            out.append(f"    ・{reason}")
        for w in it["warnings"]:
            out.append(f"    {'⚠' if w['level'] in ('critical', 'high') else '·'} [{w['level']}] {w['text']}")
        out.append("")
    if r.get("excluded"):
        out.append("被排除的餐廳（硬限制）：")
        out += [f"  ✗ {e['name']}：{'；'.join(e['reasons'])}" for e in r["excluded"]]
    out.append("")
    out.append(r["disclaimer"])
    return "\n".join(out)
