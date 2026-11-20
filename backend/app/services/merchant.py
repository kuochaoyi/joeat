"""Merchant self-declaration: claims, declarations, review, incidents.

The rules live in the database (migration 0003): this module calls the SQL functions and turns their rule violations into API errors.
Nothing here writes evidence directly: only merchant.publish_declaration() may turn a declaration into first-party evidence.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, not_found

STRONG_METHODS = {"phone_callback", "onsite_visit", "official_menu_review"}
BASIC_METHODS = {"official_channel_message"}
SQL_RULE_STATES = {"23514", "23503", "23505", "P0001"}      # check / foreign key / unique violations and plain RAISE EXCEPTION


def _actor(db: Session, actor: str) -> None:
    db.execute(text("SELECT set_config('joeat.actor', :a, true)"), {"a": actor})


def run(db: Session, actor: str, fn):
    """Runs fn() in one transaction with the audit actor set; database rule violations become 409 `rule_violation`."""
    try:
        _actor(db, actor)
        out = fn()
        db.commit()
        return out
    except (DBAPIError, IntegrityError) as e:
        db.rollback()
        orig = getattr(e, "orig", None)
        if getattr(orig, "sqlstate", None) in SQL_RULE_STATES:
            msg = getattr(getattr(orig, "diag", None), "message_primary", None) or str(orig).splitlines()[0]
            raise AppError(409, "rule_violation", msg) from e
        raise


# ---------------------------------------------------------------- claims
def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_claim(db: Session, actor: str, restaurant_id: uuid.UUID, is_demo: bool = False) -> dict:
    if db.execute(text("SELECT 1 FROM identity.restaurant WHERE restaurant_id = :r"), {"r": restaurant_id}).first() is None:
        raise not_found("restaurant")
    if is_demo and not get_settings().allow_test_evidence:
        raise AppError(409, "demo_disabled", "demo claims need ALLOW_TEST_EVIDENCE=true (they publish fake evidence into the hidden test source); never enable it in production")
    token = secrets.token_urlsafe(24)
    row = run(db, actor, lambda: db.execute(text(
        "INSERT INTO merchant.claim (restaurant_id, token_hash, invited_by, is_demo) VALUES (:r, :h, :a, :d) RETURNING claim_id, expires_at"),
        {"r": restaurant_id, "h": hash_token(token), "a": actor, "d": is_demo}).one())
    return {"claim_id": row.claim_id, "restaurant_id": restaurant_id, "status": "invited", "is_demo": is_demo, "expires_at": row.expires_at,
            "token": token, "token_note": "shown once; only its SHA-256 is stored"}


def list_claims(db: Session, status: str | None, restaurant_id: uuid.UUID | None) -> list[dict]:
    rows = db.execute(text(
        "SELECT c.claim_id, c.restaurant_id, r.canonical_name AS restaurant, c.status, c.is_demo, c.verification_method, c.verification_level, c.verified_by, c.verified_at, c.invited_by, c.invited_at, c.expires_at "
        "FROM merchant.claim c JOIN identity.restaurant r USING (restaurant_id) "
        "WHERE (CAST(:s AS TEXT) IS NULL OR c.status = :s) AND (CAST(:r AS UUID) IS NULL OR c.restaurant_id = :r) ORDER BY c.claim_id DESC"), {"s": status, "r": restaurant_id}).mappings().all()
    return [dict(r) for r in rows]


def search_restaurants(db: Session, q: str | None) -> list[dict]:
    rows = db.execute(text(
        "SELECT restaurant_id, canonical_name, canonical_address, phone, pool_status, active_status FROM identity.restaurant "
        "WHERE merged_into_restaurant_id IS NULL AND (CAST(:q AS TEXT) IS NULL OR canonical_name ILIKE '%' || :q || '%') ORDER BY pool_status DESC, canonical_name LIMIT 50"), {"q": q or None}).mappings().all()
    return [dict(r) for r in rows]


def claim_by_token(db: Session, token: str) -> dict:
    """Merchant-side lookup. Unknown token -> generic 404 (no hint whether it ever existed); revoked / expired -> 410."""
    row = db.execute(text(
        "SELECT c.claim_id, c.restaurant_id, c.status, c.is_demo, c.claimant_role, c.expires_at, r.canonical_name, r.canonical_address, r.phone "
        "FROM merchant.claim c JOIN identity.restaurant r USING (restaurant_id) WHERE c.token_hash = :h"), {"h": hash_token(token)}).mappings().first()
    if row is None:
        raise AppError(404, "not_found", "this link is not valid")
    if row["status"] in ("revoked", "expired") or row["expires_at"] < datetime.now(timezone.utc):
        raise AppError(410, "claim_unavailable", "this invitation is no longer valid; please contact the JOEAT team")
    return dict(row)


def verify_claim(db: Session, actor: str, claim_id: int, method: str, note: str, claimant_role: str | None) -> dict:
    if method not in STRONG_METHODS | BASIC_METHODS:
        raise AppError(422, "unknown_method", f"method must be one of {sorted(STRONG_METHODS | BASIC_METHODS)}")
    level = "strong" if method in STRONG_METHODS else "basic"

    def go():
        row = db.execute(text("SELECT status FROM merchant.claim WHERE claim_id = :c FOR UPDATE"), {"c": claim_id}).first()
        if row is None:
            raise not_found("claim")
        if row.status != "invited":
            raise AppError(409, "rule_violation", f"claim is {row.status}; only an invited claim can be verified")
        db.execute(text(
            "UPDATE merchant.claim SET status = 'verified', verification_method = :m, verification_level = :l, verification_note = :n, verified_by = :a, "
            "verified_at = now(), claimant_role = :role WHERE claim_id = :c"), {"m": method, "l": level, "n": note, "a": actor, "role": claimant_role, "c": claim_id})
    run(db, actor, go)
    return get_claim(db, claim_id)


def revoke_claim(db: Session, actor: str, claim_id: int) -> dict:
    def go():
        n = db.execute(text("UPDATE merchant.claim SET status = 'revoked' WHERE claim_id = :c AND status IN ('invited','verified')"), {"c": claim_id}).rowcount
        if not n:
            raise AppError(409, "rule_violation", "only an invited or verified claim can be revoked") if db.execute(
                text("SELECT 1 FROM merchant.claim WHERE claim_id = :c"), {"c": claim_id}).first() else not_found("claim")
    run(db, actor, go)
    return get_claim(db, claim_id)


def get_claim(db: Session, claim_id: int) -> dict:
    row = db.execute(text(
        "SELECT claim_id, restaurant_id, status, is_demo, verification_method, verification_level, verification_note, verified_by, verified_at, claimant_role, invited_by, invited_at, expires_at "
        "FROM merchant.claim WHERE claim_id = :c"), {"c": claim_id}).mappings().first()
    if row is None:
        raise not_found("claim")
    return dict(row)


# ---------------------------------------------------------------- declarations (the merchant-facing endpoints come in the next step; these are the service calls they will use)
def start_declaration(db: Session, actor: str, claim_id: int, valid_days: int = 90) -> int:
    return run(db, actor, lambda: db.execute(text("SELECT merchant.start_declaration(:c, :v)"), {"c": claim_id, "v": valid_days}).scalar())


def set_item(db: Session, actor: str, declaration_id: int, attribute_code: str, answer: str, cross_contact_status: str = "unknown",
             note: str | None = None, certificate_ref: str | None = None) -> None:
    def go():
        n = db.execute(text(
            "UPDATE merchant.declaration_item SET answer = :a, cross_contact_status = :cc, note = :n, certificate_ref = :cert "
            "WHERE declaration_id = :d AND attribute_code = :attr"),
            {"a": answer, "cc": cross_contact_status, "n": note, "cert": certificate_ref, "d": declaration_id, "attr": attribute_code}).rowcount
        if not n:
            raise not_found("declaration item")
    run(db, actor, go)


def set_menu(db: Session, actor: str, declaration_id: int, menu_url: str | None, menu_file_ref: str | None = None) -> None:
    run(db, actor, lambda: db.execute(text("UPDATE merchant.declaration SET menu_url = :u, menu_file_ref = :f WHERE declaration_id = :d"),
                                      {"u": menu_url, "f": menu_file_ref, "d": declaration_id}))


def submit_declaration(db: Session, actor: str, declaration_id: int, role: str, menu_as_of: date, attestation_version: str) -> None:
    run(db, actor, lambda: db.execute(text("SELECT merchant.submit_declaration(:d, :r, :m, :v)"),
                                      {"d": declaration_id, "r": role, "m": menu_as_of, "v": attestation_version}))


# ---------------------------------------------------------------- review
def list_declarations(db: Session, status: str | None) -> list[dict]:
    rows = db.execute(text(
        "SELECT d.declaration_id, d.status, r.canonical_name AS restaurant, d.restaurant_id, d.submitted_at, d.menu_as_of, c.verification_level, c.verification_method, c.is_demo, "
        "       (SELECT count(*) FROM merchant.declaration_item i WHERE i.declaration_id = d.declaration_id AND i.answer <> 'not_sure') AS answered_items, "
        "       (SELECT count(*) FROM merchant.declaration_plan(d.declaration_id) p WHERE p.conflicts IS NOT NULL) AS conflict_count "
        "FROM merchant.declaration d JOIN merchant.claim c USING (claim_id) JOIN identity.restaurant r ON r.restaurant_id = d.restaurant_id "
        "WHERE (CAST(:s AS TEXT) IS NULL OR d.status = :s) ORDER BY d.submitted_at NULLS LAST, d.declaration_id"), {"s": status}).mappings().all()
    return [dict(r) for r in rows]


def declaration_detail(db: Session, declaration_id: int) -> dict:
    d = db.execute(text(
        "SELECT d.*, r.canonical_name AS restaurant, r.canonical_address, r.phone FROM merchant.declaration d JOIN identity.restaurant r USING (restaurant_id) WHERE d.declaration_id = :d"),
        {"d": declaration_id}).mappings().first()
    if d is None:
        raise not_found("declaration")
    claim = get_claim(db, d["claim_id"])
    items = [dict(x) for x in db.execute(text(
        "SELECT i.attribute_code, a.display_name_zh, a.attribute_type, a.risk_level, i.answer, i.cross_contact_status, i.note, i.certificate_ref "
        "FROM merchant.declaration_item i JOIN ref.attribute a USING (attribute_code) WHERE i.declaration_id = :d ORDER BY a.sort_order, i.attribute_code"), {"d": declaration_id}).mappings().all()]
    plan = [dict(x) for x in db.execute(text(
        "SELECT attribute_code, answer, cross_contact_status, new_state::text AS new_state, evidence_basis, confidence, presence_extent, capped_by_cross_contact, conflicts, conflicts_confirmed "
        "FROM merchant.declaration_plan(:d) ORDER BY attribute_code"), {"d": declaration_id}).mappings().all()]
    ids = sorted({i for p in plan for i in (p["conflicts"] or [])})
    conflicts = [dict(x) for x in db.execute(text(
        "SELECT e.evidence_id, e.attribute_code, e.state::text AS state, e.evidence_basis, e.confidence, e.evidence_text, e.source_url, s.source_type "
        "FROM enrichment.restaurant_attribute_evidence e JOIN ref.data_source s USING (source_id) WHERE e.evidence_id = ANY(:ids) ORDER BY e.evidence_id"), {"ids": ids}).mappings().all()] if ids else []
    audit = [dict(x) for x in db.execute(text("SELECT event, actor, at, detail FROM merchant.declaration_audit WHERE declaration_id = :d ORDER BY audit_id"), {"d": declaration_id}).mappings().all()]
    return {"declaration": dict(d), "claim": claim, "items": items, "plan": plan, "conflicts": conflicts, "audit": audit}


def publish(db: Session, actor: str, declaration_id: int, supersede: bool) -> int:
    return run(db, actor, lambda: db.execute(text("SELECT merchant.publish_declaration(:d, :a, :s)"), {"d": declaration_id, "a": actor, "s": supersede}).scalar())


def withdraw(db: Session, actor: str, declaration_id: int, note: str) -> int:
    """Takes a published declaration down. Returns how many positive claims stopped counting (risk claims stay until they expire)."""
    return run(db, actor, lambda: db.execute(text("SELECT merchant.withdraw_declaration(:d, :a, :n)"), {"d": declaration_id, "a": actor, "n": note}).scalar())


def review(db: Session, actor: str, declaration_id: int, outcome: str, note: str) -> None:
    run(db, actor, lambda: db.execute(text("SELECT merchant.review_declaration(:d, :o, :a, :n)"), {"d": declaration_id, "o": outcome, "a": actor, "n": note}))


# ---------------------------------------------------------------- incidents
def create_incident(db: Session, actor: str, restaurant_id: uuid.UUID, severity: str, attribute_code: str | None, description: str | None) -> dict:
    def go():
        return db.execute(text(
            "INSERT INTO merchant.incident_report (restaurant_id, attribute_code, severity, description) VALUES (:r, :a, :s, :d) RETURNING incident_id"),
            {"r": restaurant_id, "a": attribute_code, "s": severity, "d": description}).scalar()
    iid = run(db, actor, go)
    return get_incident(db, iid)


def get_incident(db: Session, incident_id: int) -> dict:
    row = db.execute(text("SELECT * FROM merchant.incident_report WHERE incident_id = :i"), {"i": incident_id}).mappings().first()
    if row is None:
        raise not_found("incident")
    suspended = db.execute(text("SELECT count(*) FROM enrichment.restaurant_attribute_evidence WHERE suspended_by_incident = :i"), {"i": incident_id}).scalar()
    return {**dict(row), "suspended_evidence_count": suspended}


def list_incidents(db: Session, status: str | None) -> list[dict]:
    rows = db.execute(text("SELECT incident_id FROM merchant.incident_report WHERE (CAST(:s AS TEXT) IS NULL OR status = :s) ORDER BY incident_id"), {"s": status}).scalars().all()
    return [get_incident(db, i) for i in rows]


def resolve_incident(db: Session, actor: str, incident_id: int, outcome: str) -> dict:
    get_incident(db, incident_id)
    run(db, actor, lambda: db.execute(text("SELECT merchant.resolve_incident(:i, :o, :a)"), {"i": incident_id, "o": outcome, "a": actor}))
    return get_incident(db, incident_id)


# ---------------------------------------------------------------- merchant-side helpers (used by /merchant/* with a claim token)
def current_declaration_id(db: Session, claim_id: int) -> int | None:
    """The declaration the merchant is working on / waiting for: newest of this claim that is not rejected or withdrawn."""
    return db.execute(text(
        "SELECT declaration_id FROM merchant.declaration WHERE claim_id = :c AND status NOT IN ('rejected','withdrawn') ORDER BY declaration_id DESC LIMIT 1"), {"c": claim_id}).scalar()


def merchant_declaration_view(db: Session, declaration_id: int) -> dict:
    d = db.execute(text(
        "SELECT declaration_id, status, valid_days, menu_as_of, menu_url, declared_role, attestation_version, submitted_at, review_note, reviewed_at "
        "FROM merchant.declaration WHERE declaration_id = :d"), {"d": declaration_id}).mappings().one()
    items = [dict(x) for x in db.execute(text(
        "SELECT attribute_code, answer, cross_contact_status, note, certificate_ref FROM merchant.declaration_item WHERE declaration_id = :d ORDER BY attribute_code"), {"d": declaration_id}).mappings().all()]
    editable = d["status"] in ("draft", "needs_info")
    return {**dict(d), "editable": editable, "items": items}


def set_items_bulk(db: Session, actor: str, declaration_id: int, items: list[dict]) -> int:
    def go():
        n = 0
        for it in items:
            got = db.execute(text(
                "UPDATE merchant.declaration_item SET answer = :a, cross_contact_status = :cc, note = :n, certificate_ref = :cert WHERE declaration_id = :d AND attribute_code = :attr"),
                {"a": it["answer"], "cc": it["cross_contact_status"], "n": it.get("note"), "cert": it.get("certificate_ref"), "d": declaration_id, "attr": it["attribute_code"]}).rowcount
            if not got:
                raise AppError(422, "unknown_attribute", f"unknown attribute {it['attribute_code']}")
            n += got
        return n
    return run(db, actor, go)


def update_menu(db: Session, actor: str, declaration_id: int, menu_url: str | None) -> None:
    run(db, actor, lambda: db.execute(text("UPDATE merchant.declaration SET menu_url = :u WHERE declaration_id = :d"), {"u": menu_url, "d": declaration_id}))


def plan_rows(db: Session, declaration_id: int) -> list[dict]:
    return [dict(x) for x in db.execute(text(
        "SELECT attribute_code, attribute_type, answer, cross_contact_status, new_state::text AS new_state, presence_extent, capped_by_cross_contact "
        "FROM merchant.declaration_plan(:d) ORDER BY attribute_code"), {"d": declaration_id}).mappings().all()]
