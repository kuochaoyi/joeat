"""Restaurant detail: identity, cuisines, hours and the evidence behind every known attribute (all public facts about the venue)."""
from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.db.session import apply_runtime_flags
from app.models.enrichment import RestaurantCuisine, RestaurantOpeningHours
from app.models.identity import Restaurant
from app.models.ref import Attribute

STATE_TEXT = {
    "CONFIRMED_PRESENT": "已確認含有／提供", "LIKELY_PRESENT": "可能含有／提供（未確認）",
    "LIKELY_ABSENT": "推測沒有（不代表安全）", "CONFIRMED_ABSENT": "有第一手資料顯示沒有（以證據內容為準）", "UNKNOWN": "資料不足",
}


def get_detail(db: Session, restaurant_id: uuid.UUID) -> dict:
    r = db.get(Restaurant, restaurant_id)
    if r is None:
        raise not_found("restaurant")
    apply_runtime_flags(db)
    cuisines = [{"tag": c.tag, "origin": c.origin, "confidence": c.confidence} for c in db.scalars(select(RestaurantCuisine).where(RestaurantCuisine.restaurant_id == restaurant_id))]
    hours = [{"raw_text": h.raw_text, "consistency": h.consistency, "confidence": h.confidence, "source_url": h.source_url, "last_verified_at": h.last_verified_at.isoformat()}
             for h in db.scalars(select(RestaurantOpeningHours).where(RestaurantOpeningHours.restaurant_id == restaurant_id))]
    names = {a.attribute_code: a.display_name_zh for a in db.scalars(select(Attribute))}
    rows = db.execute(text(
        "SELECT s.attribute_code, s.state::text AS state, s.implied, s.implied_from, e.evidence_text, e.evidence_basis, e.applies_to, e.confidence, e.source_url, e.last_verified_at, e.valid_until "
        "FROM enrichment.restaurant_attribute_state s LEFT JOIN enrichment.restaurant_attribute_evidence e ON e.evidence_id = s.deciding_evidence_id "
        "WHERE s.restaurant_id = :rid ORDER BY s.attribute_code"), {"rid": restaurant_id}).mappings().all()
    attributes = [{"attribute": x["attribute_code"], "display": names.get(x["attribute_code"], x["attribute_code"]), "state": x["state"], "state_text": STATE_TEXT[x["state"]],
                   "implied": x["implied"], "evidence_text": x["evidence_text"], "basis": x["evidence_basis"], "applies_to": x["applies_to"], "confidence": x["confidence"],
                   "source_url": x["source_url"], "last_verified_at": x["last_verified_at"].isoformat() if x["last_verified_at"] else None,
                   "valid_until": x["valid_until"].isoformat() if x["valid_until"] else None} for x in rows]
    sources = [dict(x) for x in db.execute(text(
        "SELECT ds.source_type, se.source_name, se.source_address, se.match_status FROM identity.restaurant_source_entity se "
        "JOIN ref.data_source ds USING (source_id) WHERE se.restaurant_id = :rid ORDER BY ds.source_type"), {"rid": restaurant_id}).mappings().all()]
    notes = ["本頁資料來自公開來源，未經店家確認。"]
    if r.active_status == "unverified":
        notes.append("營業狀態未驗證。")
    if not any(a["state"] == "CONFIRMED_ABSENT" for a in attributes):
        notes.append("目前沒有任何過敏原或飲食項目有第一手的「確認不含」資料；沒有列出的項目代表資料不足，不代表安全。")
    return {
        "restaurant_id": r.restaurant_id, "name": r.canonical_name, "address": r.canonical_address, "phone": r.phone, "lat": r.lat, "lon": r.lon,
        "district": r.district, "cuisines": cuisines, "active_status": r.active_status, "pool_status": r.pool_status,
        "opening_hours": hours, "attributes": attributes, "sources": sources, "notes": notes,
    }
