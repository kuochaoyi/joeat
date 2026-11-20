"use client";
// Screen 4 - Top 3. Each card shows the decision at a glance; the reasons are one tap away.
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { RestaurantCard } from "@/components/RestaurantCard";
import { Back, BottomBar, ErrorBox, Hint } from "@/components/ui";
import { ApiError, getRecommendation, runRecommendation } from "@/lib/api";
import type { Recommendation } from "@/lib/types";

export default function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<Recommendation | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getRecommendation(id).then(setData).catch((e) => { if (e instanceof ApiError && e.status === 404) setMissing(true); else setError(e.message); });
  }, [id]);

  async function generate() {
    setBusy(true); setError(null);
    try { setData(await runRecommendation(id, true)); setMissing(false); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  }

  return (
    <div>
      <Back href={`/s/${id}`}>回到聚餐</Back>
      <h1>最適合你們的 3 間 🎯</h1>
      <ErrorBox message={error} />
      {missing && (
        <div className="card"><p>還沒有推薦結果。</p><button className="primary" style={{ width: "100%" }} onClick={generate} disabled={busy}>{busy ? "計算中…" : "用目前已填的人產生推薦"}</button></div>
      )}
      {data && (
        <>
          {data.test_evidence_enabled && <div className="demo-banner" data-testid="demo-banner">示範資料模式：部分「店家聲明」是假資料，不能當作真實資訊。</div>}
          <div className="muted" data-testid="summary">{data.participants} 人 · 候選 {data.pool_size} 家 · 排除 {data.excluded_count} 家 · 可推薦 {data.eligible_count} 家</div>
          {data.strict_mode && <div className="status warn" data-testid="strict-note">🛡 有成員開啟嚴格過敏模式：只推薦店家已確認不含的餐廳</div>}
          {data.top3.length === 0 && (
            <div className="card" data-testid="empty-result">
              <b>目前沒有符合所有限制的餐廳</b>
              {data.strict_mode && <p className="muted">嚴格過敏模式需要店家的確認資料，目前沒有任何餐廳符合。可請該成員改回一般模式（會顯示「資訊不足」警示），或直接聯絡店家。</p>}
            </div>
          )}
          {data.top3.map((r) => <RestaurantCard key={r.restaurant_id} r={r} sessionId={id} />)}
          {data.excluded && data.excluded.length > 0 && (
            <Hint label={`被排除的餐廳（${data.excluded.length}）`}>
              <ul className="plain">{data.excluded.map((e) => <li key={e.restaurant_id}>✗ <b>{e.name}</b>：{e.reasons.join("；")}</li>)}</ul>
              <div className="tiny">只顯示被哪一項條件排除，不會顯示是誰的條件。</div>
            </Hint>
          )}
          <p className="disclaimer">{data.disclaimer}</p>
          <BottomBar>
            <button className="narrow" onClick={generate} disabled={busy}>{busy ? "…" : "重算"}</button>
            {data.top3.length > 0 && <Link className="btn primary" href={`/s/${id}/vote`} data-testid="to-vote">🗳 開始投票</Link>}
          </BottomBar>
        </>
      )}
    </div>
  );
}
