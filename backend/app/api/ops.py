"""Operator / reviewer API for merchant declarations (/ops/*). See docs/decisions/0001-merchant-declaration.md.

Auth: header X-Ops-Key (shared key from OPS_API_KEY; the API answers 503 while it is not configured) and X-Ops-User (a name, recorded in the audit trail).
This is a pilot-grade gate for a few operators, not user management: the name is self-asserted.
"""
from __future__ import annotations

import hmac
import uuid
from typing import Literal
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.errors import AppError
from app.services import merchant as svc
from app.services import reports as reports_svc

CLAIMANT_ROLES = Literal["owner", "manager", "staff"]


def require_ops(x_ops_key: str | None = Header(default=None), x_ops_user: str | None = Header(default=None)) -> str:
    key = get_settings().ops_api_key
    if not key:
        raise AppError(503, "ops_disabled", "the reviewer API is disabled (OPS_API_KEY is not set)")
    if not x_ops_key or not hmac.compare_digest(x_ops_key.encode(), key.encode()):
        raise AppError(401, "bad_ops_key", "missing or wrong X-Ops-Key")
    # HTTP headers are ASCII: browsers send the name percent-encoded (so Chinese names work); plain ASCII passes through unchanged.
    user = unquote(x_ops_user or "").strip()
    if len(user) < 2:
        raise AppError(400, "ops_user_required", "X-Ops-User (your name, for the audit trail) is required")
    return user


router = APIRouter(prefix="/ops", tags=["ops"], dependencies=[Depends(require_ops)])


class ClaimCreate(BaseModel):
    restaurant_id: uuid.UUID
    is_demo: bool = Field(default=False, description="DEMO claim: its declarations publish FAKE evidence into the hidden test source. Refused unless ALLOW_TEST_EVIDENCE=true.")


class VerifyIn(BaseModel):
    method: Literal["phone_callback", "onsite_visit", "official_menu_review", "official_channel_message"]
    note: str = Field(min_length=5, max_length=1000, description="what was actually done: who answered / what was seen / which menu was reviewed")
    claimant_role: CLAIMANT_ROLES | None = None


class PublishIn(BaseModel):
    supersede: bool = False


class ReviewIn(BaseModel):
    note: str = Field(min_length=5, max_length=1000)


class IncidentCreate(BaseModel):
    restaurant_id: uuid.UUID
    severity: Literal["allergic_reaction", "wrong_info", "other"]
    attribute_code: str | None = None
    description: str | None = Field(default=None, max_length=2000)


class ResolveIn(BaseModel):
    outcome: Literal["confirmed", "dismissed"]


# ------------------------------------------------------------------ claims
@router.post("/claims", status_code=201)
def create_claim(body: ClaimCreate, user: str = Depends(require_ops), db: Session = Depends(get_db)):
    """Creates an invitation. The raw token is returned ONCE; only its SHA-256 is stored."""
    return svc.create_claim(db, user, body.restaurant_id, body.is_demo)


@router.get("/claims")
def list_claims(status: Literal["invited", "verified", "revoked", "expired"] | None = Query(None), restaurant_id: uuid.UUID | None = Query(None), db: Session = Depends(get_db)):
    return {"claims": svc.list_claims(db, status, restaurant_id)}


@router.get("/restaurants")
def search_restaurants(q: str | None = Query(None, max_length=50), db: Session = Depends(get_db)):
    """Find the restaurant to invite (any pool status)."""
    return {"restaurants": svc.search_restaurants(db, q)}


@router.get("/claims/{claim_id}")
def get_claim(claim_id: int, db: Session = Depends(get_db)):
    return svc.get_claim(db, claim_id)


@router.post("/claims/{claim_id}/verify")
def verify_claim(claim_id: int, body: VerifyIn, user: str = Depends(require_ops), db: Session = Depends(get_db)):
    """Records HOW this claimant was verified. The verification level follows from the method: callback / visit / reviewed menu = strong; channel message = basic."""
    return svc.verify_claim(db, user, claim_id, body.method, body.note, body.claimant_role)


@router.post("/claims/{claim_id}/revoke")
def revoke_claim(claim_id: int, user: str = Depends(require_ops), db: Session = Depends(get_db)):
    return svc.revoke_claim(db, user, claim_id)


