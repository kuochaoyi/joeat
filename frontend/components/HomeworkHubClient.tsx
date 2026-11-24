"use client";
// 作業導覽首頁互動元件：彙整所有主題入口連結、快速跳轉工具、後端連線檢查與操作小幫手
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  BookOpen,
  Check,
  CheckCircle2,
  ClipboardCopy,
  Coffee,
  Compass,
  ExternalLink,
  FileCode2,
  Flame,
  GraduationCap,
  HelpCircle,
  Keyboard,
  KeyRound,
  LifeBuoy,
  MapPin,
  Pause,
  Play,
  PlayCircle,
  RefreshCw,
  Server,
  ShieldAlert,
  ShieldCheck,
  Soup,
  Sparkles,
  Store,
  Terminal,
  Users,
  UtensilsCrossed,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { useToast } from "@/components/Toast";
import { GameButton, Logo } from "@/components/ui";
import { API_BASE, getLocations } from "@/lib/api";

const GITHUB_REPO_URL = "https://github.com/kuochaoyi/joeat";

type TopicLinkItem = {
  id: string;
  title: string;
  href: string;
  external?: boolean;
  badge: string;
  badgeTone: "brand" | "ok" | "warn" | "neutral";
  summary: string;
  highlights: string[];
  subLinks?: { label: string; href: string; external?: boolean }[];
  icon: "utensils" | "shield" | "chart" | "report" | "api" | "store" | "github";
};

const TOPIC_LINKS: TopicLinkItem[] = [
  {
    id: "create-session",
    title: "建立聚餐開團（前台 MVP）",
    href: "/create",
    badge: "核心體驗",
    badgeTone: "brand",
    summary:
      "體驗 2–20 人聚餐的 30 秒開團流程：設定固定時間或投票、鹽埕區地圖選點與攜伴需求，接著收集硬限制與料理偏好並產生 Top 3 推薦。",
    highlights: ["硬限制優先排除", "偏好加權排序", "安全警示不誤判"],
    icon: "utensils",
  },
  {
    id: "ops-dashboard",
    title: "審核後台總覽（管理員系統）",
    href: "/ops",
    badge: "管理後台",
    badgeTone: "ok",
    summary:
      "管理店家自填聲明、待審佇列、認領驗證連結、使用者回報與緊急煞車事故；內建桌面側邊欄與行動抽屜導覽。",
    highlights: ["待審聲明核准與退件", "使用者回報查證", "本機管理員名冊"],
    subLinks: [
      { label: "管理員登入", href: "/ops/login" },
      { label: "聲明審核", href: "/ops/declarations" },
      { label: "認領驗證", href: "/ops/claims" },
    ],
    icon: "shield",
  },
  {
    id: "ops-analytics",
    title: "營運數據分析（Python Dash）",
    href: "/ops/analytics",
    badge: "數據視覺化",
    badgeTone: "warn",
    summary:
      "以響應式介面嵌入 FastAPI 掛載的 Plotly Dash 互動儀表板，呈現聲明狀態分布、候選池比例與近 14 日開團參與趨勢。",
    highlights: ["5 張核心指標卡", "4 張互動式圖表", "示範資料切換"],
    icon: "chart",
  },
  {
    id: "tech-reports",
    title: "技術統計報告（專案架構指標）",
    href: "/tech-reports",
    badge: "即時掃描",
    badgeTone: "neutral",
    summary:
      "每次請求即時掃描專案原始碼、Git 提交紀錄、前後端相依套件與目錄規模，方便課程報告時檢視系統全貌。",
    highlights: ["程式碼行數統計", "Git 歷史分析", "前後端套件總覽"],
    icon: "report",
  },
  {
    id: "merchant-claim",
    title: "店家自填聲明流程（認領邀請）",
    href: "/ops/claims",
    badge: "店家端",
    badgeTone: "ok",
    summary:
      "餐廳業者透過一次性連結（/m/{token}）回報過敏原與飲食限制；先由此頁邀請餐廳產生連結，即可開啟店家填寫頁。",
    highlights: ["一次性驗證連結", "事實陳述切結", "審核通過才生效"],
    icon: "store",
  },
  {
    id: "backend-api-docs",
    title: "後端互動 API 文件（Swagger）",
    href: `${API_BASE}/docs`,
    external: true,
    badge: "後端介面",
    badgeTone: "neutral",
    summary:
      "由 FastAPI 自動產生的互動式 REST API 文件，可直接測試開團、推薦引擎、店家聲明與後台審核等所有端點。",
    highlights: ["即時端點測試", "請求與回應結構", "需先啟動後端服務"],
    icon: "api",
  },
  {
    id: "github-repo",
    title: "GitHub 專案儲存庫（原始碼）",
    href: GITHUB_REPO_URL,
    external: true,
    badge: "開源原始碼",
    badgeTone: "brand",
    summary:
      "瀏覽揪呷 JOEAT 完整前後端程式碼、架構文件、推薦引擎規則合約、UI 設計原則與版本提交紀錄。",
    highlights: ["前後端完整原始碼", "架構與設計文件", "提交紀錄與測試"],
    subLinks: [
      { label: "專案說明（README）", href: `${GITHUB_REPO_URL}#readme`, external: true },
      { label: "設計文件（docs）", href: `${GITHUB_REPO_URL}/tree/main/docs`, external: true },
    ],
    icon: "github",
  },
];

