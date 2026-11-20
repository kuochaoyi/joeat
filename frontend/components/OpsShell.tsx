"use client";
// 審核後台共用外殼：登入守衛（未登入自動導向 /ops/login）與響應式側邊欄／行動抽屜選單。
import {
  AlertTriangle,
  BarChart3,
  ClipboardCheck,
  Flag,
  LayoutDashboard,
  LogOut,
  Menu,
  ShieldAlert,
  UserCog,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useCallback, useEffect, useState } from "react";

import { Logo } from "@/components/ui";
import { cn } from "@/lib/cn";
import {
  clearDashSession,
  getOpsAuth,
  getOpsSummary,
  type OpsAuth,
  type OpsCounts,
  setOpsAuth,
} from "@/lib/opsApi";

type NavKey = "dashboard" | "analytics" | "declarations" | "claims" | "reports" | "incidents" | "admins";

interface NavItem {
  key: NavKey;
  href: string;
  label: string;
  Icon: typeof LayoutDashboard;
  badgeKey?: keyof OpsCounts;
}

const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "總覽與數據",
    items: [
      { key: "dashboard", href: "/ops", label: "總覽儀表板", Icon: LayoutDashboard },
      { key: "analytics", href: "/ops/analytics", label: "數據分析（Dash）", Icon: BarChart3 },
    ],
  },
  {
    title: "審核作業",
    items: [
      { key: "declarations", href: "/ops/declarations", label: "聲明審核", Icon: ClipboardCheck, badgeKey: "pending_declarations" },
      { key: "claims", href: "/ops/claims", label: "認領與驗證", Icon: ShieldAlert },
      { key: "reports", href: "/ops/reports", label: "使用者回報", Icon: Flag, badgeKey: "open_reports" },
      { key: "incidents", href: "/ops/incidents", label: "事故處理", Icon: AlertTriangle, badgeKey: "open_incidents" },
    ],
  },
  {
    title: "系統管理",
    items: [
      { key: "admins", href: "/ops/admins", label: "管理員帳號", Icon: UserCog },
    ],
  },
];

const PAGE_TITLES: Record<NavKey, string> = {
  dashboard: "總覽儀表板",
  analytics: "數據分析（Python Dash）",
  declarations: "聲明審核",
  claims: "認領與驗證",
  reports: "使用者回報",
  incidents: "事故處理",
  admins: "管理員帳號管理",
};

