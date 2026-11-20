"use client";
// 審核後台：總覽儀表板（/ops）
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  ClipboardCheck,
  Flag,
  RefreshCw,
  ShieldCheck,
  Store,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { OpsShell } from "@/components/OpsShell";
import { ErrorBox, GameButton, SkeletonCard } from "@/components/ui";
import { getOpsSummary, type OpsSummary } from "@/lib/opsApi";

function DashboardContent() {
  const [data, setData] = useState<OpsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getOpsSummary()
      .then((res) => setData(res))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && !data) {
    return (
      <div className="space-y-4">
        <SkeletonCard lines={2} />
        <SkeletonCard lines={4} />
      </div>
    );
  }

  const c = data?.counts;
  const stats = [
    {
      label: "待審店家聲明",
      value: c?.pending_declarations ?? 0,
      href: "/ops/declarations",
      Icon: ClipboardCheck,
      accent: (c?.pending_declarations ?? 0) > 0 ? "text-warn bg-warn-soft" : "text-ok bg-ok-soft",
      hint: "店家已送出待人工覆核",
    },
    {
      label: "待處理使用者回報",
      value: c?.open_reports ?? 0,
      href: "/ops/reports",
      Icon: Flag,
      accent: (c?.open_reports ?? 0) > 0 ? "text-warn bg-warn-soft" : "text-ok bg-ok-soft",
      hint: "查證後可駁回或升級事故",
    },
    {
      label: "未結案事故",
      value: c?.open_incidents ?? 0,
      href: "/ops/incidents",
      Icon: AlertTriangle,
      accent: (c?.open_incidents ?? 0) > 0 ? "text-crit bg-crit-soft" : "text-ok bg-ok-soft",
      hint: "已觸發正向聲明暫停",
    },
    {
      label: "進行中／已驗證認領",
      value: c?.active_claims ?? 0,
      href: "/ops/claims",
      Icon: ShieldCheck,
      accent: "text-brand bg-brand-soft",
      hint: "店家邀請與身分驗證紀錄",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="m-0 text-xl font-black text-ink">歡迎回來，{data?.user ?? "管理員"}</h2>
          <p className="m-0 mt-0.5 text-xs font-medium text-muted">
            目前系統共收錄 <b>{c?.total_restaurants ?? 0}</b> 家餐廳、累計 <b>{c?.total_sessions ?? 0}</b> 場聚餐開團。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <GameButton type="button" variant="secondary" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
            重新整理
          </GameButton>
          <Link
            href="/ops/analytics"
            className="inline-flex min-h-[38px] items-center gap-1.5 rounded-xl bg-brand px-3.5 text-sm font-bold text-white no-underline shadow-sm transition hover:bg-brand-dark"
          >
            <BarChart3 className="h-4 w-4" aria-hidden="true" />
            開啟 Python Dash 分析
          </Link>
        </div>
      </div>

      <ErrorBox message={error} />

      {/* 四張核心 KPI 卡片 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map(({ label, value, href, Icon, accent, hint }) => (
          <Link
            key={label}
            href={href}
            className="group flex flex-col justify-between rounded-3xl border-2 border-line bg-surface p-5 no-underline shadow-card transition hover:-translate-y-0.5 hover:border-brand/50 hover:shadow-card-pop"
          >
            <div className="flex items-start justify-between gap-2">
              <span className="text-xs font-extrabold text-muted">{label}</span>
              <span className={`flex h-9 w-9 items-center justify-center rounded-2xl ${accent}`}>
                <Icon className="h-4 w-4" aria-hidden="true" />
              </span>
            </div>
            <div className="mt-3 flex items-baseline justify-between">
              <span className="text-3xl font-black text-ink">{value}</span>
              <ArrowRight className="h-4 w-4 text-muted transition-transform group-hover:translate-x-1 group-hover:text-brand" aria-hidden="true" />
            </div>
            <div className="mt-1 text-[0.72rem] font-medium text-muted">{hint}</div>
          </Link>
        ))}
      </div>

      {/* 最新待審聲明摘要 + 系統概況 */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <section className="rounded-3xl border-2 border-line bg-surface p-5 shadow-card lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="m-0 text-base font-black text-ink">最新待審聲明</h3>
            <Link href="/ops/declarations" className="text-xs font-bold text-brand no-underline hover:underline">
              查看全部 →
            </Link>
          </div>
          {data && data.recent_pending_declarations.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="ops">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>餐廳</th>
                    <th>驗證</th>
                    <th>矛盾</th>
                    <th>送出時間</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data.recent_pending_declarations.map((r) => (
                    <tr key={r.declaration_id}>
                      <td>{r.declaration_id}</td>
                      <td>
                        {r.restaurant} {r.is_demo && <span className="effect possible">示範</span>}
                      </td>
                      <td>{r.verification_level === "strong" ? "強" : "基本"}</td>
                      <td>
                        {r.conflict_count > 0 ? <b className="text-crit">{r.conflict_count}</b> : 0}
                      </td>
                      <td>{r.submitted_at ? new Date(r.submitted_at).toLocaleString("zh-TW") : "—"}</td>
                      <td>
                        <Link
                          href={`/ops/declarations/${r.declaration_id}`}
                          className="font-bold text-brand no-underline hover:underline"
                        >
                          審核 →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded-2xl bg-chip px-4 py-8 text-center text-sm font-semibold text-muted">
              目前沒有待審的店家聲明，全部處理完畢！
            </div>
          )}
        </section>

        <section className="space-y-3 rounded-3xl border-2 border-line bg-surface p-5 shadow-card">
          <h3 className="m-0 text-base font-black text-ink">系統概況與快速入口</h3>
          <div className="space-y-2.5">
            <div className="flex items-center justify-between rounded-2xl bg-chip px-3.5 py-3">
              <span className="flex items-center gap-2 text-xs font-bold text-muted">
                <Store className="h-4 w-4 text-brand" aria-hidden="true" />
                收錄餐廳總數
              </span>
              <b className="text-base font-black text-ink">{c?.total_restaurants ?? 0}</b>
            </div>
            <div className="flex items-center justify-between rounded-2xl bg-chip px-3.5 py-3">
              <span className="flex items-center gap-2 text-xs font-bold text-muted">
                <Users className="h-4 w-4 text-brand" aria-hidden="true" />
                累計聚餐開團
              </span>
              <b className="text-base font-black text-ink">{c?.total_sessions ?? 0}</b>
            </div>
          </div>
          <div className="space-y-2 pt-1">
            <Link
              href="/ops/analytics"
              className="flex items-center justify-between rounded-2xl border border-brand/30 bg-brand-soft px-3.5 py-2.5 text-sm font-bold text-brand no-underline transition hover:bg-brand hover:text-white"
            >
              <span>檢視 Python Dash 互動圖表</span>
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
            <Link
              href="/ops/claims"
              className="flex items-center justify-between rounded-2xl border border-line bg-bg px-3.5 py-2.5 text-sm font-bold text-ink no-underline transition hover:border-brand/50"
            >
              <span>發送餐廳認領邀請</span>
              <ArrowRight className="h-4 w-4 text-muted" aria-hidden="true" />
            </Link>
            <Link
              href="/ops/admins"
              className="flex items-center justify-between rounded-2xl border border-line bg-bg px-3.5 py-2.5 text-sm font-bold text-ink no-underline transition hover:border-brand/50"
            >
              <span>管理員帳號與名冊</span>
              <ArrowRight className="h-4 w-4 text-muted" aria-hidden="true" />
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}

export default function OpsDashboardPage() {
  return (
    <OpsShell active="dashboard">
      <DashboardContent />
    </OpsShell>
  );
}