const QUICK_COMMANDS = [
  {
    label: "1. 啟動內嵌資料庫並寫入種子資料（後端）",
    cmd: "cd pj_joeat/joeat/backend && python scripts/dev_postgres.py && python scripts/seed.py --reset",
  },
  {
    label: "2. 啟動後端伺服器（Port 8000）",
    cmd: "cd pj_joeat/joeat/backend && python -m uvicorn app.main:app --port 8000",
  },
  {
    label: "3. 跑固定展示劇本「高中同學聚餐」並取得聚餐連結",
    cmd: "cd pj_joeat/joeat/backend && python scripts/demo.py",
  },
  {
    label: "4. 啟動前端開發伺服器（Port 3000）",
    cmd: "cd pj_joeat/joeat/frontend && npm run dev",
  },
];

function GitHubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2Z" />
    </svg>
  );
}

function TopicIcon({ kind }: { kind: TopicLinkItem["icon"] }) {
  const cls = "h-5 w-5 text-brand";
  switch (kind) {
    case "utensils":
      return <UtensilsCrossed className={cls} aria-hidden="true" />;
    case "shield":
      return <ShieldCheck className={cls} aria-hidden="true" />;
    case "chart":
      return <BarChart3 className={cls} aria-hidden="true" />;
    case "report":
      return <FileCode2 className={cls} aria-hidden="true" />;
    case "store":
      return <Store className={cls} aria-hidden="true" />;
    case "api":
      return <Terminal className={cls} aria-hidden="true" />;
    case "github":
      return <GitHubMark className={cls} />;
  }
}

function badgeClass(tone: TopicLinkItem["badgeTone"]) {
  switch (tone) {
    case "brand":
      return "bg-brand-soft text-brand-dark";
    case "ok":
      return "bg-ok-soft text-ok";
    case "warn":
      return "bg-warn-soft text-warn";
    default:
      return "bg-chip text-muted";
  }
}