export function OpsShell({ active, children }: { active: NavKey; children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [auth, setAuth] = useState<OpsAuth | null | undefined>(undefined);
  const [counts, setCounts] = useState<OpsCounts | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const redirectToLogin = useCallback(() => {
    const next = pathname && pathname.startsWith("/ops") ? `?next=${encodeURIComponent(pathname)}` : "";
    router.replace(`/ops/login${next}`);
  }, [pathname, router]);

  useEffect(() => {
    const cur = getOpsAuth();
    if (!cur) {
      setAuth(null);
      redirectToLogin();
      return;
    }
    setAuth(cur);
    getOpsSummary()
      .then((res) => setCounts(res.counts))
      .catch((err: unknown) => {
        const status = typeof err === "object" && err && "status" in err ? (err as { status: number }).status : 0;
        if (status === 401) {
          setOpsAuth(null);
          setAuth(null);
          redirectToLogin();
        }
      });
  }, [redirectToLogin]);

  // 切換路由時自動收合行動版抽屜
  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  // 按下 Esc 鍵關閉行動版抽屜
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  async function handleLogout() {
    setOpsAuth(null);
    await clearDashSession();
    setAuth(null);
    router.replace("/ops/login");
  }

  if (auth === undefined || !auth) {
    return (
      <div className="ops-shell-root flex min-h-screen items-center justify-center bg-bg text-sm font-bold text-muted">
        驗證管理員身分中…
      </div>
    );
  }

  const sidebarContent = (
    <div className="flex h-full flex-col bg-surface">
      {/* 品牌頂部 */}
      <div className="flex items-center justify-between border-b border-line px-4 py-4">
        <Link href="/ops" className="flex items-center gap-2.5 no-underline">
          <Logo size={36} />
          <div>
            <div className="text-base font-black leading-tight text-ink">揪呷 JOEAT</div>
            <div className="text-[0.72rem] font-bold text-brand">營運審核後台</div>
          </div>
        </Link>
        <button
          type="button"
          aria-label="關閉選單"
          onClick={() => setDrawerOpen(false)}
          className="flex h-9 w-9 items-center justify-center rounded-xl text-muted hover:bg-chip hover:text-ink lg:hidden cursor-pointer"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* 選單分組 */}
      <nav aria-label="管理員主選單" className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
        {NAV_GROUPS.map((group) => (
          <div key={group.title}>
            <div className="mb-1.5 px-3 text-[0.7rem] font-extrabold tracking-wider text-muted">
              {group.title}
            </div>
            <ul className="m-0 list-none space-y-1 p-0">
              {group.items.map(({ key, href, label, Icon, badgeKey }) => {
                const isActive = active === key;
                const badgeCount = badgeKey && counts ? counts[badgeKey] : 0;
                return (
                  <li key={key}>
                    <Link
                      href={href}
                      aria-current={isActive ? "page" : undefined}
                      className={cn(
                        "flex items-center justify-between rounded-2xl px-3 py-2.5 text-sm font-bold no-underline transition-all",
                        isActive
                          ? "bg-brand-soft text-brand shadow-sm ring-1 ring-brand/25"
                          : "text-ink/85 hover:bg-chip hover:text-ink"
                      )}
                    >
                      <span className="flex items-center gap-2.5">
                        <Icon className={cn("h-4 w-4 shrink-0", isActive ? "text-brand" : "text-muted")} aria-hidden="true" />
                        <span>{label}</span>
                      </span>
                      {badgeCount > 0 && (
                        <span
                          className={cn(
                            "rounded-full px-2 py-0.5 text-[0.7rem] font-black",
                            key === "incidents" ? "bg-crit text-white" : "bg-brand text-white"
                          )}
                        >
                          {badgeCount}
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* 底部登入管理員與登出 */}
      <div className="border-t border-line p-3">
        <div className="flex items-center justify-between gap-2 rounded-2xl bg-chip px-3 py-2.5">
          <div className="min-w-0">
            <div className="truncate text-xs font-extrabold text-ink">{auth.user}</div>
            <div className="flex items-center gap-1 text-[0.68rem] font-semibold text-ok">
              <span className="h-1.5 w-1.5 rounded-full bg-ok" aria-hidden="true" />
              已驗證管理員
            </div>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            title="登出後台"
            className="inline-flex items-center gap-1 rounded-xl border border-line bg-surface px-2.5 py-1.5 text-xs font-bold text-muted transition hover:border-crit/40 hover:text-crit cursor-pointer"
          >
            <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
            登出
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="ops-shell-root flex min-h-screen bg-bg text-ink">
      {/* 桌面版固定側邊欄 */}
      <aside className="hidden w-[260px] shrink-0 border-r border-line lg:sticky lg:top-0 lg:block lg:h-screen">
        {sidebarContent}
      </aside>

      {/* 行動版抽屜選單 */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden" role="dialog" aria-modal="true" aria-label="管理員選單">
          <div
            className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs"
            onClick={() => setDrawerOpen(false)}
          />
          <aside className="relative z-10 h-full w-[270px] max-w-[82vw] border-r border-line shadow-2xl">
            {sidebarContent}
          </aside>
        </div>
      )}

      {/* 右側主內容區 */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* 頂部標題列 */}
        <header className="sticky top-0 z-20 flex items-center justify-between border-b border-line bg-surface/90 px-4 py-3 backdrop-blur-md lg:px-8">
          <div className="flex items-center gap-3">
            <button
              type="button"
              aria-label="開啟選單"
              onClick={() => setDrawerOpen(true)}
              className="flex h-10 w-10 items-center justify-center rounded-xl border border-line bg-bg text-ink lg:hidden cursor-pointer"
            >
              <Menu className="h-5 w-5" />
            </button>
            <h1 className="m-0 text-lg font-black tracking-tight text-ink lg:text-xl">
              {PAGE_TITLES[active]}
            </h1>
          </div>
          <div className="hidden items-center gap-2 text-xs font-semibold text-muted sm:flex">
            <span>操作者：</span>
            <b className="text-ink">{auth.user}</b>
          </div>
        </header>

        {/* 內容容器 */}
        <div className="mx-auto w-full max-w-[1200px] flex-1 px-4 py-6 lg:px-8">
          {children}
        </div>
      </div>
    </div>
  );
}
