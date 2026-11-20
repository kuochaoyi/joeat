"use client";
// 審核後台：Python Dash 互動式數據分析頁（/ops/analytics）
import { ExternalLink, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { OpsShell } from "@/components/OpsShell";
import { ErrorBox, GameButton } from "@/components/ui";
import { createDashSession, getDashUrl } from "@/lib/opsApi";

function AnalyticsView() {
  const [ready, setReady] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const ensureSession = useCallback(async () => {
    setError(null);
    try {
      await createDashSession();
      setReady(true);
      setReloadTick((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    ensureSession();
  }, [ensureSession]);

  const dashUrl = getDashUrl();

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-3xl border-2 border-line bg-surface px-5 py-4 shadow-card">
        <div>
          <h2 className="m-0 text-base font-black text-ink">Python Dash 即時數據儀表板</h2>
          <p className="m-0 mt-0.5 text-xs text-muted">
            由後端 FastAPI 掛載 Plotly Dash 提供互動式圖表，並透過管理員簽章 Cookie 保護存取權限。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <GameButton type="button" variant="secondary" size="sm" onClick={ensureSession}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            重新載入
          </GameButton>
          <a
            href={dashUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-h-[38px] items-center gap-1.5 rounded-xl border-2 border-line bg-surface px-3 text-sm font-bold text-ink no-underline transition hover:border-brand hover:text-brand"
          >
            <ExternalLink className="h-4 w-4" aria-hidden="true" />
            在新分頁開啟
          </a>
        </div>
      </div>

      <ErrorBox message={error} />

      <div className="overflow-hidden rounded-3xl border-2 border-line bg-surface shadow-card">
        {ready ? (
          <iframe
            key={reloadTick}
            src={dashUrl}
            title="揪呷 JOEAT Python Dash 數據分析儀表板"
            className="h-[calc(100vh-230px)] min-h-[680px] w-full border-0"
          />
        ) : (
          <div className="flex h-[500px] items-center justify-center text-sm font-bold text-muted">
            正在建立 Python Dash 驗證工作階段…
          </div>
        )}
      </div>
    </div>
  );
}

export default function OpsAnalyticsPage() {
  return (
    <OpsShell active="analytics">
      <AnalyticsView />
    </OpsShell>
  );
}
