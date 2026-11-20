"""Merchant-facing API (/merchant/*), entered with the invitation token:  X-Claim-Token: <token>.

The token only says WHO is asking (which claim). It does not make anything true: a declaration still needs a verified claim, a named reviewer
and the database rules before it becomes evidence. There is no rate limiting yet (tracked in the decision record).
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core import merchant_form as form
from app.core.errors import AppError
from app.services import merchant as svc

router = APIRouter(prefix="/merchant", tags=["merchant"])

Answer = Literal["absent_entire_menu", "present_in_some_dishes", "present_in_most_dishes", "offered", "not_offered", "not_sure"]
CrossContact = Literal["confirmed_none", "possible", "confirmed_shared", "unknown"]


class ItemIn(BaseModel):
    attribute_code: str
    answer: Answer = "not_sure"
    cross_contact_status: CrossContact = "unknown"
    note: str | None = Field(default=None, max_length=300)
    certificate_ref: str | None = Field(default=None, max_length=100)


class ItemsIn(BaseModel):
    items: list[ItemIn] = Field(max_length=40)


class MenuIn(BaseModel):
    menu_url: str | None = Field(default=None, max_length=500, pattern=r"^https?://")


class SubmitIn(BaseModel):
    role: Literal["owner", "manager", "staff"]
    menu_as_of: date
    accepted: bool
    attestation_version: str


def current_claim(x_claim_token: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    if not x_claim_token:
        raise AppError(401, "token_required", "X-Claim-Token is required")
    return svc.claim_by_token(db, x_claim_token)


def _attrs(db: Session) -> dict[str, dict]:
    return {r.attribute_code: {"attribute_type": r.attribute_type, "risk_level": r.risk_level}
            for r in db.execute(text("SELECT attribute_code, attribute_type, risk_level FROM ref.attribute WHERE is_active"))}


@router.get("/form-spec")
def form_spec(db: Session = Depends(get_db)):
    """The questions, the answer options and the attestation text (a legal-review placeholder). No token needed."""
    return form.form_spec(_attrs(db))


@router.get("/me")
def me(claim: dict = Depends(current_claim), db: Session = Depends(get_db)):
    d = svc.current_declaration_id(db, claim["claim_id"])
    return {
        "restaurant": {"name": claim["canonical_name"], "address": claim["canonical_address"], "phone": claim["phone"]},
        "claim_status": claim["status"], "can_declare": claim["status"] == "verified", "demo": claim["is_demo"], "claimant_role": claim["claimant_role"],
        "declaration": svc.merchant_declaration_view(db, d) if d else None,
        "message": None if claim["status"] == "verified" else "我們的團隊會先與您聯絡確認身分，完成後您就可以填寫。",
    }


def _require_verified(claim: dict) -> None:
    if claim["status"] != "verified":
        raise AppError(409, "not_verified", "this claim has not been verified yet")


@router.post("/declaration", status_code=201)
def start(claim: dict = Depends(current_claim), db: Session = Depends(get_db)):
    """Starts a declaration (all 17 answers = not_sure), or returns the one that is already open."""
    _require_verified(claim)
    d = svc.current_declaration_id(db, claim["claim_id"])
    if d is None or svc.merchant_declaration_view(db, d)["status"] == "approved":
        d = svc.start_declaration(db, f"merchant:{claim['claim_id']}", claim["claim_id"])
    return svc.merchant_declaration_view(db, d)


@router.get("/declaration")
def current(claim: dict = Depends(current_claim), db: Session = Depends(get_db)):
    d = svc.current_declaration_id(db, claim["claim_id"])
    if d is None:
        raise AppError(404, "not_found", "no declaration yet")
    return svc.merchant_declaration_view(db, d)


def _open_declaration(claim: dict, db: Session) -> int:
    _require_verified(claim)
    d = svc.current_declaration_id(db, claim["claim_id"])
    if d is None:
        raise AppError(404, "not_found", "no declaration yet; start one first")
    if not svc.merchant_declaration_view(db, d)["editable"]:
        raise AppError(409, "rule_violation", "this declaration has been submitted and can no longer be edited")
    return d


@router.put("/declaration/items")
def save_items(body: ItemsIn, claim: dict = Depends(current_claim), db: Session = Depends(get_db)):
    """Autosave: replaces the given items. Allowed only while the declaration is a draft or was sent back for more information."""
    d = _open_declaration(claim, db)
    n = svc.set_items_bulk(db, f"merchant:{claim['claim_id']}", d, [i.model_dump() for i in body.items])
    return {"saved": n}


@router.put("/declaration/menu")
def save_menu(body: MenuIn, claim: dict = Depends(current_claim), db: Session = Depends(get_db)):
    d = _open_declaration(claim, db)
    svc.update_menu(db, f"merchant:{claim['claim_id']}", d, body.menu_url)
    return {"menu_url": body.menu_url}


@router.get("/declaration/preview")
def preview(claim: dict = Depends(current_claim), db: Session = Depends(get_db)):
    """What customers will see, and how each answer will count. Same function the reviewer's publish uses (merchant.declaration_plan)."""
    d = svc.current_declaration_id(db, claim["claim_id"])
    if d is None:
        raise AppError(404, "not_found", "no declaration yet")
    today = db.execute(text("SELECT ref.today_tpe()")).scalar()
    rows = svc.plan_rows(db, d)
    lines = [form.describe(r, today) for r in rows]
    return {
        "lines": lines, "unanswered_note": "沒有回答的項目（「我不確定」）不會顯示任何聲明，顧客會看到「資訊不足」。",
        "counts": {k: sum(1 for x in lines if x["effect"] == k) for k in ("confirmed", "possible", "contains")},
        "verification_note": "是否列為「已確認」取決於我們對您身分的驗證方式與共用設備的回答。", "demo": claim["is_demo"],
    }


@router.post("/declaration/submit")
def submit(body: SubmitIn, claim: dict = Depends(current_claim), db: Session = Depends(get_db)):
    d = _open_declaration(claim, db)
    if not body.accepted:
        raise AppError(422, "attestation_required", "you must accept the attestation to submit")
    if body.attestation_version != form.ATTESTATION_VERSION:
        raise AppError(409, "attestation_outdated", "the attestation text has changed; reload the form")
    svc.submit_declaration(db, f"merchant:{claim['claim_id']}", d, body.role, body.menu_as_of, body.attestation_version)
    return svc.merchant_declaration_view(db, d)