export function HomeworkHubClient() {
  const router = useRouter();
  const { showToast } = useToast();

  // 快速跳轉小工具狀態
  const [sessionId, setSessionId] = useState("");
  const [merchantToken, setMerchantToken] = useState("");

  // 後端連線檢查狀態
  const [apiState, setApiState] = useState<"checking" | "online" | "offline">("checking");
  const [locationCount, setLocationCount] = useState<number | null>(null);

  // 小幫手手風琴「全部展開／收合」狀態
  const accordionRef = useRef<HTMLDivElement | null>(null);
  const [allExpanded, setAllExpanded] = useState(false);

  // 背景動畫暫停／播放控制（符合 WCAG 2.2.2 Pause, Stop, Hide）
  const [motionPaused, setMotionPaused] = useState(false);

  const checkBackend = useCallback(async () => {
    setApiState("checking");
    try {
      const res = await getLocations();
      setLocationCount(res.locations.length);
      setApiState("online");
    } catch {
      setLocationCount(null);
      setApiState("offline");
    }
  }, []);

  useEffect(() => {
    void checkBackend();
  }, [checkBackend]);

  function syncAccordionExpandedState() {
    const container = accordionRef.current;
    if (!container) return;
    const items = Array.from(container.querySelectorAll<HTMLDetailsElement>(":scope > details"));
    setAllExpanded(items.length > 0 && items.every((d) => d.open));
  }

  function handleToggleAllHelpers() {
    const container = accordionRef.current;
    if (!container) return;
    const nextOpen = !allExpanded;
    const items = container.querySelectorAll<HTMLDetailsElement>(":scope > details");
    items.forEach((d) => {
      d.open = nextOpen;
    });
    setAllExpanded(nextOpen);
  }

  function handleJumpSession(e: FormEvent) {
    e.preventDefault();
    const cleaned = sessionId.trim();
    if (!cleaned) return;
    router.push(`/s/${encodeURIComponent(cleaned)}`);
  }

  function handleJumpMerchant(e: FormEvent) {
    e.preventDefault();
    const cleaned = merchantToken.trim();
    if (!cleaned) return;
    router.push(`/m/${encodeURIComponent(cleaned)}`);
  }

  async function copyCommand(cmd: string) {
    try {
      await navigator.clipboard.writeText(cmd);
      showToast("已複製指令到剪貼簿", "ok");
    } catch {
      showToast("無法自動複製，請手動選取指令", "info");
    }
  }

  return (
    <div
      className="homework-hub-root relative min-h-screen overflow-x-clip bg-bg pb-16"
      data-motion={motionPaused ? "paused" : "running"}
    >
      {/* 背景動態氛圍層：柔和漸層光暈與聚餐主題浮動微圖示（對輔助科技隱藏） */}
      <div className="hub-bg-stage" aria-hidden="true">
        <div className="hub-orb hub-orb-1" />
        <div className="hub-orb hub-orb-2" />
        <div className="hub-orb hub-orb-3" />

        <UtensilsCrossed
          className="hub-float-icon left-[5%] top-[14%] h-10 w-10"
          style={{ ["--float-duration" as string]: "9s", ["--float-delay" as string]: "0s" }}
        />
        <Soup
          className="hub-float-icon right-[7%] top-[20%] h-11 w-11"
          style={{ ["--float-duration" as string]: "11s", ["--float-delay" as string]: "-2s" }}
        />
        <Flame
          className="hub-float-icon left-[8%] top-[54%] h-9 w-9"
          style={{ ["--float-duration" as string]: "10s", ["--float-delay" as string]: "-4s" }}
        />
        <MapPin
          className="hub-float-icon right-[9%] top-[60%] h-10 w-10"
          style={{ ["--float-duration" as string]: "12s", ["--float-delay" as string]: "-1.5s" }}
        />
        <Coffee
          className="hub-float-icon left-[16%] bottom-[10%] h-9 w-9"
          style={{ ["--float-duration" as string]: "10.5s", ["--float-delay" as string]: "-3s" }}
        />
        <Sparkles
          className="hub-float-icon right-[14%] bottom-[12%] h-8 w-8"
          style={{ ["--float-duration" as string]: "8.5s", ["--float-delay" as string]: "-5s" }}
        />
      </div>

      <div className="relative z-10 mx-auto max-w-[1120px] space-y-8 px-4 pt-6 sm:px-6 md:pt-8">
        {/* 無障礙跳過導覽連結 */}
        <a
          href="#topics"
          className="visually-hidden fixed left-4 top-4 z-50 rounded-xl bg-brand px-4 py-2 text-sm font-bold text-white shadow-hero no-underline"
        >
          跳到主題功能連結
        </a>

        {/* 頂部作業展示 Hero 區 */}
        <header className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-2 to-brand p-6 text-white shadow-hero md:p-8">
          <div className="hub-hero-orb pointer-events-none absolute -right-12 -top-12 h-48 w-48 rounded-full bg-white/15 blur-2xl" />
          <div className="hub-hero-orb pointer-events-none absolute -bottom-16 left-1/3 h-40 w-40 rounded-full bg-black/10 blur-2xl" />

          <div className="relative flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-white/20 px-3 py-1 text-xs font-extrabold tracking-wide backdrop-blur-sm">
                  <GraduationCap className="h-3.5 w-3.5" aria-hidden="true" />
                  [商管軟體設計-MIS593]-Team 1
                </span>
                <span className="inline-flex items-center gap-1 rounded-full bg-black/15 px-3 py-1 text-xs font-bold">
                  <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                  預設導覽入口（/index）
                </span>
              </div>

              <div className="flex items-center gap-4">
                <div className="shrink-0 rounded-2xl bg-white/20 p-1.5 backdrop-blur-sm">
                  <Logo size={54} />
                </div>
                <div>
                  <h1 className="m-0 text-2xl font-black tracking-tight sm:text-3xl">
                    揪呷 JOEAT — 作業總覽與導覽頁
                  </h1>
                  <p className="m-0 mt-1 max-w-2xl text-sm font-medium text-white/95 sm:text-base">
                    專為 2–20 人聚餐設計的 LINE Bot + LIFF 決策工具（高雄市鹽埕區 31 家真實餐廳資料）。從這裡可快速前往各主題功能頁、檢視系統報告，或參考操作小幫手進行展示。
                  </p>
                </div>
              </div>
            </div>

            <div className="flex shrink-0 flex-wrap gap-2.5 md:flex-col">
              <Link
                href="/create"
                className="inline-flex min-h-[46px] items-center justify-center gap-2 rounded-2xl bg-white px-5 text-sm font-black text-brand shadow-card no-underline transition hover:bg-brand-soft"
              >
                <UtensilsCrossed className="h-4 w-4" aria-hidden="true" />
                立即開始建立聚餐
              </Link>
              <Link
                href="/ops"
                className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-2xl border-2 border-white/40 bg-white/15 px-5 text-sm font-extrabold text-white no-underline backdrop-blur-sm transition hover:bg-white/25"
              >
                <ShieldCheck className="h-4 w-4" aria-hidden="true" />
                進入管理員審核後台
              </Link>
              <a
                href={GITHUB_REPO_URL}
                target="_blank"
                rel="noreferrer"
                className="inline-flex min-h-[42px] items-center justify-center gap-2 rounded-2xl border-2 border-white/30 bg-black/15 px-5 text-xs font-extrabold text-white no-underline backdrop-blur-sm transition hover:bg-black/25"
              >
                <GitHubMark className="h-4 w-4" />
                GitHub 專案儲存庫
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
            </div>
          </div>

          {/* 頁內章節快速導覽 */}
          <nav
            aria-label="作業頁面章節"
            className="relative mt-6 flex flex-wrap items-center gap-2 border-t border-white/20 pt-4 text-xs font-bold"
          >
            <a
              href="#topics"
              className="inline-flex items-center gap-1.5 rounded-full bg-white/20 px-3.5 py-1.5 text-white no-underline transition hover:bg-white/30"
            >
              <Compass className="h-3.5 w-3.5" aria-hidden="true" />
              主題連結（{TOPIC_LINKS.length} 項）
            </a>
            <a
              href="#quick-tools"
              className="inline-flex items-center gap-1.5 rounded-full bg-white/20 px-3.5 py-1.5 text-white no-underline transition hover:bg-white/30"
            >
              <Activity className="h-3.5 w-3.5" aria-hidden="true" />
              快速工具與連線狀態
            </a>
            <a
              href="#helpers"
              className="inline-flex items-center gap-1.5 rounded-full bg-white/20 px-3.5 py-1.5 text-white no-underline transition hover:bg-white/30"
            >
              <LifeBuoy className="h-3.5 w-3.5" aria-hidden="true" />
              操作小幫手與指南
            </a>
            <button
              type="button"
              onClick={() => setMotionPaused((prev) => !prev)}
              className="ml-auto inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-white/30 bg-black/15 px-3.5 py-1.5 text-white transition hover:bg-black/25"
            >
              {motionPaused ? (
                <>
                  <Play className="h-3.5 w-3.5" aria-hidden="true" />
                  播放背景動畫
                </>
              ) : (
                <>
                  <Pause className="h-3.5 w-3.5" aria-hidden="true" />
                  暫停背景動畫
                </>
              )}
            </button>
          </nav>
        </header>

        {/* 區塊 1：主題功能連結（Topic Links） */}
        <section id="topics" className="space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <h2 className="m-0 flex items-center gap-2 text-xl font-black text-ink">
                <Compass className="h-5 w-5 text-brand" aria-hidden="true" />
                主題功能連結
              </h2>
              <p className="m-0 mt-1 text-sm text-muted">
                涵蓋前台聚餐決策、管理員審核後台、數據儀表板、店家聲明流程與即時技術統計。
              </p>
            </div>
          </div>

          <div className="hub-topic-grid">
            {TOPIC_LINKS.map((item, idx) => (
              <article
                key={item.id}
                className="hub-card"
                style={{ ["--card-delay" as string]: `${idx * 45}ms` }}
              >
                <header className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-brand-soft">
                      <TopicIcon kind={item.icon} />
                    </span>
                    <div>
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-[0.72rem] font-extrabold ${badgeClass(item.badgeTone)}`}
                      >
                        {item.badge}
                      </span>
                      <h3 className="m-0 mt-1 text-base font-black text-ink">
                        {item.external ? (
                          <a
                            href={item.href}
                            target="_blank"
                            rel="noreferrer"
                            className="card-link inline-flex items-center gap-1"
                          >
                            {item.title}
                            <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted" aria-hidden="true" />
                          </a>
                        ) : (
                          <Link href={item.href} className="card-link inline-flex items-center gap-1">
                            {item.title}
                            <ArrowUpRight className="h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
                          </Link>
                        )}
                      </h3>
                    </div>
                  </div>
                </header>

                <p className="m-0 text-sm leading-relaxed text-muted">{item.summary}</p>

                <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0" aria-label={`${item.title} 重點特色`}>
                  {item.highlights.map((hl) => (
                    <li
                      key={hl}
                      className="inline-flex items-center gap-1 rounded-lg border border-line bg-bg px-2.5 py-1 text-xs font-bold text-ink"
                    >
                      <Check className="h-3 w-3 shrink-0 text-brand" aria-hidden="true" />
                      {hl}
                    </li>
                  ))}
                </ul>

                <footer className="hub-card-footer mt-auto flex flex-col gap-2 border-t border-line/80 pt-3">
                  <span className="mono text-xs text-muted">{item.href}</span>
                  {item.subLinks && item.subLinks.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {item.subLinks.map((sub) =>
                        sub.external ? (
                          <a
                            key={sub.href}
                            href={sub.href}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 rounded-lg border border-line bg-chip px-2.5 py-1 text-xs font-bold text-ink no-underline transition hover:border-brand hover:text-brand"
                          >
                            {sub.label}
                            <ExternalLink className="h-3 w-3" aria-hidden="true" />
                          </a>
                        ) : (
                          <Link
                            key={sub.href}
                            href={sub.href}
                            className="rounded-lg border border-line bg-chip px-2.5 py-1 text-xs font-bold text-ink no-underline transition hover:border-brand hover:text-brand"
                          >
                            {sub.label}
                          </Link>
                        )
                      )}
                    </div>
                  )}
                </footer>
              </article>
            ))}
          </div>
        </section>

        {/* 區塊 2：互動式輔助工具列（快速跳轉 + 後端健康檢查） */}
        <section id="quick-tools" className="space-y-4">
          <div>
            <h2 className="m-0 flex items-center gap-2 text-xl font-black text-ink">
              <Activity className="h-5 w-5 text-brand" aria-hidden="true" />
              展示輔助小工具
            </h2>
            <p className="m-0 mt-1 text-sm text-muted">
              快速確認後端 API 連線狀態，或直接輸入聚餐代碼與店家一次性權杖進行跳轉。
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            {/* 後端連線狀態小幫手 */}
            <div className="flex flex-col justify-between gap-3 rounded-3xl border-2 border-line bg-surface p-5 shadow-card">
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="m-0 flex items-center gap-2 text-sm font-black text-ink">
                    <span className="inline-flex h-7 w-7 items-center justify-center rounded-xl bg-brand-soft text-brand">
                      <Server className="h-4 w-4" aria-hidden="true" />
                    </span>
                    後端服務狀態檢查
                  </h3>
                  {apiState === "online" && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-ok-soft px-2.5 py-0.5 text-xs font-extrabold text-ok">
                      <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                      已連線
                    </span>
                  )}
                  {apiState === "offline" && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-crit-soft px-2.5 py-0.5 text-xs font-extrabold text-crit">
                      <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
                      未啟動
                    </span>
                  )}
                  {apiState === "checking" && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-chip px-2.5 py-0.5 text-xs font-bold text-muted">
                      檢查中…
                    </span>
                  )}
                </div>
                <p className="m-0 text-xs text-muted">
                  目前目標位址：<code className="mono text-ink">{API_BASE}</code>
                </p>
                {apiState === "online" && locationCount !== null && (
                  <p className="m-0 text-xs font-semibold text-ok">
                    已成功載入 {locationCount} 個鹽埕區集合地標，可直接開團體驗！
                  </p>
                )}
                {apiState === "offline" && (
                  <p className="m-0 text-xs font-semibold text-crit">
                    尚未偵測到後端回應。請展開下方「本機開發環境啟動指令小抄」啟動伺服器。
                  </p>
                )}
              </div>

              <GameButton
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => void checkBackend()}
                disabled={apiState === "checking"}
                className="w-full"
              >
                <RefreshCw
                  className={`h-4 w-4 text-brand ${apiState === "checking" ? "animate-spin" : ""}`}
                  aria-hidden="true"
                />
                重新檢查連線
              </GameButton>
            </div>

            {/* 快速前往聚餐頁 */}
            <form
              onSubmit={handleJumpSession}
              className="flex flex-col justify-between gap-3 rounded-3xl border-2 border-line bg-surface p-5 shadow-card"
            >
              <div className="space-y-2">
                <h3 className="m-0 flex items-center gap-2 text-sm font-black text-ink">
                  <span className="inline-flex h-7 w-7 items-center justify-center rounded-xl bg-brand-soft text-brand">
                    <Users className="h-4 w-4" aria-hidden="true" />
                  </span>
                  快速前往聚餐頁面
                </h3>
                <label htmlFor="quick-session-id" className="block text-xs font-semibold text-muted">
                  貼上由 <code className="mono">demo.py</code> 或朋友分享的聚餐代碼（Session ID）
                </label>
                <input
                  id="quick-session-id"
                  type="text"
                  value={sessionId}
                  onChange={(e) => setSessionId(e.target.value)}
                  placeholder="例如：sess_01abc..."
                  className="h-11 w-full rounded-xl border-2 border-line bg-bg px-3 text-sm font-semibold text-ink focus:border-brand focus:bg-surface focus:outline-none"
                />
              </div>
              <GameButton
                type="submit"
                variant="primary"
                size="sm"
                disabled={!sessionId.trim()}
                className="w-full"
              >
                前往聚餐頁（/s/代碼）
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </GameButton>
            </form>

            {/* 快速前往店家自填頁 */}
            <form
              onSubmit={handleJumpMerchant}
              className="flex flex-col justify-between gap-3 rounded-3xl border-2 border-line bg-surface p-5 shadow-card"
            >
              <div className="space-y-2">
                <h3 className="m-0 flex items-center gap-2 text-sm font-black text-ink">
                  <span className="inline-flex h-7 w-7 items-center justify-center rounded-xl bg-ok-soft text-ok">
                    <Store className="h-4 w-4" aria-hidden="true" />
                  </span>
                  快速前往店家自填頁
                </h3>
                <label htmlFor="quick-merchant-token" className="block text-xs font-semibold text-muted">
                  貼上於「認領驗證」頁面產生的一次性店家權杖（Token）
                </label>
                <input
                  id="quick-merchant-token"
                  type="text"
                  value={merchantToken}
                  onChange={(e) => setMerchantToken(e.target.value)}
                  placeholder="貼上店家一次性權杖…"
                  className="h-11 w-full rounded-xl border-2 border-line bg-bg px-3 text-sm font-semibold text-ink focus:border-brand focus:bg-surface focus:outline-none"
                />
              </div>
              <GameButton
                type="submit"
                variant="secondary"
                size="sm"
                disabled={!merchantToken.trim()}
                className="w-full"
              >
                開啟店家填寫頁（/m/權杖）
                <ArrowRight className="h-4 w-4 text-brand" aria-hidden="true" />
              </GameButton>
            </form>
          </div>
        </section>

        {/* 區塊 3：操作小幫手與指南（Helpers — 原生 <details> 手風琴） */}
        <section id="helpers" className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="m-0 flex items-center gap-2 text-xl font-black text-ink">
                <LifeBuoy className="h-5 w-5 text-brand" aria-hidden="true" />
                操作小幫手與指南
              </h2>
              <p className="m-0 mt-1 text-sm text-muted">
                整理課堂展示步驟、後台登入方式、本機啟動指令與系統設計原則，點選即可展開閱讀。
              </p>
            </div>

            <button
              type="button"
              aria-expanded={allExpanded}
              onClick={handleToggleAllHelpers}
              className="hub-toggle-all inline-flex min-h-[38px] cursor-pointer items-center gap-1.5 rounded-xl border-2 border-line bg-surface px-3.5 text-xs font-extrabold text-ink transition hover:border-brand hover:text-brand"
            >
              <BookOpen className="h-3.5 w-3.5 text-brand" aria-hidden="true" />
              <span className="label-expand">全部展開</span>
              <span className="label-collapse">全部收合</span>
            </button>
          </div>

          <div ref={accordionRef} className="hub-accordion">
            {/* Helper 1 */}
            <details open onToggle={syncAccordionExpandedState}>
              <summary>
                <PlayCircle className="h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
                <span>如何快速走完一次「多人聚餐推薦」完整展示流程？</span>
              </summary>
              <div className="hub-accordion-body space-y-3">
                <ol className="m-0 list-decimal space-y-1.5 pl-5">
                  <li>
                    點擊上方「建立聚餐開團」進入 <code className="mono">/create</code>，輸入聚餐名稱（例如「高中同學聚餐」）、設定人數與時間、選擇鹽埕區集合地標後送出。
                  </li>
                  <li>
                    進入聚餐頁後，先完成自己的<strong>硬限制</strong>（例如勾選「不吃牛」或「花生過敏」）與<strong>料理偏好</strong>（調整想吃程度）。
                  </li>
                  <li>
                    複製聚餐連結，用<strong>無痕視窗或另一款瀏覽器</strong>開啟，即可模擬第 2 位、第 3 位朋友加入並填寫各自條件。
                  </li>
                  <li>
                    所有人進度完成後，點擊「產生推薦 Top 3」，即可檢視推薦分數、硬限制安全警示，以及展開「被排除的餐廳」查看排除原因（僅顯示條件、不洩漏是哪位成員的限制）。
                  </li>
                </ol>
                <div className="rounded-2xl border border-line bg-bg p-3 text-xs text-muted">
                  <strong className="text-ink">內建示範劇本預期結果：</strong>
                  A 不吃牛且想吃日式、B 花生過敏且想吃火鍋、C 都可以 → 系統從 15 家候選池排除港園牛肉麵（含牛）與郭家肉粽（疑似含花生），推薦東京小城、柒壹喫堂與汕頭天天沙茶火鍋，並同步標示「花生資訊不足」警示。
                </div>
              </div>
            </details>

            {/* Helper 2 */}
            <details onToggle={syncAccordionExpandedState}>
              <summary>
                <KeyRound className="h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
                <span>如何登入管理員審核後台（/ops）與測試店家自填頁（/m/權杖）？</span>
              </summary>
              <div className="hub-accordion-body space-y-2.5">
                <p className="m-0">
                  審核後台採用雙層驗證：輸入後端環境變數設定的 <code className="mono">OPS_API_KEY</code> 與稽核人員姓名（至少 2 字）即可登入，並會自動核發 Python Dash 專用的簽章 Cookie。
                </p>
                <ul className="m-0 list-disc space-y-1 pl-5">
                  <li>
                    <strong>進入後台：</strong>前往{" "}
                    <Link href="/ops/login" className="font-bold text-brand underline">
                      /ops/login
                    </Link>{" "}
                    完成登入，或於本機管理員名冊快選啟用中的管理員。
                  </li>
                  <li>
                    <strong>體驗店家自填：</strong>登入後前往{" "}
                    <Link href="/ops/claims" className="font-bold text-brand underline">
                      認領與驗證
                    </Link>{" "}
                    挑選一家餐廳產生一次性邀請連結，即可開啟 <code className="mono">/m/權杖</code> 模擬店家填寫過敏原聲明，提交後回到{" "}
                    <Link href="/ops/declarations" className="font-bold text-brand underline">
                      聲明審核
                    </Link>{" "}
                    進行核准或退件。
                  </li>
                </ul>
              </div>
            </details>

            {/* Helper 3 */}
            <details onToggle={syncAccordionExpandedState}>
              <summary>
                <Terminal className="h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
                <span>本機開發環境啟動指令小抄（點擊即可一鍵複製）</span>
              </summary>
              <div className="hub-accordion-body space-y-3">
                <p className="m-0 text-xs text-muted">
                  若上方連線檢查顯示「未啟動」，請依序於終端機執行下列指令（需 Python 3.12+ 與 Node.js 20+）：
                </p>
                <div className="space-y-2.5">
                  {QUICK_COMMANDS.map((item) => (
                    <div
                      key={item.label}
                      className="flex flex-col gap-2 rounded-2xl border border-line bg-bg p-3 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="min-w-0 space-y-1">
                        <div className="text-xs font-extrabold text-ink">{item.label}</div>
                        <code className="mono block text-xs text-muted">{item.cmd}</code>
                      </div>
                      <button
                        type="button"
                        onClick={() => void copyCommand(item.cmd)}
                        aria-label={`複製指令：${item.label}`}
                        className="inline-flex min-h-[36px] shrink-0 cursor-pointer items-center justify-center gap-1.5 rounded-xl border border-line bg-surface px-3 text-xs font-bold text-ink transition hover:border-brand hover:text-brand"
                      >
                        <ClipboardCopy className="h-3.5 w-3.5 text-brand" aria-hidden="true" />
                        複製指令
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </details>

            {/* Helper 4 */}
            <details onToggle={syncAccordionExpandedState}>
              <summary>
                <ShieldAlert className="h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
                <span>推薦引擎的「安全優先」原則與目前資料限制說明</span>
              </summary>
              <div className="hub-accordion-body space-y-2">
                <ul className="m-0 list-disc space-y-1.5 pl-5">
                  <li>
                    <strong>資料不足絕不標示「安全」：</strong>目前資料庫尚無任何餐廳擁有第一手「確認不含過敏原」的正式聲明，因此遇到過敏原條件時會如實呈現「資訊不足」警示，提醒使用者致電確認。
                  </li>
                  <li>
                    <strong>嚴格過敏模式：</strong>僅放行店家已確認不含該過敏原的餐廳；在沒有第一手確認資料的情況下會如實顯示 0 家，絕不硬湊不安全的推薦。
                  </li>
                  <li>
                    <strong>保護個人隱私：</strong>被排除的餐廳只會顯示觸發排除的條件項目（例如「牛肉」），不會顯示是哪一位聚餐成員勾選了該限制。
                  </li>
                </ul>
              </div>
            </details>

            {/* Helper 5 */}
            <details onToggle={syncAccordionExpandedState}>
              <summary>
                <Keyboard className="h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
                <span>介面無障礙與鍵盤操作提示</span>
              </summary>
              <div className="hub-accordion-body space-y-2">
                <p className="m-0">
                  本作業前端依循現代網頁無障礙規範建置，評審與使用者可直接透過鍵盤與輔助工具操作：
                </p>
                <ul className="m-0 list-disc space-y-1 pl-5">
                  <li>
                    使用 <kbd className="rounded border border-line bg-bg px-1.5 py-0.5 text-xs font-bold">Tab</kbd> 可依序瀏覽所有主題卡片、按鈕與手風琴項目，並顯示高對比橘色聚焦外框。
                  </li>
                  <li>
                    展開收合小幫手項目時支援原生{" "}
                    <kbd className="rounded border border-line bg-bg px-1.5 py-0.5 text-xs font-bold">Enter</kbd> 與{" "}
                    <kbd className="rounded border border-line bg-bg px-1.5 py-0.5 text-xs font-bold">Space</kbd> 鍵，且保留瀏覽器「頁面內搜尋（Ctrl/Cmd + F）」自動展開命中區塊的能力。
                  </li>
                  <li>
                    全站支援系統深色／淺色模式與「減少動態效果（prefers-reduced-motion）」偏好設定。
                  </li>
                </ul>
              </div>
            </details>
          </div>
        </section>

        {/* 頁尾資訊 */}
        <footer className="flex flex-col items-start justify-between gap-3 border-t-2 border-line pt-6 text-xs text-muted sm:flex-row sm:items-center">
          <div className="flex items-center gap-2 font-semibold">
            <HelpCircle className="h-4 w-4 text-brand" aria-hidden="true" />
            <span>揪呷 JOEAT · [商管軟體設計-MIS593]-Team 1 展示導覽頁（/index）</span>
          </div>
          <div className="flex flex-wrap items-center gap-3 font-bold">
            <Link href="/create" className="text-ink no-underline hover:text-brand">
              建立聚餐
            </Link>
            <Link href="/ops" className="text-ink no-underline hover:text-brand">
              審核後台
            </Link>
            <Link href="/tech-reports" className="text-ink no-underline hover:text-brand">
              技術報告
            </Link>
            <a
              href={GITHUB_REPO_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-ink no-underline hover:text-brand"
            >
              <GitHubMark className="h-3.5 w-3.5" />
              GitHub
            </a>
            <span className="inline-flex items-center gap-1 text-muted">
              <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
              高雄鹽埕 MVP
            </span>
          </div>
        </footer>
      </div>
    </div>
  );
}
