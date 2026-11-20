"use client";
// Reviewer console: one declaration. Shows what publishing WOULD write, the contradictions, the audit trail; publish / send back / reject.
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { OpsShell } from "@/components/OpsShell";
import { ErrorBox } from "@/components/ui";
import { ops, post } from "@/lib/opsApi";

interface Detail {
  declaration: { declaration_id: number; status: string; restaurant: string; canonical_address: string | null; phone: string | null; menu_as_of: string | null; menu_url: string | null; declared_role: string | null; valid_days: number; review_note: string | null; reviewed_by: string | null };
  claim: { status: string; is_demo: boolean; verification_method: string; verification_level: string; verification_note: string; verified_by: string; verified_at: string; claimant_role: string | null };
  items: { attribute_code: string; display_name_zh: string; attribute_type: string; risk_level: string; answer: string; cross_contact_status: string; note: string | null; certificate_ref: string | null }[];
  plan: { attribute_code: string; answer: string; cross_contact_status: string; new_state: string; evidence_basis: string; confidence: string; presence_extent: string | null; capped_by_cross_contact: boolean; conflicts: number[] | null; conflicts_confirmed: boolean }[];
  conflicts: { evidence_id: number; attribute_code: string; state: string; evidence_basis: string; evidence_text: string | null; source_type: string }[];
  audit: { event: string; actor: string | null; at: string; detail: unknown }[];
}

