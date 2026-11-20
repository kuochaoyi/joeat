"""Shortlist real restaurants for the merchant pilot, from what the database actually knows.   Writes docs/pilot/02_candidates.md and .csv

    python scripts/pilot_candidates.py [--wave-size 6]

It only READS. It never contacts anyone. Selection rule (printed in the output, so it can be argued with):
  eligible for a phone callback = in the recommendation pool (existence confirmed by a 2nd source) AND has a listed phone number;
  wave 1 = eligible ones ranked by (existing third-party allergen/diet evidence desc, independent sources desc, name), at most 2 per primary cuisine.
Why evidence first: a declaration is worth most where our current knowledge is a weak third-party guess (blog / media), and a correction there is visible.
"""
import argparse
import csv
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.db.session import new_session  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "pilot"
MOBILE = re.compile(r"^(\+?886[-\s]?9|09)")
STATE_ZH = {"CONFIRMED_PRESENT": "已確認含有", "LIKELY_PRESENT": "可能含有", "LIKELY_ABSENT": "推測沒有", "CONFIRMED_ABSENT": "確認沒有"}


def load(db):
    rows = db.execute(text("""
      SELECT r.restaurant_id, r.canonical_name AS name, r.canonical_address AS address, r.phone, r.pool_status, r.active_status,
        (SELECT string_agg(DISTINCT rc.tag, '、' ORDER BY rc.tag) FROM enrichment.restaurant_cuisine rc WHERE rc.restaurant_id = r.restaurant_id) AS cuisines,
        (SELECT count(DISTINCT se.source_id) FROM identity.restaurant_source_entity se WHERE se.restaurant_id = r.restaurant_id AND se.match_status IN ('auto','manual_confirmed')) AS sources,
        (SELECT string_agg(DISTINCT h.consistency, '/') FROM enrichment.restaurant_opening_hours h WHERE h.restaurant_id = r.restaurant_id) AS hours
      FROM identity.restaurant r WHERE r.merged_into_restaurant_id IS NULL ORDER BY r.canonical_name""")).mappings().all()
    rows = [dict(r) for r in rows]
    ev = db.execute(text("""
      SELECT e.restaurant_id, a.display_name_zh AS attr, e.state::text AS state, left(coalesce(e.evidence_text, ''), 70) AS txt
      FROM enrichment.restaurant_attribute_evidence e JOIN ref.attribute a USING (attribute_code) JOIN ref.data_source s USING (source_id)
      WHERE NOT s.is_test AND e.status = 'active' ORDER BY a.sort_order""")).mappings().all()
    by: dict = {}
    for e in ev:
        by.setdefault(e["restaurant_id"], []).append(e)
    return rows, by


def pick(eligible, size):
    ranked = sorted(eligible, key=lambda r: (-r["n_ev"], -r["sources"], r["name"]))
    first = Counter()
    chosen = []
    for r in ranked:
        key = (r["cuisines"] or "?").split("、")[0]
        if first[key] >= 2:
            continue
        first[key] += 1
        chosen.append(r)
        if len(chosen) == size:
            break
    return chosen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave-size", type=int, default=6)
    size = ap.parse_args().wave_size
    db = new_session()
    rows, by = load(db)
    for r in rows:
        r["n_ev"] = len(by.get(r["restaurant_id"], []))
        r["mobile"] = bool(r["phone"] and MOBILE.match(re.sub(r"[\s-]", "", r["phone"])))
        r["eligible"] = r["pool_status"] == "in_pool" and bool(r["phone"])
    eligible = [r for r in rows if r["eligible"]]
    wave = pick(eligible, size)
    wave_ids = {r["restaurant_id"] for r in wave}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "02_candidates.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "address", "phone", "phone_is_mobile", "cuisines", "pool_status", "independent_sources", "hours", "third_party_evidence", "phone_callback_eligible", "wave1"])
        for r in rows:
            w.writerow([r["name"], r["address"], r["phone"], r["mobile"], r["cuisines"], r["pool_status"], r["sources"], r["hours"], r["n_ev"], r["eligible"], r["restaurant_id"] in wave_ids])

    L = [f"# 試辦候選名單(自動產生,{date.today().isoformat()})", "",
         "> 由 `backend/scripts/pilot_candidates.py` 從資料庫產生,**只讀、不聯絡任何人**。重跑會覆蓋這個檔案。資料來源是公開資料(稅籍、OSM、媒體 / 部落格),**店家本人沒有確認過任何一筆**。", "",
         "## 篩選規則", "",
         "1. **可電話回撥** = 在推薦池(存在性有第二個來源佐證)且資料裡有電話。電話回撥是最便宜的強驗證方式;沒有電話的店只能走實地確認。",
         f"2. **第一波({size} 家)** = 可電話回撥者,依「現有第三方食材 / 飲食證據數(多者優先)→ 獨立來源數 → 店名」排序,同一主要料理類型最多 2 家。理由:店家聲明在「我們現在只有部落格 / 媒體的推測」的地方價值最大,而且更正看得見。",
         "3. 這只是建議,不是結論:你可以因為人脈、地點順路、老闆好不好溝通而換人。", "",
         f"## 數字(共 {len(rows)} 家)", "",
         f"- 在推薦池:{sum(r['pool_status'] == 'in_pool' for r in rows)} 家;有電話:{sum(bool(r['phone']) for r in rows)} 家;**可電話回撥:{len(eligible)} 家**。",
         f"- 沒電話的 {sum(not r['phone'] for r in rows)} 家只能實地確認(或先去要電話 / 官方管道)。",
         f"- 電話看起來是**手機號碼**的:{sum(r['mobile'] for r in rows)} 家(見下表)。手機可能是老闆個人的:**只在營業時間打、說明來意、對方說別再打就記下來不再打**,不要把號碼貼到任何公開地方。", "",
         f"## 第一波建議({len(wave)} 家)", ""]
    for i, r in enumerate(wave, 1):
        L += [f"### {i}. {r['name']}", "",
              f"- 地址:{r['address'] or '未知'}　電話:{r['phone']}{'　⚠ 手機號碼' if r['mobile'] else ''}",
              f"- 料理:{r['cuisines'] or '未知'}　獨立來源:{r['sources']}　營業時間資料:{r['hours'] or '無'}　營業狀態:**未驗證**(先確認有在營業)",
              "- 我們目前對它的了解(第三方,**未經店家確認**):"]
        evs = by.get(r["restaurant_id"], [])
        L += [f"  - {e['attr']}:{STATE_ZH.get(e['state'], e['state'])} ——{e['txt']}" for e in evs] or ["  - (沒有任何食材 / 飲食證據)"]
        L += ["- 通話時請特別問:" + ("上面列出的項目是否屬實(特別是「可能含有」的)。" if evs else "過敏原與主要食材的使用狀況。"), ""]
    L += ["## 全部 31 家", "", "| 店名 | 池 | 電話 | 料理 | 來源數 | 第三方證據 | 可電話回撥 | 第一波 |", "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (not r["eligible"], r["name"])):
        L.append(f"| {r['name']} | {r['pool_status']} | {(r['phone'] or '—') + (' ⚠手機' if r['mobile'] else '')} | {r['cuisines'] or '—'} | {r['sources']} | {r['n_ev']} | "
                 f"{'是' if r['eligible'] else '否'} | {'★' if r['restaurant_id'] in wave_ids else ''} |")
    (OUT_DIR / "02_candidates.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {OUT_DIR / '02_candidates.md'} and .csv: {len(rows)} restaurants, {len(eligible)} callback-eligible, wave 1 = {[r['name'] for r in wave]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
