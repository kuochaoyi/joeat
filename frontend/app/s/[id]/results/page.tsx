"use client";
// 畫面 7：推薦結果 — 篩選漏斗摘要、安全規則強化版 Top 3 餐廳卡片、被排除清單與常駐免責聲明
import { RefreshCw, ShieldAlert, Sparkles, Vote } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { RestaurantCard } from "@/components/RestaurantCard";
import {
  Back,
  BottomBar,
  ErrorBox,
  GameButton,
  Hint,
  JourneyHeader,
  SkeletonCard,
} from "@/components/ui";
import { ApiError, getRecommendation, runRecommendation } from "@/lib/api";
import type { Recommendation } from "@/lib/types";

export default function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<Recommendation | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getRecommendation(id)
      .then(setData)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) setMissing(true);
        else setError(e.message);
      });
  }, [id]);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      setData(await runRecommendation(id, true));
      setMissing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  }

  return (
    <div className="space-y-3.5">
      <Back href={`/s/${id}`}>回到聚餐</Back>
      <JourneyHeader current="results" />

      <header>
        <h1 className="m-0 flex items-center gap-2 text-2xl font-black text-ink">
          <Sparkles className="h-6 w-6 text-brand" aria-hidden="true" />
          最適合你們的 3 間
        </h1>
      </header>

      <ErrorBox message={error} />

      {!data && !missing && !error && (
        <>
          <SkeletonCard lines={4} />
          <SkeletonCard lines={3} />
        </>
      )}

      {missing && (
        <section className="rounded-3xl border-2 border-line bg-surface p-5 text-center shadow-card">
          <p className="mt-0 mb-4 text-sm font-bold text-muted">還沒有產生過推薦結果喔！</p>
          <GameButton type="button" variant="primary" className="w-full" onClick={generate} disabled={busy}>
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            {busy ? "計算中…" : "用目前已填的人產生推薦"}
          </GameButton>
        </section>
      )}

      {data && (
        <>
          {data.test_evidence_enabled && (
            <div className="demo-banner" data-testid="demo-banner">
              示範資料模式：部分「店家聲明」是假資料，不能當作真實資訊。
            </div>
          )}

          {/* 篩選漏斗摘要膠囊 */}
          <div
            data-testid="summary"
            className="grid grid-cols-4 gap-1.5 rounded-2xl border border-line bg-surface p-2.5 text-center shadow-sm"
          >
            <div>
              <div className="text-[0.68rem] font-bold text-muted">參與人數</div>
              <div className="text-sm font-black text-ink">{data.participants} 人</div>
            </div>
            <div className="border-l border-line">
              <div className="text-[0.68rem] font-bold text-muted">候選池</div>
              <div className="text-sm font-black text-ink">{data.pool_size} 家</div>
            </div>
            <div className="border-l border-line">
              <div className="text-[0.68rem] font-bold text-muted">已排除</div>
              <div className="text-sm font-black text-crit">{data.excluded_count} 家</div>
            </div>
            <div className="border-l border-line">
              <div className="text-[0.68rem] font-bold text-muted">可推薦</div>
              <div className="text-sm font-black text-ok">{data.eligible_count} 家</div>
            </div>
          </div>

          {data.strict_mode && (
            <div
              data-testid="strict-note"
              className="flex items-start gap-2 rounded-2xl border-l-4 border-warn bg-warn-soft px-3.5 py-2.5 text-xs font-bold text-warn"
            >
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>有成員開啟嚴格過敏模式：只推薦店家已確認不含的餐廳</span>
            </div>
          )}

          {data.top3.length === 0 && (
            <section
              data-testid="empty-result"
              className="rounded-3xl border-2 border-line bg-surface p-5 shadow-card"
            >
              <b className="block text-base font-black text-ink">目前沒有符合所有限制的餐廳</b>
              {data.strict_mode && (
                <p className="mt-2 mb-0 text-sm leading-relaxed text-muted">
                  嚴格過敏模式需要店家的確認資料，目前沒有任何餐廳符合。可請該成員改回一般模式（會顯示「資訊不足」警示），或直接聯絡店家。
                </p>
              )}
            </section>
          )}

          {/* Top 3 推薦卡片 */}
          <div>
            {data.top3.map((r) => (
              <RestaurantCard key={r.restaurant_id} r={r} sessionId={id} />
            ))}
          </div>

          {/* 被排除的餐廳 */}
          {data.excluded && data.excluded.length > 0 && (
            <div className="rounded-2xl border border-line bg-surface px-3.5 py-2 shadow-sm">
              <Hint label={`查看被排除的餐廳（${data.excluded.length} 家）`}>
                <ul className="m-0 list-none space-y-1.5 p-0">
                  {data.excluded.map((e) => (
                    <li key={e.restaurant_id} className="text-xs leading-relaxed">
                      <span className="font-black text-crit">✗ {e.name}</span>：{e.reasons.join("；")}
                    </li>
                  ))}
                </ul>
                <div className="mt-2 border-t border-line pt-1.5 text-[0.72rem] text-muted">
                  只顯示被哪一項條件排除，不會顯示是誰的條件。
                </div>
              </Hint>
            </div>
          )}

          {/* 安全免責聲明（常駐不收合） */}
          <p className="px-1 text-xs leading-relaxed text-muted">{data.disclaimer}</p>

          <BottomBar>
            <GameButton type="button" variant="secondary" onClick={generate} disabled={busy}>
              <RefreshCw className={busy ? "h-4 w-4 animate-spin" : "h-4 w-4"} aria-hidden="true" />
              {busy ? "重算中" : "重算"}
            </GameButton>
            {data.top3.length > 0 && (
              <Link
                href={`/s/${id}/vote`}
                data-testid="to-vote"
                className="flex flex-1 min-h-[48px] items-center justify-center gap-1.5 rounded-2xl bg-gradient-to-b from-brand-2 to-brand px-4 text-[0.96rem] font-extrabold text-white no-underline shadow-game-brand transition active:translate-y-[2px] active:shadow-game-brand-press"
              >
                <Vote className="h-4 w-4" aria-hidden="true" />
                開始最後投票 →
              </Link>
            )}
          </BottomBar>
        </>
      )}
    </div>
  );
}
