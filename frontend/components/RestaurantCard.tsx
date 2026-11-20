"use client";
// A result card: name, one status line, the warnings that matter, then everything else behind "查看原因".
// Safety rule: an unknown allergen or a critical warning is NEVER hidden in the folded part, and nothing here says "safe".
import { useState } from "react";

import { Hint } from "@/components/ui";
import { ReportKind, reportRestaurant } from "@/lib/api";
import { getStoredParticipant } from "@/lib/storage";
import type { Need, RestaurantRecommendation, Warning } from "@/lib/types";

const ORDER = { critical: 0, high: 1, normal: 2 } as const;
const BADGE = { critical: "crit", high: "high", normal: "normal" } as const;
const LEVEL = { critical: "重要", high: "注意", normal: "提醒" } as const;
const KINDS: [ReportKind, string][] = [["wrong_info", "資訊有誤"], ["allergic_reaction", "吃了出現過敏反應"], ["closed", "歇業 / 搬遷"], ["other", "其他"]];
const NEED_SHORT: Record<Need["status"], [string, string]> = { yes: ["可以", "ok"], maybe: ["可能可以", "high"], no: ["沒有", "high"], unknown: ["資訊不足", "normal"] };

/** Attributes with no data at all are named in the status line (critical ones first, marked), so their own warning rows would only repeat it. */
const isUnknownRow = (w: Warning, unknown: string[]) => (w.code === "attribute_unknown" || w.code === "attribute_likely_absent") && !!w.display && unknown.includes(w.display);

function Status({ r }: { r: RestaurantRecommendation }) {
  const hc = r.hard_constraint;
  const bad = r.warnings.some((w) => w.level === "critical");
  const critical = new Set(r.warnings.filter((w) => w.level === "critical" && isUnknownRow(w, hc.unknown_attributes)).map((w) => w.display));
  const names = [...hc.unknown_attributes].sort((a, b) => Number(critical.has(b)) - Number(critical.has(a))).map((n) => (critical.has(n) ? `${n}（重要）` : n));
  let cls = "ok", text = "已知資料沒有衝突";
  if (hc.status === "no_constraints") { cls = "none"; text = "沒有人設定限制"; }
  else if (hc.status === "suspected_conflict") { cls = "crit"; text = "有資料顯示可能衝突（未確認）"; }
  else if (hc.status === "partial_conflict") { cls = "warn"; text = "只有部分餐點含有不想吃的食材"; }
  else if (names.length > 0) { cls = "warn"; text = `資料不足：${names.join("、")}`; }
  else if (bad) { cls = "warn"; text = "有重要提醒"; }
  return <div className={`status ${cls}`} data-testid="status">{cls === "ok" ? "✓" : cls === "crit" ? "!" : cls === "warn" ? "⚠" : "·"} {text}</div>;
}

