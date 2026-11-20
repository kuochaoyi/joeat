"use client";
// Reviewer console: incidents (kill switch). Logging one suspends the restaurant's positive (safety) claims at once.
import { useCallback, useEffect, useState } from "react";

import { OpsShell } from "@/components/OpsShell";
import { ErrorBox } from "@/components/ui";
import { ops, post } from "@/lib/opsApi";

interface Incident { incident_id: number; restaurant_id: string; attribute_code: string | null; severity: string; description: string | null; status: string; created_at: string; handled_by: string | null; suspended_evidence_count: number }
interface Rest { restaurant_id: string; canonical_name: string }

function Incidents() {
  const [rows, setRows] = useState<Incident[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [rests, setRests] = useState<Rest[]>([]);
  const [pick, setPick] = useState("");
  const [severity, setSeverity] = useState("allergic_reaction");
  const [desc, setDesc] = useState("");
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => ops<{ incidents: Incident[] }>("/incidents").then((r) => setRows(r.incidents)).catch((e) => setError(e.message)), []);
  useEffect(() => {
    load();
    ops<{ restaurants: Rest[] }>("/restaurants").then((r) => { setRests(r.restaurants); setNames(Object.fromEntries(r.restaurants.map((x) => [x.restaurant_id, x.canonical_name]))); if (r.restaurants[0]) setPick(r.restaurants[0].restaurant_id); }).catch(() => undefined);
  }, [load]);
  async function act(fn: () => Promise<unknown>) { setError(null); try { await fn(); await load(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } }
  return (
    <div>
      <ErrorBox message={error} />
      <div className="card">
        <h3 style={{ marginTop: 0 }}>登錄事故（會立即暫停該店的正向聲明）</h3>
        <div className="row">
          <div><label htmlFor="p">餐廳</label><select id="p" value={pick} onChange={(e) => setPick(e.target.value)}>{rests.map((r) => <option key={r.restaurant_id} value={r.restaurant_id}>{r.canonical_name}</option>)}</select></div>
          <div><label htmlFor="s">類型</label><select id="s" value={severity} onChange={(e) => setSeverity(e.target.value)}><option value="allergic_reaction">過敏反應</option><option value="wrong_info">資訊錯誤</option><option value="other">其他</option></select></div>
        </div>
        <label htmlFor="d">說明</label><input id="d" value={desc} onChange={(e) => setDesc(e.target.value)} />
        <button className="primary" style={{ marginTop: 10 }} disabled={!pick} onClick={() => act(() => post("/incidents", { restaurant_id: pick, severity, description: desc || null }))}>登錄</button>
      </div>
      <table className="ops" data-testid="incidents">
        <thead><tr><th>#</th><th>餐廳</th><th>類型</th><th>說明</th><th>被暫停的證據</th><th>狀態</th><th /></tr></thead>
        <tbody>
          {rows.map((i) => (
            <tr key={i.incident_id}>
              <td>{i.incident_id}</td><td>{names[i.restaurant_id] ?? i.restaurant_id}</td><td>{i.severity}</td><td>{i.description}</td><td>{i.suspended_evidence_count}</td><td>{i.status}</td>
              <td>{i.status === "open" && <>
                <a href="#" onClick={(e) => { e.preventDefault(); act(() => post(`/incidents/${i.incident_id}/resolve`, { outcome: "dismissed" })); }}>駁回（恢復聲明）</a>{" · "}
                <a href="#" onClick={(e) => { e.preventDefault(); act(() => post(`/incidents/${i.incident_id}/resolve`, { outcome: "confirmed" })); }}>確認（作廢並撤銷認領）</a></>}</td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={7} className="muted">沒有事故</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

export default function IncidentsPage() { return <OpsShell active="incidents"><Incidents /></OpsShell>; }
