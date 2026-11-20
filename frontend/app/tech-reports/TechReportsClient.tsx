"use client";
// 技術統計報告互動式儀表板：呈現程式碼、Git 提交、套件依賴與系統架構統計
import {
  ArrowLeft,
  Boxes,
  Code2,
  Database,
  FileCode2,
  FolderGit2,
  GitBranch,
  GitCommitHorizontal,
  Layers,
  Package,
  RefreshCw,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  TestTube2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  type CSSProperties,
  type KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
  useTransition,
} from "react";

import type { TechReportData } from "@/lib/techReportCollector";

type TabId = "code" | "commits" | "packages" | "architecture";
type SortDir = "ascending" | "descending";

interface SortState<K extends string> {
  key: K;
  dir: SortDir;
}

const TABS: { id: TabId; label: string; badge: (r: TechReportData) => string }[] = [
  { id: "code", label: "程式碼統計", badge: (r) => `${r.summary.totalFiles} 檔` },
  {
    id: "commits",
    label: "Git 提交紀錄",
    badge: (r) => `${r.summary.totalCommits} 次`,
  },
  {
    id: "packages",
    label: "套件依賴清單",
    badge: (r) => `${r.summary.directPackages} 項`,
  },
  {
    id: "architecture",
    label: "架構與測試",
    badge: (r) => `${r.summary.apiEndpoints} API`,
  },
];

const COLLATOR = new Intl.Collator("zh-Hant", {
  numeric: true,
  sensitivity: "base",
});

function formatNumber(n: number): string {
  return n.toLocaleString("zh-TW");
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  // 固定轉換為台北時間 (UTC+8) 並手動補零，避免 Node SSR 與瀏覽器 ICU 格式差異導致水合警告
  const taipei = new Date(d.getTime() + 8 * 60 * 60 * 1000);
  const y = taipei.getUTCFullYear();
  const m = String(taipei.getUTCMonth() + 1).padStart(2, "0");
  const day = String(taipei.getUTCDate()).padStart(2, "0");
  const hh = String(taipei.getUTCHours()).padStart(2, "0");
  const mm = String(taipei.getUTCMinutes()).padStart(2, "0");
  return `${y}/${m}/${day} ${hh}:${mm}`;
}

function toggleSort<K extends string>(
  current: SortState<K>,
  nextKey: K
): SortState<K> {
  if (current.key === nextKey) {
    return {
      key: nextKey,
      dir: current.dir === "ascending" ? "descending" : "ascending",
    };
  }
  return { key: nextKey, dir: "ascending" };
}

function SortableHeader<K extends string>({
  colKey,
  label,
  sort,
  onSort,
}: {
  colKey: K;
  label: string;
  sort: SortState<K>;
  onSort: (key: K, label: string) => void;
}) {
  const active = sort.key === colKey;
  return (
    <th scope="col" aria-sort={active ? sort.dir : undefined}>
      <button type="button" onClick={() => onSort(colKey, label)}>
        <span>{label}</span>
        <span className="tech-sort-icon" aria-hidden="true" />
      </button>
    </th>
  );
}

