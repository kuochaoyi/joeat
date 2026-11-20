"use client";
// 獨立管理員登入頁（/ops/login）：沿用 OPS_API_KEY + 稽核姓名驗證，並同步核發 Python Dash 簽章 Cookie。
import { Eye, EyeOff, KeyRound, ShieldCheck, UserCheck } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";

import { ErrorBox, GameButton, Logo } from "@/components/ui";
import {
  createDashSession,
  getLocalAdmins,
  getOpsAuth,
  getOpsSummary,
  isLocalAdminDisabled,
  type LocalAdminRecord,
  setOpsAuth,
} from "@/lib/opsApi";

function safeNextPath(raw: string | null): string {
  if (!raw || !raw.startsWith("/ops") || raw.startsWith("/ops/login")) {
    return "/ops";
  }
  return raw;
}

function OpsLoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = safeNextPath(searchParams.get("next"));

  const [key, setKey] = useState("");
  const [user, setUser] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [admins, setAdmins] = useState<LocalAdminRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // 若此分頁已登入則直接進入後台
    if (getOpsAuth()) {
      router.replace(nextPath);
      return;
    }
    setAdmins(getLocalAdmins().filter((a) => a.active));
  }, [nextPath, router]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmedUser = user.trim();
    if (!key || trimmedUser.length < 2) {
      setError("請輸入金鑰與至少 2 個字的管理員姓名。");
      return;
    }
    if (isLocalAdminDisabled(trimmedUser)) {
      setError(`管理員「${trimmedUser}」目前已停用，無法由此裝置登入。`);
      return;
    }
    setBusy(true);
    setError(null);
    setOpsAuth({ key, user: trimmedUser });
    try {
      await getOpsSummary();
      await createDashSession();
      router.replace(nextPath);
    } catch (err) {
      setOpsAuth(null);
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <div className="ops-login-root flex min-h-screen items-center justify-center bg-bg px-4 py-10">
      <div className="w-full max-w-[440px] space-y-5">
        {/* 品牌識別標頭 */}
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-2 to-brand p-6 text-white shadow-hero">
          <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-white/15 blur-xl" />
          <div className="relative flex items-center gap-4">
            <div className="rounded-2xl bg-white/20 p-1.5 backdrop-blur-sm">
              <Logo size={48} />
            </div>
            <div>
              <div className="inline-flex items-center gap-1 rounded-full bg-white/20 px-2.5 py-0.5 text-[0.72rem] font-extrabold tracking-wide">
                <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                營運審核系統
              </div>
              <h1 className="m-0 mt-1 text-2xl font-black tracking-tight">揪呷 · 管理員登入</h1>
              <p className="m-0 text-xs font-medium text-white/90">
                審核店家聲明、使用者回報與 Python Dash 數據分析
              </p>
            </div>
          </div>
        </div>

        {/* 登入表單卡片 */}
        <form
          onSubmit={handleSubmit}
          className="space-y-4 rounded-3xl border-2 border-line bg-surface p-6 shadow-card"
        >
          <p className="m-0 rounded-2xl bg-chip px-3.5 py-2.5 text-xs leading-relaxed text-muted">
            目前為試辦階段存取控制：使用共用金鑰驗證，您的姓名將寫入稽核紀錄，憑證僅保留於此瀏覽器分頁（sessionStorage）。
          </p>

          <div>
            <label htmlFor="ops-key" className="mb-1.5 flex items-center gap-1.5 text-sm font-extrabold text-ink">
              <KeyRound className="h-4 w-4 text-brand" aria-hidden="true" />
              管理員金鑰（OPS_API_KEY）
            </label>
            <div className="relative">
              <input
                id="ops-key"
                type={showKey ? "text" : "password"}
                autoComplete="current-password"
                required
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="請輸入審核後台金鑰"
                className="h-12 w-full rounded-2xl border-2 border-line bg-bg pl-3.5 pr-12 text-sm font-semibold text-ink transition focus:border-brand focus:bg-surface focus:outline-none"
              />
              <button
                type="button"
                aria-label={showKey ? "隱藏金鑰" : "顯示金鑰"}
                onClick={() => setShowKey((v) => !v)}
                className="absolute right-2 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-xl text-muted transition hover:bg-chip hover:text-ink cursor-pointer"
              >
                {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <div>
            <label htmlFor="ops-user" className="mb-1.5 flex items-center gap-1.5 text-sm font-extrabold text-ink">
              <UserCheck className="h-4 w-4 text-brand" aria-hidden="true" />
              管理員姓名
            </label>
            <input
              id="ops-user"
              type="text"
              autoComplete="name"
              required
              minLength={2}
              value={user}
              onChange={(e) => setUser(e.target.value)}
              placeholder="例如：審核員小明（至少 2 字）"
              className="h-12 w-full rounded-2xl border-2 border-line bg-bg px-3.5 text-sm font-semibold text-ink transition focus:border-brand focus:bg-surface focus:outline-none"
            />
            {admins.length > 0 && (
              <div className="mt-2">
                <span className="mb-1 block text-[0.72rem] font-bold text-muted">快速選取啟用中的管理員：</span>
                <div className="flex flex-wrap gap-1.5">
                  {admins.map((a) => (
                    <button
                      key={a.id}
                      type="button"
                      onClick={() => setUser(a.name)}
                      className="rounded-full border border-line bg-chip px-2.5 py-1 text-xs font-bold text-ink transition hover:border-brand hover:text-brand cursor-pointer"
                    >
                      {a.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <ErrorBox message={error} />

          <GameButton
            type="submit"
            variant="primary"
            className="w-full"
            disabled={busy || !key || user.trim().length < 2}
          >
            {busy ? "驗證登入中…" : "登入審核後台"}
          </GameButton>
        </form>
      </div>
    </div>
  );
}

export default function OpsLoginPage() {
  return (
    <Suspense
      fallback={
        <div className="ops-login-root flex min-h-screen items-center justify-center bg-bg text-sm font-bold text-muted">
          載入登入頁面中…
        </div>
      }
    >
      <OpsLoginForm />
    </Suspense>
  );
}
