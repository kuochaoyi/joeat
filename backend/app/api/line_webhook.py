"""LINE Messaging API webhook:  POST /line/webhook  (set this URL in the LINE Developers console)."""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import verify_line_signature
from app.services import line_bot

router = APIRouter()


@router.post("/line/webhook")
async def line_webhook(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    body = await request.body()
    if not settings.line_skip_signature:
        if not settings.line_channel_secret:
            raise HTTPException(503, "LINE channel secret is not configured")
        if not verify_line_signature(body, request.headers.get("x-line-signature", ""), settings.line_channel_secret):
            raise HTTPException(403, "invalid signature")
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "invalid JSON")
    outcomes = []
    for event in payload.get("events", []):
        key = line_bot.source_key(event)
        token = event.get("replyToken")
        if not key or not token:
            continue
        if event.get("type") == "join":
            texts = [line_bot.HELP]
        elif event.get("type") == "message" and event.get("message", {}).get("type") == "text":
            texts = line_bot.handle_text(db, key, event["message"]["text"])
        else:
            continue
        if texts:
            outcomes.append(line_bot.send_reply(token, texts))
    return {"handled": len(outcomes), "results": outcomes if settings.line_dry_run else []}
