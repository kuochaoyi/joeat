"use client";
// Reviewer console: declarations queue
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { OpsShell } from "@/components/OpsShell";
import { ErrorBox } from "@/components/ui";
import { ops } from "@/lib/opsApi";

interface Row { declaration_id: number; status: string; restaurant: string; submitted_at: string | null; menu_as_of: string | null; verification_level: string; verification_method: string; is_demo: boolean; answered_items: number; conflict_count: number }
const STATUS = [["submitted", "待審"], ["needs_info", "已退回補件"], ["approved", "已核准"], ["rejected", "已駁回"], ["draft", "草稿"]] as const;

function Queue() {
  const [status, setStatus] = useState("submitted");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => ops<{ declarations: Row[] }>(`/declarations?status=${status}`).then((r) => setRows(r.declarations)).catch((e) => setError(e.message)), [status]);
  useEffect(() => { load(); }, [load]);
  return (
    <div>
      <div className="tabs">{STATUS.map(([s, l]) => <a key={s} href="#" className={status === s ? "on" : ""} onClick={(e) => { e.preventDefault(); setStatus(s); }}>{l}</a>)}</div>
      <ErrorBox message={error} />
      <table className="ops" data-testid="queue">
        <thead><tr><th>#</th><th>餐廳</th><th>驗證</th><th>已回答</th><th>矛盾</th><th>送出時間</th><th /></tr></thead>
        <tbody>
          {rows?.map((r) => (
            <tr key={r.declaration_id}>
              <td>{r.declaration_id}</td>
              <td>{r.restaurant} {r.is_demo && <span className="effect possible">示範</span>}</td>
              <td>{r.verification_level === "strong" ? "強" : "基本"}（{r.verification_method}）</td>
              <td>{r.answered_items}</td>
              <td>{r.conflict_count > 0 ? <b style={{ color: "var(--crit)" }}>{r.conflict_count}</b> : 0}</td>
              <td>{r.submitted_at ? new Date(r.submitted_at).toLocaleString("zh-TW") : "—"}</td>
              <td><Link href={`/ops/declarations/${r.declaration_id}`}>審核 →</Link></td>
            </tr>
          ))}
          {rows && rows.length === 0 && <tr><td colSpan={7} className="muted">沒有資料</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

export default function OpsHome() { return <OpsShell active="declarations"><Queue /></OpsShell>; }
