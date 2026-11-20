"""Human-readable explanations (Traditional Chinese) built from engine results.

Privacy: everything here is GROUP-level. Warnings name an attribute ("花生資訊不足"), never the person who has the constraint.
Wording rule: never imply safety. "No known conflict" is stated as exactly that, and only for the data we have.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from app.recommendation.engine import CandidateResult
from app.core.ui_meta import NEED_ATTRIBUTES
from app.recommendation.types import AttributeInfo

LEVEL_ORDER = {"critical": 0, "high": 1, "normal": 2}
NON_ATTRIBUTE_TEXT = {
    "distance_unknown": "無法計算距離（缺少座標）",
    "hours_unknown": "營業時間資訊不足",
    "hours_conflict": "營業時間來源互相矛盾，出發前請確認",
    "price_unknown": "價格資訊不足",
}


CROSS_CONTACT_TEXT = {"confirmed_none": "確認沒有共用", "possible": "可能共用", "confirmed_shared": "確認共用", "unknown": "未知"}


def _is_declared_gap(c) -> bool:
    """A merchant declared the thing absent but the shared-equipment answer keeps it from being confirmed (a different message than 'no data')."""
    return c.declared and c.evidence_state == "LIKELY_ABSENT" and c.cross_contact in ("possible", "unknown")


def attribute_warnings(cand: CandidateResult, attributes: Mapping[str, AttributeInfo]) -> list[dict]:
    """Deduplicated by (attribute, state, code): several people with the same constraint produce one warning.

    Wording stays factual (docs/decisions/0001, D2): it says what the merchant declared and what is still unknown, never "safe".
    """
    seen: dict[tuple[str, str, str], dict] = {}
    for c in cand.filter.warning_checks:
        if c.attribute_code in NEED_ATTRIBUTES:
            continue                                  # group needs (pet / child) have their own row: see need_items()
        name = attributes[c.attribute_code].display_name_zh
        if c.engine_note == "softened_some":
            code, text = "attribute_present_some", f"{name}：店家表示有些餐點含有，可選擇不含的餐點，建議向店家確認"
        elif c.action == "PASS_CONDITIONAL":
            code, text = "attribute_" + c.evidence_state.lower(), f"{name}：可能符合，但未經店家確認"
        elif c.evidence_state == "LIKELY_PRESENT":
            code, text = "attribute_likely_present", f"{name}：資料顯示可能含有（未確認），建議向店家確認"
        elif _is_declared_gap(c) and c.cross_contact == "possible":
            code, text = "attribute_cross_contact_possible", f"{name}：店家聲明菜單未使用，但共用設備可能有交叉接觸，建議向店家確認"
        elif _is_declared_gap(c):
            code, text = "attribute_declared_shared_unknown", f"{name}：店家聲明菜單未使用；共用設備資訊：未知，建議向店家確認"
        else:
            code, text = "attribute_" + c.evidence_state.lower(), f"{name}資訊不足，建議向店家確認"
        key = (c.attribute_code, c.evidence_state, code)
        prev = seen.get(key)
        if prev is None or LEVEL_ORDER[c.warning_level] < LEVEL_ORDER[prev["level"]]:
            seen[key] = {"code": code, "attribute": c.attribute_code, "display": name,
                         "level": c.warning_level, "state": c.evidence_state, "text": text, "declared_gap": _is_declared_gap(c)}
    return sorted(seen.values(), key=lambda w: (LEVEL_ORDER[w["level"]], w["attribute"]))


def confirmed_safe(cand: CandidateResult, attributes: Mapping[str, AttributeInfo]) -> list[str]:
    """Attributes with first-party confirmation (the only case where a positive statement is allowed). Kept as an API field."""
    return sorted({attributes[c.attribute_code].display_name_zh for c in cand.filter.checks if c.may_show_safe_badge and c.attribute_code not in NEED_ATTRIBUTES})


def _date_zh(iso: str | None) -> str:
    return iso.replace("-", "/") if iso else "日期不明"


def declaration_statements(cand: CandidateResult, attributes: Mapping[str, AttributeInfo]) -> list[dict]:
    """What the merchant said, as a dated statement of fact - the only way a declaration is shown to customers (D2).

    `verified` = a reviewer confirmed the claimant by a strong method (the evidence is CONFIRMED_*). Nothing here claims safety.
    """
    out: dict[str, dict] = {}
    for c in cand.filter.checks:
        if not c.declared or c.attribute_code in out or c.attribute_code in NEED_ATTRIBUTES:
            continue
        attr = attributes[c.attribute_code]
        name, when = attr.display_name_zh, _date_zh(c.declared_on or c.verified_on)      # the merchant's declaration date; the publish date only as a fallback
        shared = f"；共用設備資訊：{CROSS_CONTACT_TEXT.get(c.cross_contact or 'unknown', '未知')}" if attr.risk_level == "critical" else ""
        verified = c.evidence_state.startswith("CONFIRMED")
        if c.attribute_type == "require":
            verb = "提供" if c.evidence_state.endswith("PRESENT") else "未提供"
            text = f"店家於 {when} 聲明{verb}{name}餐點"
        elif c.evidence_state.endswith("ABSENT"):
            text = f"店家於 {when} 聲明其目前菜單未使用{name}{shared}"
        elif c.evidence_state == "LIKELY_PRESENT" and c.cross_contact == "confirmed_shared" and c.presence_extent is None:   # an "absent" answer capped by shared equipment
            text = f"店家於 {when} 聲明菜單未使用{name}，但確認共用設備有交叉接觸風險"
        else:
            extent = {"some": "有些餐點", "most": "大部分餐點"}.get(c.presence_extent or "", "")
            text = f"店家於 {when} 聲明其菜單{extent}含有{name}"
        out[c.attribute_code] = {"attribute": c.attribute_code, "display": name, "verified": verified,
                                 "text": text + ("。已由揪呷人工驗證身分。" if verified else "。尚未列為「已確認」。")}
    return sorted(out.values(), key=lambda d: d["attribute"])


def cuisine_reason(preferences: Mapping[str, Mapping[str, str]], tags: Sequence[tuple[str, str | None]]) -> list[dict]:
    n = len(preferences)
    if not n:
        return []
    keys: list[str] = []
    for tag, parent in tags:
        for k in (tag, parent):
            if k and k not in keys:
                keys.append(k)
    best_key, best_support = None, 0
    for k in keys:
        support = sum(1 for p in preferences.values() if p.get(k) in ("love", "ok"))
        if support > best_support:
            best_key, best_support = k, support
    out: list[dict] = []
    if best_key:
        out.append({"code": "cuisine_match", "text": f"{best_support}/{n} 人偏好{best_key}"})
    for k in keys:
        dislikes = sum(1 for p in preferences.values() if p.get(k) == "dislike")
        if dislikes:
            out.append({"code": "cuisine_dislike", "text": f"{dislikes}/{n} 人不太想{k}"})
    return out


# group need attribute -> (code shown to the UI, short name, "yes" phrase, "no" phrase, what to ask)
NEEDS = {
    "pets_allowed": ("pets", "攜帶寵物", "可攜帶寵物入內", "不可攜帶寵物入內", "寵物是否能入內，請先向店家確認"),
    "kid_friendly": ("kids", "帶小孩", "有兒童座椅或兒童餐", "沒有兒童座椅與兒童餐", "有沒有兒童座椅或兒童餐，請先向店家確認"),
}


def need_items(cand: CandidateResult) -> list[dict]:
    """How this restaurant fits the group's needs (bringing a pet / a child). A merchant's declaration is stated as a dated fact (D2), like the food ones."""
    out: dict[str, dict] = {}
    for c in cand.filter.checks:
        if c.attribute_code not in NEEDS or c.attribute_code in out:
            continue
        code, name, yes, no, ask = NEEDS[c.attribute_code]
        present, confirmed = c.evidence_state.endswith("PRESENT"), c.evidence_state.startswith("CONFIRMED")
        if c.evidence_state == "UNKNOWN":
            status, text = "unknown", f"資訊不足：{ask}"
        else:
            phrase = yes if present else no
            status = "yes" if present and confirmed else "maybe" if present else "no"
            if c.declared:
                text = f"店家於 {_date_zh(c.declared_on or c.verified_on)} 聲明{phrase}。" + ("已由揪呷人工驗證身分。" if confirmed else "尚未列為「已確認」。")
            elif confirmed:
                text = f"{phrase}（第一手資料）"
            else:
                text = f"資料顯示可能{phrase}（未經店家確認）"
            if c.engine_note == "soft_need":
                text += "這只是提醒，不會排除這家店。"
            elif status == "no":
                text += "，請先向店家確認"
        out[c.attribute_code] = {"code": code, "name": name, "status": status, "text": text}
    return list(out.values())


def build_explanation(cand: CandidateResult, preferences: Mapping[str, Mapping[str, str]], attributes: Mapping[str, AttributeInfo]) -> dict:
    assert cand.score is not None
    s = cand.score
    reasons = cuisine_reason(preferences, cand.restaurant.cuisine_tags)
    safe = confirmed_safe(cand, attributes)
    if not cand.filter.checks:
        reasons.append({"code": "no_constraints", "text": "沒有人設定硬限制"})
    else:
        suspected = any(c.evidence_state == "LIKELY_PRESENT" and c.attribute_type == "avoid" and c.engine_note is None for c in cand.filter.checks)
        partial = any(c.engine_note == "softened_some" for c in cand.filter.checks)
        if suspected:
            reasons.append({"code": "suspected_conflict", "text": "有資料顯示可能與某項限制衝突（未確認，見警示）"})
        elif partial:
            reasons.append({"code": "partial_conflict", "text": "部分餐點含有某項不想吃的食材（店家表示只有些餐點含有，見警示）"})
        else:
            reasons.append({"code": "no_known_conflict", "text": "已知資料中，沒有任何人的硬限制被違反（資料不足的項目見警示）"})
        if safe:
            reasons.append({"code": "confirmed_safe", "text": "有店家聲明並經人工驗證：" + "、".join(safe)})
    if s.distance_m is not None:
        reasons.append({"code": "distance", "text": f"距離集合點約 {s.distance_m} 公尺"})
    if s.data_confidence_score > 0:
        reasons.append({"code": "data_confidence", "text": "名稱與地址經 2 個以上獨立來源確認"})
    warnings = attribute_warnings(cand, attributes)
    notes = [{"code": w["code"], "level": w["level"], "text": NON_ATTRIBUTE_TEXT[w["code"]]} for w in cand.warnings]
    if cand.restaurant.active_status == "unverified":
        notes.append({"code": "status_unverified", "level": "normal", "text": "營業狀態未驗證"})
    codes = {r["code"] for r in reasons}
    status = ("no_constraints" if "no_constraints" in codes else "suspected_conflict" if "suspected_conflict" in codes
              else "partial_conflict" if "partial_conflict" in codes else "no_known_conflict")
    unknown_states = [w for w in warnings if w["state"] in ("UNKNOWN", "LIKELY_ABSENT") and not w["declared_gap"]]    # truly no data (a declared-but-unconfirmed gap has its own wording)
    unknown_attrs = sorted({w["display"] for w in unknown_states})
    note = {"no_constraints": "沒有人設定硬限制", "no_known_conflict": "已知資料中沒有發現衝突；資料不足的項目不代表安全",
            "partial_conflict": "店家表示只有些餐點含有不想吃的食材；其餘資料不足的項目不代表安全",
            "suspected_conflict": "有資料顯示可能與某項限制衝突（未確認）"}[status]
    return {
        "hard_constraint": {"status": status, "unknown_attributes": unknown_attrs, "confirmed_safe": safe, "note": note},
        "declarations": declaration_statements(cand, attributes),
        "needs": need_items(cand),
        "summary_zh": f"總分 {s.total_score:g}：料理偏好 {s.cuisine_score:g}、距離 {s.distance_score:g}、資料可信度 {s.data_confidence_score:g}；評價與價格尚無可靠資料，未計分",
        "reasons": reasons,
        "attribute_warnings": warnings,
        "notes": notes,
        "unknown_attributes": sorted({w["attribute"] for w in unknown_states}),
        "confirmed_safe": safe,
    }