/** "Report a mistake": goes to a human reviewer's queue. It does not change the results by itself (and is rate limited on the server). */
function ReportForm({ r, sessionId }: { r: RestaurantRecommendation; sessionId: string }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<ReportKind>("wrong_info");
  const [attr, setAttr] = useState("");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const pid = getStoredParticipant(sessionId);
  if (!pid) return null;                                       // opened on a device that never joined: nothing to attribute the report to

  const attributes = new Map<string, string>();
  r.declarations.forEach((d) => attributes.set(d.attribute, d.display));
  r.warnings.forEach((w) => { if (w.attribute && w.display) attributes.set(w.attribute, w.display); });

  async function send() {
    setBusy(true); setMsg(null);
    try {
      const res = await reportRestaurant(r.restaurant_id, { participant_id: pid as string, kind, attribute_code: attr || undefined, note: note.trim() || undefined });
      setMsg({ ok: true, text: res.message }); setOpen(false); setNote("");
    } catch (e) { setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) }); }
    setBusy(false);
  }

  return (
    <div style={{ marginTop: 6 }}>
      {!open && <button className="link" data-testid={`report-open-${r.rank}`} onClick={() => { setOpen(true); setMsg(null); }}>回報資料錯誤</button>}
      {open && (
        <div className="card" style={{ background: "var(--chip)", boxShadow: "none" }}>
          <select aria-label="哪裡有問題" value={kind} onChange={(e) => setKind(e.target.value as ReportKind)}>{KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          <select aria-label="和哪一項有關" style={{ marginTop: 8 }} value={attr} onChange={(e) => setAttr(e.target.value)}>
            <option value="">整體 / 不確定</option>{[...attributes].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <input aria-label="說明" style={{ marginTop: 8 }} placeholder="說明（選填）" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
          <p className="tiny">交給審核人員查證，查證前不會改變結果。每人 24 小時最多 3 次。</p>
          <div className="row"><button className="primary small" disabled={busy} onClick={send}>送出</button><button className="small" onClick={() => setOpen(false)}>取消</button></div>
        </div>
      )}
      {msg && <div className="tiny" data-testid={`report-msg-${r.rank}`} style={{ color: msg.ok ? undefined : "var(--crit)" }}>{msg.text}</div>}
    </div>
  );
}

export function RestaurantCard({ r, sessionId }: { r: RestaurantRecommendation; sessionId: string }) {
  const [open, setOpen] = useState(false);
  const sorted: Warning[] = [...r.warnings].filter((w) => !isUnknownRow(w, r.hard_constraint.unknown_attributes)).sort((a, b) => ORDER[a.level] - ORDER[b.level]);
  const inline = sorted.filter((w) => w.level !== "normal").slice(0, 2);          // the warnings that matter stay on the surface
  const more = sorted.length - inline.length;
  const sc = r.score;

  return (
    <article className="card" data-testid={`rec-${r.rank}`}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span className={`badge ${r.rank === 1 ? "brand" : "normal"}`}>{r.rank === 1 ? "👑 最符合大家" : `第 ${r.rank} 名`}</span>
        <span className="badge normal">{sc.total} 分</span>
      </div>
      <h2 style={{ fontSize: "1.2rem", margin: "0 0 2px" }}>{r.name}</h2>
      <div className="muted">{r.cuisines.join("、") || "料理類型未知"} · {r.distance_m != null ? `距離 ${r.distance_m} 公尺` : "距離未知"}</div>

      <Status r={r} />
      {inline.map((w, i) => <div key={i} className="warning"><span className={`badge ${BADGE[w.level]}`}>{LEVEL[w.level]}</span><span>{w.text}</span></div>)}

      {r.needs.length > 0 && (
        <div className="chips" style={{ margin: "8px 0" }} data-testid={`needs-${r.rank}`}>
          {r.needs.map((n) => <span key={n.code} className={`badge ${NEED_SHORT[n.status][1]}`}>{n.code === "pets" ? "🐾" : "🧒"} {n.name}：{NEED_SHORT[n.status][0]}</span>)}
        </div>
      )}
      {r.declarations.length > 0 && (
        <div className="chips" style={{ margin: "8px 0" }} data-testid={`declarations-${r.rank}`}>
          {r.declarations.map((d) => <span key={d.attribute} className={`badge ${d.verified ? "ok" : "normal"}`}>店家聲明{d.verified ? "・已驗證" : ""}：{d.display}</span>)}
        </div>
      )}

      <button className="small" style={{ width: "100%", marginTop: 6 }} aria-expanded={open} onClick={() => setOpen((v) => !v)} data-testid={`more-${r.rank}`}>
        {open ? "收起" : `查看原因${more > 0 ? `（還有 ${more} 則提醒）` : ""}`}
      </button>

      {open && (
        <div style={{ marginTop: 10 }} data-testid={`detail-${r.rank}`}>
          <h2 style={{ fontSize: ".9rem" }}>為什麼推薦</h2>
          <ul className="plain">{r.reasons.map((t, i) => <li key={i}>・{t}</li>)}</ul>
          {sorted.length > inline.length && (
            <>
              <h2 style={{ fontSize: ".9rem", marginTop: 12 }}>其他提醒</h2>
              {sorted.filter((w) => !inline.includes(w)).map((w, i) => <div key={i} className="warning"><span className={`badge ${BADGE[w.level]}`}>{LEVEL[w.level]}</span><span>{w.text}</span></div>)}
            </>
          )}
          {(r.declarations.length > 0 || r.needs.some((n) => n.status !== "unknown")) && (
            <>
              <h2 style={{ fontSize: ".9rem", marginTop: 12 }}>店家說的</h2>
              {r.declarations.map((d) => <div key={d.attribute} className="warning"><span>・{d.text}</span></div>)}
              {r.needs.filter((n) => n.status !== "unknown").map((n) => <div key={n.code} className="warning"><span>・{n.name}：{n.text}</span></div>)}
            </>
          )}
          <div className="score"><span>料理 {sc.cuisine}</span><span>距離 {sc.distance}</span><span>資料可信度 {sc.data_confidence}</span><span title="尚無可靠資料">評價 —</span><span title="尚無可靠資料">價格 —</span></div>
          <div className="tiny">{r.address || "地址未知"}{r.phone ? ` · ${r.phone}` : ""}</div>
          <ReportForm r={r} sessionId={sessionId} />
        </div>
      )}
    </article>
  );
}
