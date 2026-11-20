"""'Report a mistake' (回報錯誤).

A report NEVER changes recommendation data. It only lands in a queue that a reviewer works through (dismiss, or escalate to a merchant
incident - which is what suspends a merchant's positive claims). That is deliberate: otherwise anyone could knock out a competitor's declaration.

Abuse limits (all counted in the database, so they survive restarts):
  * per participant: REPORTS_PER_DAY reports in 24 hours, and not twice about the same restaurant + attribute in 24 hours;
  * the reported restaurant must have been a candidate in a recommendation run of the reporter's own session;
  * per restaurant: at most OPEN_PER_RESTAURANT open reports (the queue never floods a reviewer).
Known limit: participants are cheap to create, so these limits slow down casual abuse but not a determined one; a real defense needs real LINE identity.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, not_found
from app.models.identity import Restaurant
from app.models.product import Participant, RecommendationCandidate, RecommendationRun, RestaurantReport
from app.models.ref import Attribute
from app.schemas.api import ReportIn

REPORTS_PER_DAY = 3
OPEN_PER_RESTAURANT = 30


def create_report(db: Session, restaurant_id: uuid.UUID, body: ReportIn) -> RestaurantReport:
    p = db.get(Participant, body.participant_id)
    if p is None:
        raise not_found("participant")
    if db.get(Restaurant, restaurant_id) is None:
        raise not_found("restaurant")
    seen = db.scalar(select(func.count()).select_from(RecommendationCandidate).join(RecommendationRun, RecommendationRun.run_id == RecommendationCandidate.run_id)
                     .where(RecommendationRun.session_id == p.session_id, RecommendationCandidate.restaurant_id == restaurant_id))
    if not seen:
        raise AppError(403, "not_a_candidate", "you can only report restaurants that appeared in your own session's results")
    if body.attribute_code is not None and db.get(Attribute, body.attribute_code) is None:
        raise AppError(422, "unknown_attribute", f"unknown attribute {body.attribute_code}")
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    mine = db.scalars(select(RestaurantReport).where(RestaurantReport.participant_id == p.participant_id, RestaurantReport.created_at >= since)).all()
    if len(mine) >= REPORTS_PER_DAY:
        raise AppError(429, "rate_limited", f"at most {REPORTS_PER_DAY} reports per 24 hours")
    if any(r.restaurant_id == restaurant_id and r.attribute_code == body.attribute_code for r in mine):
        raise AppError(429, "already_reported", "you already reported this today")
    open_n = db.scalar(select(func.count()).select_from(RestaurantReport).where(RestaurantReport.restaurant_id == restaurant_id, RestaurantReport.status == "open"))
    if open_n >= OPEN_PER_RESTAURANT:
        raise AppError(429, "queue_full", "this restaurant already has many open reports; a reviewer will look at them")
    row = RestaurantReport(restaurant_id=restaurant_id, attribute_code=body.attribute_code, participant_id=p.participant_id, kind=body.kind,
                           note=(body.note or "").strip() or None)
    db.add(row)
    db.commit()
    return row


# ---------------------------------------------------------------- reviewer side (/ops/reports)
INCIDENT_SEVERITY = {"allergic_reaction": "allergic_reaction", "wrong_info": "wrong_info", "closed": "other", "other": "other"}


def list_reports(db: Session, status: str | None) -> list[dict]:
    """Reviewer view. The reporter is never exposed; `reporters_for_restaurant` (distinct open reporters) tells a reviewer whether it is one person or many."""
    q = select(RestaurantReport, Restaurant.canonical_name).join(Restaurant, Restaurant.restaurant_id == RestaurantReport.restaurant_id).order_by(RestaurantReport.report_id)
    if status:
        q = q.where(RestaurantReport.status == status)
    rows = db.execute(q).all()
    counts = {rid: n for rid, n in db.execute(select(RestaurantReport.restaurant_id, func.count(func.distinct(RestaurantReport.participant_id)))
                                             .where(RestaurantReport.status == "open").group_by(RestaurantReport.restaurant_id))}
    return [{"report_id": r.report_id, "restaurant_id": r.restaurant_id, "restaurant": name, "attribute_code": r.attribute_code, "kind": r.kind, "note": r.note,
             "status": r.status, "created_at": r.created_at, "handled_by": r.handled_by, "handled_note": r.handled_note, "incident_id": r.incident_id,
             "reporters_for_restaurant": counts.get(r.restaurant_id, 0)} for r, name in rows]


def _open_report(db: Session, report_id: int) -> RestaurantReport:
    r = db.get(RestaurantReport, report_id)
    if r is None:
        raise not_found("report")
    if r.status != "open":
        raise AppError(409, "already_handled", f"report is already {r.status}")
    return r


def dismiss_report(db: Session, actor: str, report_id: int, note: str) -> dict:
    r = _open_report(db, report_id)
    r.status, r.handled_by, r.handled_at, r.handled_note = "dismissed", actor, datetime.now(timezone.utc), note
    db.commit()
    return next(x for x in list_reports(db, "dismissed") if x["report_id"] == report_id)


def escalate_report(db: Session, actor: str, report_id: int, note: str) -> dict:
    """Turns the report into a merchant incident. For allergic_reaction / wrong_info that suspends the restaurant's positive claims at once."""
    from app.services import merchant as merchant_svc          # late import: the merchant service pulls in the whole declaration lifecycle
    r = _open_report(db, report_id)
    incident = merchant_svc.create_incident(db, actor, r.restaurant_id, INCIDENT_SEVERITY[r.kind], r.attribute_code,
                                            f"使用者回報 #{r.report_id}（{r.kind}）：{r.note or '無說明'}")
    r = _open_report(db, report_id)
    r.status, r.incident_id, r.handled_by, r.handled_at, r.handled_note = "escalated", incident["incident_id"], actor, datetime.now(timezone.utc), note
    db.commit()
    return next(x for x in list_reports(db, "escalated") if x["report_id"] == report_id)
