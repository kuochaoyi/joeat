"use client";
// Reviewer console: user reports ("report a mistake"). A report changes nothing by itself; escalating it creates a merchant incident.
import { useCallback, useEffect, useState } from "react";

import { OpsShell } from "@/components/OpsShell";
import { ErrorBox } from "@/components/ui";
import { ops, post } from "@/lib/opsApi";

interface Report { report_id: number; restaurant: string; attribute_code: string | null; kind: string; note: string | null; status: string; created_at: string; handled_by: string | null; handled_note: string | null; incident_id: number | null; reporters_for_restaurant: number }
const KIND: Record<string, string> = { wrong_info: "資訊有誤", allergic_reaction: "過敏反應", closed: "歇業 / 搬遷", other: "其他" };
const STATUS = [["open", "待處理"], ["escalated", "已升級為事故"], ["dismissed", "已駁回"]] as const;

function Reports() {
  const [status, setStatus] = useState("open");
  const [rows, setRows] = useState<Report[] | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => ops<{ reports: Report[] }>(`/reports?status=${status}`).then((r) => setRows(r.reports)).catch((e) => setError(e.message)), [status]);
  useEffect(() => { load(); }, [load]);
  async function act(id: number, what: "dismiss" | "escalate") {
    setError(null);
    try { await post(`/reports/${id}/${what}`, { note: notes[id] ?? "" }); await load(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }
  return (
    <div>
      <p className="muted">使用者回報在你處理之前不會改變任何推薦結果。「升級為事故」會立刻暫停該店的正向聲明（過敏反應 / 資訊錯誤），請先查證；回報人不會顯示。</p>
      <div className="tabs">{STATUS.map(([s, l]) => <a key={s} href="#" className={status === s ? "on" : ""} onClick={(e) => { e.preventDefault(); setStatus(s); }}>{l}</a>)}</div>
      <ErrorBox message={error} />
      <table className="ops" data-testid="reports">
        <thead><tr><th>#</th><th>餐廳</th><th>類型</th><th>項目</th><th>說明</th><th>此店待處理的不同回報人</th><th>處理</th></tr></thead>
        <tbody>
          {rows?.map((r) => (
            <tr key={r.report_id}>
              <td>{r.report_id}</td><td>{r.restaurant}</td><td>{KIND[r.kind] ?? r.kind}</td><td>{r.attribute_code ?? "整體"}</td><td>{r.note ?? "—"}</td><td>{r.reporters_for_restaurant}</td>
              <td>
                {r.status === "open" ? (
                  <>
                    <input aria-label={`處理說明 ${r.report_id}`} placeholder="查證結果（至少 5 字）" value={notes[r.report_id] ?? ""} onChange={(e) => setNotes({ ...notes, [r.report_id]: e.target.value })} />
                    <div className="row" style={{ marginTop: 6 }}>
                      <button disabled={(notes[r.report_id] ?? "").trim().length < 5} onClick={() => act(r.report_id, "escalate")}>升級為事故</button>
                      <button disabled={(notes[r.report_id] ?? "").trim().length < 5} onClick={() => act(r.report_id, "dismiss")}>駁回</button>
                    </div>
                  </>
                ) : <span className="muted">{r.handled_by}：{r.handled_note}{r.incident_id ? `（事故 #${r.incident_id}）` : ""}</span>}
              </td>
            </tr>
          ))}
          {rows && rows.length === 0 && <tr><td colSpan={7} className="muted">沒有資料</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

export default function ReportsPage() { return <OpsShell active="reports"><Reports /></OpsShell>; }