# ------------------------------------------------------------------ declarations
@router.get("/declarations")
def list_declarations(status: Literal["draft", "submitted", "needs_info", "approved", "rejected", "withdrawn"] | None = Query(None), db: Session = Depends(get_db)):
    return {"declarations": svc.list_declarations(db, status)}


@router.get("/declarations/{declaration_id}")
def get_declaration(declaration_id: int, db: Session = Depends(get_db)):
    """Everything a reviewer needs: claim and how it was verified, every answer, what publishing WOULD write (new state, basis, confidence), the contradictions, the audit trail."""
    return svc.declaration_detail(db, declaration_id)


@router.post("/declarations/{declaration_id}/publish")
def publish_declaration(declaration_id: int, body: PublishIn | None = None, user: str = Depends(require_ops), db: Session = Depends(get_db)):
    """Approves and writes first-party evidence. A contradiction with LIKELY_* evidence blocks it unless `supersede` is true; with CONFIRMED_* evidence it always blocks."""
    n = svc.publish(db, user, declaration_id, bool(body and body.supersede))
    return {"published_evidence": n, "declaration": svc.declaration_detail(db, declaration_id)["declaration"]}


@router.post("/declarations/{declaration_id}/reject")
def reject_declaration(declaration_id: int, body: ReviewIn, user: str = Depends(require_ops), db: Session = Depends(get_db)):
    svc.review(db, user, declaration_id, "rejected", body.note)
    return svc.declaration_detail(db, declaration_id)["declaration"]


@router.post("/declarations/{declaration_id}/needs-info")
def request_info(declaration_id: int, body: ReviewIn, user: str = Depends(require_ops), db: Session = Depends(get_db)):
    svc.review(db, user, declaration_id, "needs_info", body.note)
    return svc.declaration_detail(db, declaration_id)["declaration"]


@router.post("/declarations/{declaration_id}/withdraw")
def withdraw_declaration(declaration_id: int, body: ReviewIn, user: str = Depends(require_ops), db: Session = Depends(get_db)):
    """Takes a PUBLISHED declaration down (menu changed / the merchant asked / trust lost). 'No X' claims stop counting at once; 'contains X' risk claims stay until they expire."""
    n = svc.withdraw(db, user, declaration_id, body.note)
    return {"positive_claims_retired": n, "declaration": svc.declaration_detail(db, declaration_id)["declaration"]}


# ------------------------------------------------------------------ incidents (kill switch)
@router.post("/incidents", status_code=201)
def create_incident(body: IncidentCreate, user: str = Depends(require_ops), db: Session = Depends(get_db)):
    """Logging a reaction / wrong-info report suspends the restaurant's POSITIVE claims immediately (see the design doc, section 8)."""
    return svc.create_incident(db, user, body.restaurant_id, body.severity, body.attribute_code, body.description)


@router.get("/incidents")
def list_incidents(status: Literal["open", "confirmed", "dismissed"] | None = Query(None), db: Session = Depends(get_db)):
    return {"incidents": svc.list_incidents(db, status)}


@router.post("/incidents/{incident_id}/resolve")
def resolve_incident(incident_id: int, body: ResolveIn, user: str = Depends(require_ops), db: Session = Depends(get_db)):
    return svc.resolve_incident(db, user, incident_id, body.outcome)


# ------------------------------------------------------------------ user reports ("report a mistake")
@router.get("/reports")
def list_reports(status: Literal["open", "dismissed", "escalated"] | None = Query(None), db: Session = Depends(get_db)):
    """The reporter is never included. A report changes nothing until a reviewer escalates it."""
    return {"reports": reports_svc.list_reports(db, status)}


@router.post("/reports/{report_id}/dismiss")
def dismiss_report(report_id: int, body: ReviewIn, user: str = Depends(require_ops), db: Session = Depends(get_db)):
    return reports_svc.dismiss_report(db, user, report_id, body.note)


@router.post("/reports/{report_id}/escalate")
def escalate_report(report_id: int, body: ReviewIn, user: str = Depends(require_ops), db: Session = Depends(get_db)):
    """Creates a merchant incident from the report (allergic_reaction / wrong_info suspend the restaurant's positive claims immediately)."""
    return reports_svc.escalate_report(db, user, report_id, body.note)