function Review() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [supersede, setSupersede] = useState(false);
  const load = useCallback(() => ops<Detail>(`/declarations/${id}`).then(setD).catch((e) => setError(e.message)), [id]);
  useEffect(() => { load(); }, [load]);

  async function act(fn: () => Promise<unknown>, done: string) {
    setError(null); setMsg(null);
    try { await fn(); setMsg(done); await load(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  if (!d) return <ErrorBox message={error} />;
  const { declaration: x, claim: c } = d;
  const open = x.status === "submitted";
  const hasConflict = d.plan.some((p) => p.conflicts);
  const confirmedConflict = d.plan.some((p) => p.conflicts_confirmed);
  const answered = new Map(d.items.map((i) => [i.attribute_code, i]));
  return (
    <div>
      <p><Link href="/ops" className="muted">← 回到清單</Link></p>
      <h2 style={{ margin: 0 }}>#{x.declaration_id} {x.restaurant} {c.is_demo && <span className="effect possible">示範資料</span>} <span className="effect contains" style={{ background: "var(--chip)", color: "var(--ink)" }}>{x.status}</span></h2>
      <p className="muted">{x.canonical_address ?? "地址未知"} · {x.phone ?? "電話未知"}</p>
      <ErrorBox message={error} />
      {msg && <div className="card" style={{ background: "#d3f9d8" }} data-testid="msg">{msg}</div>}

      <div className="card">
        <b>驗證</b>：{c.verification_level === "strong" ? "強" : "基本"}（{c.verification_method}）· {c.verified_by} · {new Date(c.verified_at).toLocaleString("zh-TW")}<br />
        <span className="muted">備註：{c.verification_note}</span><br />
        <b>聲明人</b>：{x.declared_role ?? "—"}　<b>菜單日期</b>：{x.menu_as_of ?? "—"}　<b>菜單</b>：{x.menu_url ? <a href={x.menu_url} target="_blank" rel="noreferrer">連結</a> : "無"}　<b>有效</b>：{x.valid_days} 天
      </div>

      <h3>發布預覽（發布會寫入什麼）</h3>
      <table className="ops" data-testid="plan">
        <thead><tr><th>屬性</th><th>店家答案</th><th>共用設備</th><th>寫入狀態</th><th>基礎 / 信心</th><th>備註</th></tr></thead>
        <tbody>
          {d.plan.map((p) => {
            const it = answered.get(p.attribute_code);
            return (
              <tr key={p.attribute_code} className={p.conflicts ? "conflict" : ""}>
                <td>{it?.display_name_zh ?? p.attribute_code}</td><td>{p.answer}</td><td>{p.cross_contact_status}</td>
                <td><b>{p.new_state}</b>{p.presence_extent ? `（${p.presence_extent}）` : ""}{p.capped_by_cross_contact ? " ⚠ 共用設備降級" : ""}</td>
                <td>{p.evidence_basis} / {p.confidence}</td>
                <td>{p.conflicts ? <b style={{ color: "var(--crit)" }}>與證據 {p.conflicts.join(", ")} 矛盾{p.conflicts_confirmed ? "（已確認，不可覆蓋）" : ""}</b> : ""}{it?.note ? `備註：${it.note}` : ""}{it?.certificate_ref ? ` 認證：${it.certificate_ref}` : ""}</td>
              </tr>
            );
          })}
          {d.plan.length === 0 && <tr><td colSpan={6} className="muted">店家沒有回答任何項目（全部「不確定」）。</td></tr>}
        </tbody>
      </table>

      {d.conflicts.length > 0 && (
        <>
          <h3>矛盾的既有證據</h3>
          <table className="ops"><thead><tr><th>#</th><th>屬性</th><th>狀態</th><th>基礎</th><th>內容</th></tr></thead>
            <tbody>{d.conflicts.map((e) => <tr key={e.evidence_id}><td>{e.evidence_id}</td><td>{e.attribute_code}</td><td>{e.state}</td><td>{e.evidence_basis} / {e.source_type}</td><td>{e.evidence_text}</td></tr>)}</tbody></table>
        </>
      )}

      {open && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3 style={{ marginTop: 0 }}>決定</h3>
          {hasConflict && !confirmedConflict && (
            <label style={{ display: "flex", gap: 8, fontWeight: 400 }}><input type="checkbox" style={{ width: "auto" }} checked={supersede} onChange={(e) => setSupersede(e.target.checked)} />
              <span>我已查證，同意以這份聲明<b>取代</b>上列矛盾的「可能」證據（會寫入稽核紀錄）</span></label>
          )}
          {confirmedConflict && <p style={{ color: "var(--crit)" }}>與「已確認」的證據矛盾：不能發布。請先處理資料或駁回。</p>}
          <label htmlFor="note">退回 / 駁回的說明（必填，至少 5 字）</label>
          <input id="note" value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="row" style={{ marginTop: 10 }}>
            <button className="primary" disabled={confirmedConflict || (hasConflict && !supersede)} onClick={() => act(() => post(`/declarations/${id}/publish`, { supersede }), "已發布")}>核准並發布</button>
            <button disabled={note.trim().length < 5} onClick={() => act(() => post(`/declarations/${id}/needs-info`, { note }), "已退回補件")}>退回補件</button>
            <button disabled={note.trim().length < 5} onClick={() => act(() => post(`/declarations/${id}/reject`, { note }), "已駁回")}>駁回</button>
          </div>
        </div>
      )}
      {x.status === "approved" && (
        <div className="card" style={{ marginTop: 16 }} data-testid="withdraw-card">
          <h3 style={{ marginTop: 0 }}>撤下這份已發布的聲明</h3>
          <p className="muted">菜單改了、店家要求撤下、或不再信任這份聲明時使用。<b>「沒有 X」這類聲明會立刻失效</b>；「含有 X」這類風險資訊會保留到原本的有效期限（拿掉它只會讓使用者更不謹慎）。撤下後店家可以重新填寫。</p>
          <label htmlFor="wnote">撤下原因（必填，至少 5 字；用職稱，不要寫姓名）</label>
          <input id="wnote" value={note} onChange={(e) => setNote(e.target.value)} />
          <button style={{ marginTop: 10 }} disabled={note.trim().length < 5} onClick={() => act(() => post(`/declarations/${id}/withdraw`, { note }), "已撤下")}>撤下聲明</button>
        </div>
      )}
      {x.status !== "submitted" && x.review_note && <p className="muted">審核說明（{x.reviewed_by}）：{x.review_note}</p>}

      <h3>稽核紀錄</h3>
      <table className="ops"><thead><tr><th>時間</th><th>事件</th><th>操作者</th></tr></thead>
        <tbody>{d.audit.map((a, i) => <tr key={i}><td>{new Date(a.at).toLocaleString("zh-TW")}</td><td>{a.event}</td><td>{a.actor ?? "—"}</td></tr>)}</tbody></table>
    </div>
  );
}

export default function DeclarationPage() { return <OpsShell active="declarations"><Review /></OpsShell>; }