export function TechReportsClient({ report }: { report: TechReportData }) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [activeTab, setActiveTab] = useState<TabId>("code");
  const [statusMessage, setStatusMessage] = useState("");

  // 套件篩選與搜尋狀態
  const [pkgQuery, setPkgQuery] = useState("");
  const [pkgEco, setPkgEco] = useState<"all" | "Frontend (npm)" | "Backend (Python)">("all");
  const [pkgScope, setPkgScope] = useState<"all" | "正式依賴" | "開發與測試">("all");

  // 各表格排序狀態
  const [modSort, setModSort] = useState<SortState<"module" | "category" | "files" | "lines" | "percent">>({
    key: "lines",
    dir: "descending",
  });
  const [fileSort, setFileSort] = useState<SortState<"path" | "language" | "lines" | "bytes">>({
    key: "lines",
    dir: "descending",
  });
  const [pkgSort, setPkgSort] = useState<SortState<"name" | "version" | "ecosystem" | "scope">>({
    key: "ecosystem",
    dir: "ascending",
  });

  const tabRefs = useRef<Record<TabId, HTMLButtonElement | null>>({
    code: null,
    commits: null,
    packages: null,
    architecture: null,
  });

  const panelRefs = useRef<Record<TabId, HTMLDivElement | null>>({
    code: null,
    commits: null,
    packages: null,
    architecture: null,
  });

  // 支援瀏覽器 Ctrl+F（頁內搜尋）在 hidden="until-found" 面板命中時自動切換分頁
  useEffect(() => {
    const cleanups: (() => void)[] = [];
    for (const tab of TABS) {
      const el = panelRefs.current[tab.id];
      if (!el) continue;
      const handler = () => setActiveTab(tab.id);
      el.addEventListener("beforematch", handler);
      cleanups.push(() => el.removeEventListener("beforematch", handler));
    }
    return () => cleanups.forEach((fn) => fn());
  }, []);

  // 切換分頁時，確保選中的分頁鈕捲動進可視區域
  function selectTab(next: TabId, focusTab = false) {
    setActiveTab(next);
    const btn = tabRefs.current[next];
    if (btn) {
      if (focusTab) btn.focus();
      btn.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }

  // 鍵盤方向鍵切換分頁（作為 focusgroup 的跨瀏覽器降級支援）
  function handleTabKeyDown(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIdx = -1;
    if (e.key === "ArrowRight") nextIdx = (index + 1) % TABS.length;
    else if (e.key === "ArrowLeft") nextIdx = (index - 1 + TABS.length) % TABS.length;
    else if (e.key === "Home") nextIdx = 0;
    else if (e.key === "End") nextIdx = TABS.length - 1;
    if (nextIdx >= 0) {
      e.preventDefault();
      selectTab(TABS[nextIdx].id, true);
    }
  }

  function handleRefresh() {
    startTransition(() => {
      router.refresh();
    });
  }

  // 模組排序清單
  const sortedModules = useMemo(() => {
    const factor = modSort.dir === "ascending" ? 1 : -1;
    return [...report.modules].sort((a, b) => {
      if (modSort.key === "files") return factor * (a.files - b.files);
      if (modSort.key === "lines") return factor * (a.lines - b.lines);
      if (modSort.key === "percent") return factor * (a.percent - b.percent);
      return factor * COLLATOR.compare(a[modSort.key], b[modSort.key]);
    });
  }, [report.modules, modSort]);

  // 最大程式碼檔案排序清單
  const sortedFiles = useMemo(() => {
    const factor = fileSort.dir === "ascending" ? 1 : -1;
    return [...report.largestFiles].sort((a, b) => {
      if (fileSort.key === "lines") return factor * (a.lines - b.lines);
      if (fileSort.key === "bytes") return factor * (a.bytes - b.bytes);
      return factor * COLLATOR.compare(a[fileSort.key], b[fileSort.key]);
    });
  }, [report.largestFiles, fileSort]);

  // 篩選與排序後的套件清單
  const filteredPackages = useMemo(() => {
    const q = pkgQuery.trim().toLowerCase();
    const list = report.packages.filter((p) => {
      if (pkgEco !== "all" && p.ecosystem !== pkgEco) return false;
      if (pkgScope !== "all" && p.scope !== pkgScope) return false;
      if (
        q &&
        !p.name.toLowerCase().includes(q) &&
        !p.purpose.toLowerCase().includes(q) &&
        !p.version.toLowerCase().includes(q)
      ) {
        return false;
      }
      return true;
    });

    const factor = pkgSort.dir === "ascending" ? 1 : -1;
    return list.sort((a, b) => factor * COLLATOR.compare(a[pkgSort.key], b[pkgSort.key]));
  }, [report.packages, pkgQuery, pkgEco, pkgScope, pkgSort]);

  const topLanguages = report.languages.slice(0, 7);
  const otherLangPercent = Math.max(
    0,
    Number(
      (100 - topLanguages.reduce((sum, item) => sum + item.percent, 0)).toFixed(1)
    )
  );

  const unitTestCount = report.testSuites
    .filter((t) => t.kind === "單元測試")
    .reduce((sum, t) => sum + t.testCount, 0);
  const integrationTestCount = report.testSuites
    .filter((t) => t.kind === "整合測試")
    .reduce((sum, t) => sum + t.testCount, 0);

  return (
    <div className="tech-report-wrap pb-16">
      {/* 螢幕報讀專用排序狀態通知區 */}
      <div role="status" className="sr-only-status">
        {statusMessage}
      </div>

      {/* 頂部導覽與報告標頭 */}
      <header className="mb-6 flex flex-col gap-4 rounded-3xl border-2 border-line bg-surface p-5 shadow-card md:flex-row md:items-center md:justify-between md:p-6">
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
            <Link
              href="/"
              className="inline-flex items-center gap-1 rounded-full border border-line bg-chip px-3 py-1 text-ink no-underline transition hover:border-brand hover:text-brand"
            >
              <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
              返回揪呷首頁
            </Link>
            <span className="inline-flex items-center gap-1 rounded-full bg-brand-soft px-3 py-1 text-brand-dark">
              <GitBranch className="h-3.5 w-3.5" aria-hidden="true" />
              {report.repoName} · {report.branch}
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-ok-soft px-3 py-1 text-ok">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              即時掃描統計
            </span>
          </div>

          <h1 className="m-0 text-2xl font-black tracking-tight text-ink md:text-3xl">
            技術統計報告
          </h1>
          <p className="m-0 text-sm text-muted">
            即時彙整程式碼規模、Git 提交動態、前後端套件依賴與系統架構品質指標（更新時間：
            <time dateTime={report.generatedAt} className="tabular-nums font-semibold text-ink">
              {formatDateTime(report.generatedAt)}
            </time>
            ）
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/ops"
            className="inline-flex min-h-[42px] items-center gap-2 rounded-xl border-2 border-line bg-bg px-4 text-sm font-bold text-ink no-underline transition hover:border-brand hover:text-brand"
          >
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            審核後台
          </Link>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={isPending}
            className="inline-flex min-h-[42px] cursor-pointer items-center gap-2 rounded-xl border-0 bg-brand px-4 text-sm font-extrabold text-brand-ink shadow-game-brand transition active:translate-y-[2px] disabled:opacity-60"
          >
            <RefreshCw
              className={`h-4 w-4 ${isPending ? "animate-spin" : ""}`}
              aria-hidden="true"
            />
            {isPending ? "重新掃描中…" : "重新整理統計"}
          </button>
        </div>
      </header>

      {/* 核心 KPI 統計卡片列 */}
      <section aria-label="核心技術指標摘要" className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <article className="rounded-2xl border-2 border-line bg-surface p-4 shadow-card">
          <div className="mb-2 flex items-center justify-between text-muted">
            <span className="text-xs font-bold">總行數</span>
            <Code2 className="h-4 w-4 text-brand" aria-hidden="true" />
          </div>
          <p className="m-0 text-2xl font-black tabular-nums text-ink">
            {formatNumber(report.summary.totalLines)}
          </p>
          <p className="mt-1 mb-0 text-xs text-muted tabular-nums">
            純程式碼 {formatNumber(report.summary.codeLines)} 行
          </p>
        </article>

        <article className="rounded-2xl border-2 border-line bg-surface p-4 shadow-card">
          <div className="mb-2 flex items-center justify-between text-muted">
            <span className="text-xs font-bold">專案檔案</span>
            <FileCode2 className="h-4 w-4 text-brand" aria-hidden="true" />
          </div>
          <p className="m-0 text-2xl font-black tabular-nums text-ink">
            {formatNumber(report.summary.totalFiles)}
          </p>
          <p className="mt-1 mb-0 text-xs text-muted tabular-nums">
            總容量 {formatBytes(report.summary.totalBytes)}
          </p>
        </article>

        <article className="rounded-2xl border-2 border-line bg-surface p-4 shadow-card">
          <div className="mb-2 flex items-center justify-between text-muted">
            <span className="text-xs font-bold">Git 提交</span>
            <GitCommitHorizontal className="h-4 w-4 text-ok" aria-hidden="true" />
          </div>
          <p className="m-0 text-2xl font-black tabular-nums text-ink">
            {formatNumber(report.summary.totalCommits)}
          </p>
          <p className="mt-1 mb-0 text-xs text-muted tabular-nums">
            {report.summary.uncommittedFiles > 0
              ? `工作樹 ${report.summary.uncommittedFiles} 檔異動中`
              : "工作樹已完全同步"}
          </p>
        </article>

        <article className="rounded-2xl border-2 border-line bg-surface p-4 shadow-card">
          <div className="mb-2 flex items-center justify-between text-muted">
            <span className="text-xs font-bold">直接依賴套件</span>
            <Package className="h-4 w-4 text-warn" aria-hidden="true" />
          </div>
          <p className="m-0 text-2xl font-black tabular-nums text-ink">
            {formatNumber(report.summary.directPackages)}
          </p>
          <p className="mt-1 mb-0 text-xs text-muted tabular-nums">
            npm 解析 {formatNumber(report.summary.resolvedNpmPackages)} 套件
          </p>
        </article>

        <article className="rounded-2xl border-2 border-line bg-surface p-4 shadow-card">
          <div className="mb-2 flex items-center justify-between text-muted">
            <span className="text-xs font-bold">API 與遷移</span>
            <Server className="h-4 w-4 text-brand" aria-hidden="true" />
          </div>
          <p className="m-0 text-2xl font-black tabular-nums text-ink">
            {formatNumber(report.summary.apiEndpoints)}
          </p>
          <p className="mt-1 mb-0 text-xs text-muted tabular-nums">
            {report.summary.migrationsCount} 版 DB 遷移 · {report.summary.frontendPagesCount} 頁
          </p>
        </article>

        <article className="rounded-2xl border-2 border-line bg-surface p-4 shadow-card">
          <div className="mb-2 flex items-center justify-between text-muted">
            <span className="text-xs font-bold">自動化測試</span>
            <TestTube2 className="h-4 w-4 text-ok" aria-hidden="true" />
          </div>
          <p className="m-0 text-2xl font-black tabular-nums text-ink">
            {formatNumber(report.summary.testCases)}
          </p>
          <p className="mt-1 mb-0 text-xs text-muted tabular-nums">
            共 {report.summary.testFiles} 個測試套件檔
          </p>
        </article>
      </section>

      {/* 程式語言佔比堆疊條 */}
      <section
        aria-label="程式語言分佈比例"
        className="mb-6 rounded-2xl border-2 border-line bg-surface p-4 shadow-card md:p-5"
      >
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="m-0 flex items-center gap-2 text-base font-extrabold text-ink">
            <Layers className="h-4 w-4 text-brand" aria-hidden="true" />
            程式語言與檔案組成比例
          </h2>
          <span className="text-xs font-semibold text-muted tabular-nums">
            文件共 {formatNumber(report.summary.docLines)} 行 · 程式碼佔比{" "}
            {report.summary.totalLines > 0
              ? ((report.summary.codeLines / report.summary.totalLines) * 100).toFixed(1)
              : "0.0"}
            %
          </span>
        </div>

        <div
          className="flex h-3.5 w-full overflow-hidden rounded-full bg-chip"
          role="img"
          aria-label={topLanguages
            .map((l) => `${l.language} 佔 ${l.percent}%`)
            .join("，")}
        >
          {topLanguages.map((lang) => (
            <div
              key={lang.language}
              title={`${lang.language}: ${formatNumber(lang.lines)} 行 (${lang.percent}%)`}
              style={{
                width: `${lang.percent}%`,
                backgroundColor: lang.color,
              }}
            />
          ))}
          {otherLangPercent > 0 && (
            <div
              title={`其他格式: ${otherLangPercent}%`}
              style={{ width: `${otherLangPercent}%`, backgroundColor: "#94A3B8" }}
            />
          )}
        </div>

        <ul className="mt-3 mb-0 flex flex-wrap gap-x-5 gap-y-2 p-0 list-none text-xs">
          {topLanguages.map((lang) => (
            <li key={lang.language} className="inline-flex items-center gap-1.5">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: lang.color }}
                aria-hidden="true"
              />
              <span className="font-bold text-ink">{lang.language}</span>
              <span className="text-muted tabular-nums">
                {lang.percent}%（{formatNumber(lang.lines)} 行 / {lang.files} 檔）
              </span>
            </li>
          ))}
        </ul>
      </section>

      {/* 分頁導覽列（依 modern-web-guidance tabs 規範） */}
      <div
        className="tech-tablist"
        role="tablist"
        aria-label="技術統計分類"
        {...({ focusgroup: "tablist nomemory" } as Record<string, string>)}
      >
        {TABS.map((tab, index) => {
          const selected = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              ref={(el) => {
                tabRefs.current[tab.id] = el;
              }}
              type="button"
              role="tab"
              id={`tab-${tab.id}`}
              aria-selected={selected}
              tabIndex={selected ? 0 : -1}
              {...(selected ? ({ focusgroupstart: "" } as Record<string, string>) : {})}
              onClick={() => selectTab(tab.id)}
              onKeyDown={(e) => handleTabKeyDown(e, index)}
            >
              <span>{tab.label}</span>
              <span className="rounded-full bg-chip px-2 py-0.5 text-xs font-bold text-muted tabular-nums">
                {tab.badge(report)}
              </span>
            </button>
          );
        })}
      </div>

      {/* ===== 分頁 1：程式碼統計 ===== */}
      <div
        ref={(el) => {
          panelRefs.current.code = el;
        }}
        role="tabpanel"
        aria-labelledby="tab-code"
        className="tech-tabpanel"
        hidden={activeTab !== "code" ? ("until-found" as unknown as boolean) : undefined}
      >
        <div className="space-y-6 pt-5">
          {/* 模組分佈可排序響應式表格 */}
          <div
            tabIndex={0}
            role="region"
            aria-labelledby="mod-table-caption"
            className="tech-table-wrapper"
          >
            <table
              className="tech-table"
              style={
                {
                  "--label-2": '"類別"',
                  "--label-3": '"檔案數"',
                  "--label-4": '"程式碼行數"',
                  "--label-5": '"佔比"',
                } as CSSProperties
              }
            >
              <caption id="mod-table-caption">
                專案目錄與模組統計（點擊欄位標題可切換排序）
              </caption>
              <thead>
                <tr>
                  <SortableHeader
                    colKey="module"
                    label="模組路徑"
                    sort={modSort}
                    onSort={(key, label) => {
                      const next = toggleSort(modSort, key);
                      setModSort(next);
                      setStatusMessage(
                        `模組表已依「${label}」${next.dir === "ascending" ? "遞增" : "遞減"}排序，共 ${sortedModules.length} 筆`
                      );
                    }}
                  />
                  <SortableHeader
                    colKey="category"
                    label="類別"
                    sort={modSort}
                    onSort={(key, label) => {
                      const next = toggleSort(modSort, key);
                      setModSort(next);
                      setStatusMessage(
                        `模組表已依「${label}」${next.dir === "ascending" ? "遞增" : "遞減"}排序，共 ${sortedModules.length} 筆`
                      );
                    }}
                  />
                  <SortableHeader
                    colKey="files"
                    label="檔案數"
                    sort={modSort}
                    onSort={(key, label) => {
                      const next = toggleSort(modSort, key);
                      setModSort(next);
                      setStatusMessage(
                        `模組表已依「${label}」${next.dir === "ascending" ? "遞增" : "遞減"}排序，共 ${sortedModules.length} 筆`
                      );
                    }}
                  />
                  <SortableHeader
                    colKey="lines"
                    label="行數"
                    sort={modSort}
                    onSort={(key, label) => {
                      const next = toggleSort(modSort, key);
                      setModSort(next);
                      setStatusMessage(
                        `模組表已依「${label}」${next.dir === "ascending" ? "遞增" : "遞減"}排序，共 ${sortedModules.length} 筆`
                      );
                    }}
                  />
                  <SortableHeader
                    colKey="percent"
                    label="佔比"
                    sort={modSort}
                    onSort={(key, label) => {
                      const next = toggleSort(modSort, key);
                      setModSort(next);
                      setStatusMessage(
                        `模組表已依「${label}」${next.dir === "ascending" ? "遞增" : "遞減"}排序，共 ${sortedModules.length} 筆`
                      );
                    }}
                  />
                </tr>
              </thead>
              <tbody>
                {sortedModules.map((m) => (
                  <tr key={m.module}>
                    <th scope="row" className="mono">
                      {m.module}
                    </th>
                    <td>
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-bold ${
                          m.category === "前端"
                            ? "bg-brand-soft text-brand-dark"
                            : m.category === "後端"
                              ? "bg-ok-soft text-ok"
                              : m.category === "文件"
                                ? "bg-warn-soft text-warn"
                                : "bg-chip text-muted"
                        }`}
                      >
                        {m.category}
                      </span>
                    </td>
                    <td className="tabular-nums">{formatNumber(m.files)}</td>
                    <td className="tabular-nums font-semibold">
                      {formatNumber(m.lines)}
                    </td>
                    <td>
                      <div className="flex items-center gap-2">
                        <div className="h-2 w-24 overflow-hidden rounded-full bg-chip">
                          <div
                            className="h-full rounded-full bg-brand"
                            style={{ width: `${Math.min(100, m.percent * 2.5)}%` }}
                          />
                        </div>
                        <span className="tabular-nums text-xs text-muted">
                          {m.percent}%
                        </span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 前 15 大程式碼檔案表格 */}
          <div
            tabIndex={0}
            role="region"
            aria-labelledby="files-table-caption"
            className="tech-table-wrapper"
          >
            <table
              className="tech-table"
              style={
                {
                  "--label-2": '"程式語言"',
                  "--label-3": '"行數"',
                  "--label-4": '"檔案大小"',
                } as CSSProperties
              }
            >
              <caption id="files-table-caption">
                核心程式碼檔案規模排行（前 15 大檔案）
              </caption>
              <thead>
                <tr>
                  <SortableHeader
                    colKey="path"
                    label="檔案路徑"
                    sort={fileSort}
                    onSort={(key, label) => {
                      const next = toggleSort(fileSort, key);
                      setFileSort(next);
                      setStatusMessage(
                        `檔案排行已依「${label}」${next.dir === "ascending" ? "遞增" : "遞減"}排序，共 ${sortedFiles.length} 筆`
                      );
                    }}
                  />
                  <SortableHeader
                    colKey="language"
                    label="語言"
                    sort={fileSort}
                    onSort={(key, label) => {
                      const next = toggleSort(fileSort, key);
                      setFileSort(next);
                      setStatusMessage(
                        `檔案排行已依「${label}」${next.dir === "ascending" ? "遞增" : "遞減"}排序，共 ${sortedFiles.length} 筆`
                      );
                    }}
                  />
                  <SortableHeader
                    colKey="lines"
                    label="行數"
                    sort={fileSort}
                    onSort={(key, label) => {
                      const next = toggleSort(fileSort, key);
                      setFileSort(next);
                      setStatusMessage(
                        `檔案排行已依「${label}」${next.dir === "ascending" ? "遞增" : "遞減"}排序，共 ${sortedFiles.length} 筆`
                      );
                    }}
                  />
                  <SortableHeader
                    colKey="bytes"
                    label="大小"
                    sort={fileSort}
                    onSort={(key, label) => {
                      const next = toggleSort(fileSort, key);
                      setFileSort(next);
                      setStatusMessage(
                        `檔案排行已依「${label}」${next.dir === "ascending" ? "遞增" : "遞減"}排序，共 ${sortedFiles.length} 筆`
                      );
                    }}
                  />
                </tr>
              </thead>
              <tbody>
                {sortedFiles.map((f) => (
                  <tr key={f.path}>
                    <th scope="row" className="mono">
                      {f.path}
                    </th>
                    <td>{f.language}</td>
                    <td className="tabular-nums font-bold">
                      {formatNumber(f.lines)}
                    </td>
                    <td className="tabular-nums text-muted">
                      {formatBytes(f.bytes)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ===== 分頁 2：Git 提交紀錄 ===== */}
      <div
        ref={(el) => {
          panelRefs.current.commits = el;
        }}
        role="tabpanel"
        aria-labelledby="tab-commits"
        className="tech-tabpanel"
        hidden={activeTab !== "commits" ? ("until-found" as unknown as boolean) : undefined}
      >
        <div className="space-y-6 pt-5">
          {/* 貢獻者摘要 */}
          <div className="grid gap-3 md:grid-cols-2">
            {report.contributors.map((c) => (
              <div
                key={c.author}
                className="flex items-center justify-between rounded-2xl border-2 border-line bg-surface p-4 shadow-card"
              >
                <div>
                  <p className="m-0 text-xs font-bold text-muted">主要貢獻者</p>
                  <p className="mt-0.5 mb-0 text-base font-extrabold text-ink">
                    {c.author}
                  </p>
                </div>
                <div className="text-right tabular-nums">
                  <p className="m-0 text-lg font-black text-brand">
                    {c.commits} 次提交
                  </p>
                  <p className="m-0 text-xs font-semibold">
                    <span className="text-ok">+{formatNumber(c.insertions)}</span>{" "}
                    /{" "}
                    <span className="text-crit">-{formatNumber(c.deletions)}</span>
                  </p>
                </div>
              </div>
            ))}

            <div className="flex items-center justify-between rounded-2xl border-2 border-line bg-surface p-4 shadow-card">
              <div>
                <p className="m-0 text-xs font-bold text-muted">目前工作樹待提交變更</p>
                <p className="mt-0.5 mb-0 text-base font-extrabold text-ink">
                  {report.summary.uncommittedFiles > 0
                    ? `${report.summary.uncommittedFiles} 個檔案開發中`
                    : "目前無未提交變更"}
                </p>
              </div>
              <div className="text-right tabular-nums">
                <p className="m-0 text-sm font-extrabold text-ok">
                  +{formatNumber(report.summary.uncommittedInsertions)} 行
                </p>
                <p className="m-0 text-sm font-extrabold text-crit">
                  -{formatNumber(report.summary.uncommittedDeletions)} 行
                </p>
              </div>
            </div>
          </div>

          {/* 正式提交歷史時間軸 */}
          <section className="rounded-2xl border-2 border-line bg-surface p-5 shadow-card">
            <h2 className="mt-0 mb-4 flex items-center gap-2 text-base font-extrabold text-ink">
              <FolderGit2 className="h-4 w-4 text-brand" aria-hidden="true" />
              Git 提交歷史時間軸
            </h2>
            {report.commits.length === 0 ? (
              <p className="m-0 text-sm text-muted">目前尚無 Git 提交紀錄。</p>
            ) : (
              <ol className="m-0 space-y-3 p-0 list-none">
                {report.commits.map((c) => {
                  const totalDelta = Math.max(1, c.insertions + c.deletions);
                  const addPct = Math.round((c.insertions / totalDelta) * 100);
                  return (
                    <li
                      key={c.hash}
                      className="rounded-xl border border-line bg-bg p-4"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <code className="rounded-md bg-brand-soft px-2 py-0.5 font-mono text-xs font-bold text-brand-dark">
                              {c.hash}
                            </code>
                            <span className="text-sm font-extrabold text-ink">
                              {c.subject}
                            </span>
                          </div>
                          <p className="m-0 text-xs text-muted">
                            {c.author} ·{" "}
                            <time dateTime={c.date} className="tabular-nums">
                              {formatDateTime(c.date)}
                            </time>
                          </p>
                        </div>
                        <div className="text-right text-xs font-bold tabular-nums">
                          <span className="text-muted">{c.filesChanged} 檔異動</span>
                          <div className="mt-1 flex items-center justify-end gap-2">
                            <span className="text-ok">
                              +{formatNumber(c.insertions)}
                            </span>
                            <span className="text-crit">
                              -{formatNumber(c.deletions)}
                            </span>
                          </div>
                        </div>
                      </div>
                      <div className="mt-3 flex h-1.5 w-full overflow-hidden rounded-full bg-chip">
                        <div
                          className="bg-ok"
                          style={{ width: `${addPct}%` }}
                          aria-hidden="true"
                        />
                        <div
                          className="bg-crit"
                          style={{ width: `${100 - addPct}%` }}
                          aria-hidden="true"
                        />
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </section>

          {/* 工作樹即時異動表 */}
          {report.workingTree.length > 0 && (
            <div
              tabIndex={0}
              role="region"
              aria-labelledby="wt-table-caption"
              className="tech-table-wrapper"
            >
              <table
                className="tech-table"
                style={
                  {
                    "--label-2": '"狀態"',
                    "--label-3": '"新增行數"',
                    "--label-4": '"刪除行數"',
                  } as CSSProperties
                }
              >
                <caption id="wt-table-caption">
                  工作樹未提交變更明細（共 {report.workingTree.length} 檔）
                </caption>
                <thead>
                  <tr>
                    <th scope="col">檔案路徑</th>
                    <th scope="col">狀態</th>
                    <th scope="col">新增行數</th>
                    <th scope="col">刪除行數</th>
                  </tr>
                </thead>
                <tbody>
                  {report.workingTree.map((item) => (
                    <tr key={item.path}>
                      <th scope="row" className="mono">
                        {item.path}
                      </th>
                      <td>
                        <span
                          className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-bold ${
                            item.status === "??" || item.status === "A"
                              ? "bg-ok-soft text-ok"
                              : "bg-warn-soft text-warn"
                          }`}
                        >
                          {item.statusLabel}
                        </span>
                      </td>
                      <td className="tabular-nums font-bold text-ok">
                        +{formatNumber(item.insertions)}
                      </td>
                      <td className="tabular-nums font-bold text-crit">
                        -{formatNumber(item.deletions)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* ===== 分頁 3：套件依賴清單 ===== */}
      <div
        ref={(el) => {
          panelRefs.current.packages = el;
        }}
        role="tabpanel"
        aria-labelledby="tab-packages"
        className="tech-tabpanel"
        hidden={activeTab !== "packages" ? ("until-found" as unknown as boolean) : undefined}
      >
        <div className="space-y-4 pt-5">
          {/* 套件摘要與篩選工具列 */}
          <div className="flex flex-col gap-3 rounded-2xl border-2 border-line bg-surface p-4 shadow-card md:flex-row md:items-center md:justify-between">
            <div className="relative flex-1">
              <Search
                className="pointer-events-none absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2 text-muted"
                aria-hidden="true"
              />
              <input
                type="search"
                value={pkgQuery}
                onChange={(e) => setPkgQuery(e.target.value)}
                placeholder="搜尋套件名稱、版本或用途說明…"
                aria-label="搜尋套件"
                className="min-h-[42px] w-full rounded-xl border-2 border-line bg-bg pr-4 pl-10 text-sm text-ink"
              />
            </div>

            <div className="flex flex-wrap gap-2">
              {(["all", "Frontend (npm)", "Backend (Python)"] as const).map((eco) => (
                <button
                  key={eco}
                  type="button"
                  onClick={() => setPkgEco(eco)}
                  className={`min-h-[38px] cursor-pointer rounded-full border px-3 text-xs font-bold transition ${
                    pkgEco === eco
                      ? "border-brand bg-brand text-brand-ink"
                      : "border-line bg-chip text-ink hover:border-brand"
                  }`}
                >
                  {eco === "all"
                    ? `全部生態系 (${report.summary.directPackages})`
                    : eco === "Frontend (npm)"
                      ? `前端 npm (${report.summary.frontendDirectPackages})`
                      : `後端 Python (${report.summary.backendDirectPackages})`}
                </button>
              ))}
              {(["all", "正式依賴", "開發與測試"] as const).map((sc) => (
                <button
                  key={sc}
                  type="button"
                  onClick={() => setPkgScope(sc)}
                  className={`min-h-[38px] cursor-pointer rounded-full border px-3 text-xs font-bold transition ${
                    pkgScope === sc
                      ? "border-ink bg-ink text-bg"
                      : "border-line bg-bg text-muted hover:text-ink"
                  }`}
                >
                  {sc === "all" ? "全部類型" : sc}
                </button>
              ))}
            </div>
          </div>

          <div
            tabIndex={0}
            role="region"
            aria-labelledby="pkg-table-caption"
            className="tech-table-wrapper"
          >
            <table
              className="tech-table"
              style={
                {
                  "--label-2": '"版本條件"',
                  "--label-3": '"生態系"',
                  "--label-4": '"依賴類型"',
                  "--label-5": '"用途說明"',
                } as CSSProperties
              }
            >
              <caption id="pkg-table-caption">
                前後端直接套件清單（顯示 {filteredPackages.length} / {report.packages.length} 項；npm 鎖定檔共解析{" "}
                {formatNumber(report.summary.resolvedNpmPackages)} 個套件）
              </caption>
              <thead>
                <tr>
                  <SortableHeader
                    colKey="name"
                    label="套件名稱"
                    sort={pkgSort}
                    onSort={(key, label) => {
                      const next = toggleSort(pkgSort, key);
                      setPkgSort(next);
                      setStatusMessage(
                        `套件表已依「${label}」${next.dir === "ascending" ? "遞增" : "遞減"}排序，共 ${filteredPackages.length} 筆`
                      );
                    }}
                  />
                  <SortableHeader
                    colKey="version"
                    label="版本"
                    sort={pkgSort}
                    onSort={(key, label) => {
                      const next = toggleSort(pkgSort, key);
                      setPkgSort(next);
                      setStatusMessage(
                        `套件表已依「${label}」${next.dir === "ascending" ? "遞增" : "遞減"}排序，共 ${filteredPackages.length} 筆`
                      );
                    }}
                  />
                  <SortableHeader
                    colKey="ecosystem"
                    label="生態系"
                    sort={pkgSort}
                    onSort={(key, label) => {
                      const next = toggleSort(pkgSort, key);
                      setPkgSort(next);
                      setStatusMessage(
                        `套件表已依「${label}」${next.dir === "ascending" ? "遞增" : "遞減"}排序，共 ${filteredPackages.length} 筆`
                      );
                    }}
                  />
                  <SortableHeader
                    colKey="scope"
                    label="類型"
                    sort={pkgSort}
                    onSort={(key, label) => {
                      const next = toggleSort(pkgSort, key);
                      setPkgSort(next);
                      setStatusMessage(
                        `套件表已依「${label}」${next.dir === "ascending" ? "遞增" : "遞減"}排序，共 ${filteredPackages.length} 筆`
                      );
                    }}
                  />
                  <th scope="col">用途說明</th>
                </tr>
              </thead>
              <tbody>
                {filteredPackages.map((p) => (
                  <tr key={`${p.ecosystem}-${p.name}`}>
                    <th scope="row" className="mono">
                      {p.name}
                    </th>
                    <td className="mono text-muted">{p.version}</td>
                    <td>
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-bold ${
                          p.ecosystem === "Frontend (npm)"
                            ? "bg-brand-soft text-brand-dark"
                            : "bg-ok-soft text-ok"
                        }`}
                      >
                        {p.ecosystem}
                      </span>
                    </td>
                    <td>
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-bold ${
                          p.scope === "正式依賴"
                            ? "bg-chip text-ink"
                            : "bg-warn-soft text-warn"
                        }`}
                      >
                        {p.scope}
                      </span>
                    </td>
                    <td className="text-muted">{p.purpose}</td>
                  </tr>
                ))}
                {filteredPackages.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-muted">
                      找不到符合條件的套件，請調整搜尋關鍵字或篩選條件。
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ===== 分頁 4：系統架構與測試 ===== */}
      <div
        ref={(el) => {
          panelRefs.current.architecture = el;
        }}
        role="tabpanel"
        aria-labelledby="tab-architecture"
        className="tech-tabpanel"
        hidden={activeTab !== "architecture" ? ("until-found" as unknown as boolean) : undefined}
      >
        <div className="grid gap-5 pt-5 lg:grid-cols-2">
          {/* 後端 API 端點分佈 */}
          <section className="rounded-2xl border-2 border-line bg-surface p-5 shadow-card">
            <h2 className="mt-0 mb-3 flex items-center gap-2 text-base font-extrabold text-ink">
              <Server className="h-4 w-4 text-brand" aria-hidden="true" />
              FastAPI 路由模組（共 {report.summary.apiEndpoints} 個端點）
            </h2>
            <ul className="m-0 space-y-2.5 p-0 list-none">
              {report.apiModules.map((mod) => (
                <li
                  key={mod.file}
                  className="flex items-center justify-between gap-3 rounded-xl border border-line bg-bg px-3.5 py-2.5 text-sm"
                >
                  <span className="mono truncate font-semibold text-ink">
                    {mod.file}
                  </span>
                  <span className="shrink-0 rounded-full bg-brand-soft px-2.5 py-0.5 text-xs font-extrabold text-brand-dark tabular-nums">
                    {mod.endpoints} 端點 · {mod.lines} 行
                  </span>
                </li>
              ))}
            </ul>
          </section>

          {/* 資料庫遷移版本歷程 */}
          <section className="rounded-2xl border-2 border-line bg-surface p-5 shadow-card">
            <h2 className="mt-0 mb-3 flex items-center gap-2 text-base font-extrabold text-ink">
              <Database className="h-4 w-4 text-warn" aria-hidden="true" />
              Alembic 資料庫遷移歷程（{report.migrations.length} 個版本）
            </h2>
            <ol className="m-0 grid grid-cols-1 gap-2 p-0 list-none sm:grid-cols-2">
              {report.migrations.map((mig) => (
                <li
                  key={mig.filename}
                  className="flex items-center justify-between gap-2 rounded-xl border border-line bg-bg px-3 py-2 text-xs"
                >
                  <span className="mono truncate font-semibold text-ink">
                    {mig.filename}
                  </span>
                  <span className="shrink-0 text-muted tabular-nums">
                    {mig.lines} 行
                  </span>
                </li>
              ))}
            </ol>
          </section>

          {/* 自動化測試分佈 */}
          <section className="rounded-2xl border-2 border-line bg-surface p-5 shadow-card">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="m-0 flex items-center gap-2 text-base font-extrabold text-ink">
                <TestTube2 className="h-4 w-4 text-ok" aria-hidden="true" />
                自動化測試套件（{report.summary.testCases} 個測試案例）
              </h2>
              <span className="text-xs font-bold text-muted tabular-nums">
                單元 {unitTestCount} · 整合 {integrationTestCount}
              </span>
            </div>
            <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
              {report.testSuites.map((suite) => (
                <div
                  key={suite.file}
                  className="flex items-center justify-between gap-2 rounded-xl border border-line bg-bg px-3 py-2 text-xs"
                >
                  <span className="mono truncate font-semibold text-ink">
                    {suite.file.replace(/^backend\/tests\//, "")}
                  </span>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <span
                      className={`rounded-full px-2 py-0.5 font-bold ${
                        suite.kind === "單元測試"
                          ? "bg-ok-soft text-ok"
                          : "bg-brand-soft text-brand-dark"
                      }`}
                    >
                      {suite.kind}
                    </span>
                    <span className="font-extrabold text-ink tabular-nums">
                      {suite.testCount} 例
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* 前端路由與元件清單 */}
          <section className="rounded-2xl border-2 border-line bg-surface p-5 shadow-card">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="m-0 flex items-center gap-2 text-base font-extrabold text-ink">
                <Boxes className="h-4 w-4 text-brand" aria-hidden="true" />
                Next.js 頁面路由（{report.frontendPages.length} 頁）
              </h2>
              <span className="text-xs font-bold text-muted tabular-nums">
                共用元件 {report.summary.frontendComponentsCount} 個
              </span>
            </div>
            <ul className="m-0 grid grid-cols-1 gap-2 p-0 list-none sm:grid-cols-2">
              {report.frontendPages.map((route) => {
                const isDynamic = route.includes("[");
                return (
                  <li
                    key={route}
                    className="flex items-center justify-between rounded-xl border border-line bg-bg px-3 py-2 text-xs"
                  >
                    {isDynamic ? (
                      <span className="mono font-semibold text-ink">{route}</span>
                    ) : (
                      <Link
                        href={route}
                        className="mono font-semibold text-brand no-underline hover:underline"
                      >
                        {route}
                      </Link>
                    )}
                    <span className="text-[11px] font-bold text-muted">
                      {isDynamic ? "動態路由" : "靜態路由"}
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
