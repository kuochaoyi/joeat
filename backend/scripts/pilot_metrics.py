"""Numbers for the merchant pilot (docs/pilot/01_pilot_plan.md): does the flow work, and does it produce data worth having?   READ-ONLY.

    python scripts/pilot_metrics.py                 # real merchants only
    python scripts/pilot_metrics.py --include-demo  # also count demo claims (to try the script on a development database)

Small numbers: with 6 merchants a percentage is an anecdote. Read the counts, not the percentages.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.db.session import new_session  # noqa: E402


def q(db, sql, **p):
    return db.execute(text(sql), p).all()


def median_hours(db, expr, where):
    v = db.scalar(text(f"SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY {expr}) FROM {where}"))
    return "—" if v is None else f"{v / 3600:.1f} 小時"


def main() -> int:
    demo = "--include-demo" in sys.argv
    scope = "TRUE" if demo else "NOT c.is_demo"
    db = new_session()
    print(f"=== 試辦指標({'含示範資料' if demo else '只含真實店家'}) ===\n")

    f = q(db, f"""SELECT count(DISTINCT c.claim_id) AS invited,
                         count(DISTINCT c.claim_id) FILTER (WHERE c.verified_at IS NOT NULL) AS verified,
                         count(DISTINCT d.claim_id) AS started,
                         count(DISTINCT d.claim_id) FILTER (WHERE d.status <> 'draft') AS submitted,
                         count(DISTINCT d.claim_id) FILTER (WHERE d.status IN ('approved','withdrawn')) AS published
                  FROM merchant.claim c LEFT JOIN merchant.declaration d ON d.claim_id = c.claim_id WHERE {scope}""")[0]
    print("【漏斗】邀請 {0} → 已驗證 {1} → 開始填寫 {2} → 已送出 {3} → 曾經發布 {4}".format(*f))
    print("  (已驗證 / 邀請 低 = 找人與驗證是瓶頸;已送出 / 已驗證 低 = 表單太難或店家沒興趣)\n")

    base = f"merchant.claim c JOIN merchant.declaration d ON d.claim_id = c.claim_id WHERE {scope}"
    print("【花費的時間(中位數)】")
    print("  邀請 → 驗證完成:", median_hours(db, "extract(epoch FROM c.verified_at - c.invited_at)", f"merchant.claim c WHERE c.verified_at IS NOT NULL AND {scope}"))
    print("  驗證完成 → 送出:", median_hours(db, "extract(epoch FROM d.submitted_at - c.verified_at)", f"{base} AND d.submitted_at IS NOT NULL"))
    print("  送出 → 審核結果:", median_hours(db, "extract(epoch FROM d.reviewed_at - d.submitted_at)", f"{base} AND d.reviewed_at IS NOT NULL"), "\n")

    items = f"merchant.declaration_item i JOIN merchant.declaration d USING (declaration_id) JOIN merchant.claim c ON c.claim_id = d.claim_id JOIN ref.attribute a ON a.attribute_code = i.attribute_code WHERE d.status <> 'draft' AND {scope}"
    ans = q(db, f"SELECT i.answer, count(*) FROM {items} GROUP BY 1 ORDER BY 2 DESC")
    total = sum(n for _, n in ans)
    print(f"【店家的答案】共 {total} 題(含店家沒動、預設就是 not_sure 的題目):", "、".join(f"{a} {n}" for a, n in ans) or "(還沒有送出的聲明)")
    print("  not_sure(我不確定)很多不是壞事——那是誠實的答案;但如果幾乎全部都是,這個流程就沒有產出。\n")

    print("【關鍵過敏原答「菜單完全沒有」時,共用設備怎麼答】(決定過敏族群能不能真的得到「已確認」)")
    cc = q(db, f"SELECT i.cross_contact_status, count(*) FROM {items} AND a.risk_level = 'critical' AND i.answer = 'absent_entire_menu' GROUP BY 1 ORDER BY 2 DESC")
    n_cc = sum(n for _, n in cc)
    print("  ", "、".join(f"{s} {n}" for s, n in cc) or "(沒有資料)")
    none = dict(cc).get("confirmed_none", 0)
    if n_cc:
        print(f"   → 能拿到 CONFIRMED_ABSENT 的只有 confirmed_none:{none}/{n_cc}。其餘會是 LIKELY_ABSENT(重要警示,嚴格過敏模式會排除)。\n")
    else:
        print()

    audit = dict(q(db, f"""SELECT a.event, count(*) FROM merchant.declaration_audit a JOIN merchant.declaration d USING (declaration_id) JOIN merchant.claim c ON c.claim_id = d.claim_id
                          WHERE {scope} AND a.event IN ('status:needs_info','status:rejected','superseded_third_party_evidence','withdrawn') GROUP BY 1"""))
    print("【審核】退回補件 {0} 次、駁回 {1} 次、取代第三方證據 {2} 次(店家與我們原本的資料不一致)、撤下 {3} 次\n".format(
        audit.get("status:needs_info", 0), audit.get("status:rejected", 0), audit.get("superseded_third_party_evidence", 0), audit.get("withdrawn", 0)))

    inc = q(db, "SELECT status, count(*) FROM merchant.incident_report GROUP BY 1")
    rep = q(db, "SELECT status, count(*) FROM product.restaurant_report GROUP BY 1")
    print("【事故】", "、".join(f"{s} {n}" for s, n in inc) or "無", "　【使用者回報】", "、".join(f"{s} {n}" for s, n in rep) or "無")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
