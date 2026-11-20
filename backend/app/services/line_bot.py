"""LINE bot: a tiny command interface (no AI chat). Pure formatting + command routing; HTTP to LINE is isolated in `send_reply`.

Commands (group chat or 1:1):
  建立聚餐 [名稱] [N人]   create a dining session bound to this chat and reply with the LIFF link
  分享 / 連結            re-send the LIFF link
  進度                   who has filled what (counts only, never contents)
  推薦                   run the recommendation (when everyone is done)
  強制推薦               run it even if some members have not finished
  結果 / Top3            re-send the latest Top 3
  說明                   help
"""
from __future__ import annotations

import re
import uuid
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.product import DiningSession
from app.schemas.api import SessionCreate
from app.services import recommendations as rec
from app.services import sessions as sess

HELP = ("揪呷 JOEAT 指令：\n"
        "・建立聚餐 高中同學聚餐 3人\n・分享（再次取得填寫連結）\n・進度\n・推薦（全員填完後）\n・強制推薦（不等沒填完的人）\n・結果（再看一次 Top 3）\n\n"
        "每個人的限制只有自己看得到，結果只顯示群組層級的資訊。")
DISCLAIMER = "※ 推薦只依據目前蒐集到的資料；標示「資訊不足」代表無法確認、不代表安全。過敏或嚴格飲食請務必向店家確認。"


def liff_url(session_id: uuid.UUID) -> str:
    s = get_settings()
    base = f"https://liff.line.me/{s.liff_id}" if s.liff_id else s.frontend_url.rstrip("/")
    return f"{base}/s/{session_id}"


def source_key(event: dict) -> str | None:
    src = event.get("source", {})
    return src.get("groupId") or src.get("roomId") or src.get("userId")


def parse_command(text: str) -> tuple[str, dict[str, Any]]:
    t = text.strip()
    m = re.match(r"^建立聚餐\s*(.*)$", t)
    if m:
        rest = m.group(1).strip()
        size = None
        sm = re.search(r"(\d{1,2})\s*人$", rest)
        if sm:
            size = int(sm.group(1))
            rest = rest[: sm.start()].strip()
        return "create", {"title": rest or "聚餐", "party_size": size}
    if t in ("分享", "連結", "加入"):
        return "share", {}
    if t == "進度":
        return "progress", {}
    if t == "強制推薦":
        return "recommend", {"allow_partial": True}
    if t in ("推薦", "產生推薦"):
        return "recommend", {"allow_partial": False}
    if t in ("結果", "top3", "Top3", "TOP3"):
        return "result", {}
    if t in ("說明", "help", "幫助", "?", "？"):
        return "help", {}
    return "none", {}


def format_top3(title: str | None, data: dict) -> str:
    lines = [f"🍽 {title or '聚餐'} 推薦 Top {len(data['top3']) or 3}"]
    if not data["top3"]:
        lines.append("目前沒有符合所有硬限制的餐廳。")
        if data.get("strict_mode"):
            lines.append("有成員開啟了嚴格過敏模式：只推薦店家已確認的餐廳，目前沒有任何餐廳符合。")
    for it in data["top3"]:
        cuisines = "、".join(it["cuisines"]) or "料理類型未知"
        dist = f"{it['distance_m']}m" if it["distance_m"] is not None else "距離未知"
        lines.append(f"\n{it['rank']}. {it['name']}（{cuisines}）\n   總分 {it['score']['total']:g}｜{dist}")
        for r in it["reasons"][:2]:
            lines.append(f"   ・{r}")
        for d in it.get("declarations", [])[:2]:
            lines.append(f"   📝 {d['text']}")
        for w in [w for w in it["warnings"] if w["level"] in ("critical", "high")][:3]:
            lines.append(f"   ⚠ {w['text']}")
    lines.append(f"\n（候選 {data['pool_size']} 家，排除 {data['excluded_count']} 家）\n{DISCLAIMER}")
    return "\n".join(lines)


def format_progress(p: dict) -> str:
    lines = [f"已加入 {p['joined']} 人" + (f" / 預計 {p['party_size']} 人" if p["party_size"] else ""),
             f"硬限制：{p['constraints_done']}/{p['joined']}　偏好：{p['preferences_done']}/{p['joined']}"]
    lines += [f"{'✅' if x['constraints_done'] and x['preferences_done'] else '⏳'} {x['label']}" for x in p["participants"]]
    lines.append("可以輸入「推薦」了" if p["ready_for_recommendation"] else "等大家填完再輸入「推薦」，或輸入「強制推薦」")
    return "\n".join(lines)


def handle_text(db: Session, key: str, text: str) -> list[str]:
    """Returns the reply texts for one incoming message (may be empty)."""
    cmd, args = parse_command(text)
    if cmd == "none":
        return []
    if cmd == "help":
        return [HELP]
    if cmd == "create":
        if args["party_size"] is not None and not 2 <= args["party_size"] <= 20:
            return ["人數需介於 2 到 20 人。"]
        s = sess.create_session(db, SessionCreate(title=args["title"], party_size=args["party_size"], location_preset="yancheng_pu", line_group_id=key))
        return [f"已建立聚餐「{s.title}」（地點預設：{s.location_label}）\n請大家點連結填寫：\n{liff_url(s.session_id)}\n填完後輸入「推薦」。"]
    s = sess.latest_session_for_group(db, key)
    if s is None:
        return ["這裡還沒有進行中的聚餐。輸入「建立聚餐 名稱 N人」開始。"]
    if cmd == "share":
        return [f"「{s.title}」填寫連結：\n{liff_url(s.session_id)}"]
    if cmd == "progress":
        return [format_progress(sess.progress(db, s))]
    if cmd == "recommend":
        try:
            data = rec.run_recommendation(db, s.session_id, allow_partial=args["allow_partial"])
        except AppError as e:
            if e.code == "incomplete":
                return [f"還有 {e.extra['missing_count']} 人沒填完。等大家填完，或輸入「強制推薦」。"]
            return [e.message]
        return [format_top3(s.title, data)]
    if cmd == "result":
        try:
            return [format_top3(s.title, rec.get_recommendation(db, s.session_id))]
        except AppError:
            return ["還沒有推薦結果。填完後輸入「推薦」。"]
    return []


def send_reply(reply_token: str, texts: list[str]) -> dict:
    """Reply through the Messaging API, or only report what would be sent when running in dry-run / without a token."""
    settings = get_settings()
    messages = [{"type": "text", "text": t[:4900]} for t in texts][:5]
    if settings.line_dry_run or not settings.line_channel_access_token:
        return {"dry_run": True, "messages": messages}
    resp = httpx.post("https://api.line.me/v2/bot/message/reply", json={"replyToken": reply_token, "messages": messages},
                      headers={"Authorization": f"Bearer {settings.line_channel_access_token}"}, timeout=10)
    return {"dry_run": False, "status": resp.status_code}
