"use client";
// Reviewer console: invite a restaurant, record HOW the claimant was verified, revoke
import { useCallback, useEffect, useState } from "react";

import { OpsShell } from "@/components/OpsShell";
import { ErrorBox } from "@/components/ui";
import { ops, post } from "@/lib/opsApi";

interface Claim { claim_id: number; restaurant: string; status: string; is_demo: boolean; verification_method: string | null; verification_level: string; verified_by: string | null; invited_by: string; invited_at: string }
interface Rest { restaurant_id: string; canonical_name: string; canonical_address: string | null; pool_status: string }
const METHODS = [
  ["phone_callback", "電話回撥（強）"], ["onsite_visit", "實地確認（強）"], ["official_menu_review", "官方菜單 + 人工覆核（強，發布時必須附菜單）"], ["official_channel_message", "官方管道訊息（基本）"],
] as const;

function Claims() {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Rest[]>([]);
  const [pick, setPick] = useState("");
  const [demo, setDemo] = useState(false);
  const [created, setCreated] = useState<{ token: string; claim_id: number } | null>(null);
  const [vid, setVid] = useState<number | null>(null);
  const [method, setMethod] = useState("phone_callback");
  const [role, setRole] = useState("owner");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => ops<{ claims: Claim[] }>("/claims").then((r) => setClaims(r.claims)).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { ops<{ restaurants: Rest[] }>(`/restaurants?q=${encodeURIComponent(q)}`).then((r) => { setFound(r.restaurants); if (!pick && r.restaurants[0]) setPick(r.restaurants[0].restaurant_id); }).catch(() => undefined); }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

  async function act(fn: () => Promise<unknown>) { setError(null); try { await fn(); await load(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } }
  const base = typeof window !== "undefined" ? window.location.origin : "";

  return (
    <div>
      <ErrorBox message={error} />
      <div className="card">
        <h3 style={{ marginTop: 0 }}>邀請餐廳</h3>
        <div className="row">
          <div><label htmlFor="q">搜尋餐廳</label><input id="q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="店名" /></div>
          <div><label htmlFor="pick">選擇</label><select id="pick" value={pick} onChange={(e) => setPick(e.target.value)}>{found.map((r) => <option key={r.restaurant_id} value={r.restaurant_id}>{r.canonical_name}（{r.pool_status}）</option>)}</select></div>
        </div>
        <label style={{ display: "flex", gap: 8, fontWeight: 400 }}><input type="checkbox" style={{ width: "auto" }} checked={demo} onChange={(e) => setDemo(e.target.checked)} /><span>示範用認領（發布假證據到隱藏的測試來源；僅在開啟 ALLOW_TEST_EVIDENCE 時可用）</span></label>
        <button className="primary" style={{ marginTop: 10 }} disabled={!pick} onClick={() => act(async () => setCreated(await post("/claims", { restaurant_id: pick, is_demo: demo })))}>建立邀請</button>
        {created && <p data-testid="created">連結（<b>只會顯示這一次</b>）：<span className="mono">{base}/m/{created.token}</span></p>}
      </div>

      <table className="ops" data-testid="claims">
        <thead><tr><th>#</th><th>餐廳</th><th>狀態</th><th>驗證</th><th>邀請</th><th /></tr></thead>
        <tbody>
          {claims.map((c) => (
            <tr key={c.claim_id}>
              <td>{c.claim_id}</td><td>{c.restaurant} {c.is_demo && <span className="effect possible">示範</span>}</td><td>{c.status}</td>
              <td>{c.verification_method ? `${c.verification_level === "strong" ? "強" : "基本"}（${c.verification_method}）${c.verified_by}` : "—"}</td>
              <td>{c.invited_by}</td>
              <td>
                {c.status === "invited" && <a href="#" onClick={(e) => { e.preventDefault(); setVid(c.claim_id); }}>驗證</a>}{" "}
                {(c.status === "invited" || c.status === "verified") && <a href="#" onClick={(e) => { e.preventDefault(); act(() => post(`/claims/${c.claim_id}/revoke`)); }}>撤銷</a>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {vid !== null && (
        <div className="card" style={{ marginTop: 12 }} data-testid="verify-form">
          <h3 style={{ marginTop: 0 }}>驗證認領 #{vid}：記錄你實際做了什麼</h3>
          <label htmlFor="m">方式</label><select id="m" value={method} onChange={(e) => setMethod(e.target.value)}>{METHODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          <label htmlFor="r">對方身分</label><select id="r" value={role} onChange={(e) => setRole(e.target.value)}><option value="owner">老闆</option><option value="manager">店長</option><option value="staff">員工</option></select>
          <label htmlFor="n">備註（必填，至少 5 字：用職稱說明誰接的電話（老闆 / 店長 / 員工），<b>不要寫姓名或個人電話</b>；看到什麼；覆核了哪份菜單）</label><input id="n" value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="row" style={{ marginTop: 10 }}>
            <button className="primary" disabled={note.trim().length < 5} onClick={() => act(async () => { await post(`/claims/${vid}/verify`, { method, note, claimant_role: role }); setVid(null); setNote(""); })}>確認驗證</button>
            <button onClick={() => setVid(null)}>取消</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ClaimsPage() { return <OpsShell active="claims"><Claims /></OpsShell>; }
