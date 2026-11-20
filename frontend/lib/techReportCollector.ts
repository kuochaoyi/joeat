// 伺服器端技術統計資料收集器：即時掃描專案程式碼、Git 提交紀錄、前後端套件與架構指標
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

export interface LanguageStat {
  language: string;
  files: number;
  lines: number;
  bytes: number;
  percent: number;
  color: string;
}

export interface ModuleStat {
  module: string;
  files: number;
  lines: number;
  percent: number;
  category: "前端" | "後端" | "資料與設定" | "文件";
}

export interface CodeFileStat {
  path: string;
  language: string;
  lines: number;
  bytes: number;
}

export interface CommitStat {
  hash: string;
  date: string;
  author: string;
  subject: string;
  filesChanged: number;
  insertions: number;
  deletions: number;
}

export interface WorkingTreeChange {
  status: string;
  statusLabel: string;
  path: string;
  insertions: number;
  deletions: number;
}

export interface ContributorStat {
  author: string;
  commits: number;
  insertions: number;
  deletions: number;
}

export interface PackageStat {
  name: string;
  version: string;
  ecosystem: "Frontend (npm)" | "Backend (Python)";
  scope: "正式依賴" | "開發與測試";
  purpose: string;
}

export interface MigrationStat {
  revision: string;
  filename: string;
  lines: number;
}

export interface RouteModuleStat {
  file: string;
  endpoints: number;
  lines: number;
}

export interface TestSuiteStat {
  file: string;
  kind: "單元測試" | "整合測試";
  testCount: number;
  lines: number;
}

export interface TechReportData {
  generatedAt: string;
  repoName: string;
  branch: string;
  summary: {
    totalFiles: number;
    totalLines: number;
    codeLines: number;
    docLines: number;
    totalBytes: number;
    totalCommits: number;
    uncommittedFiles: number;
    uncommittedInsertions: number;
    uncommittedDeletions: number;
    directPackages: number;
    frontendDirectPackages: number;
    backendDirectPackages: number;
    resolvedNpmPackages: number;
    apiEndpoints: number;
    testCases: number;
    testFiles: number;
    migrationsCount: number;
    frontendPagesCount: number;
    frontendComponentsCount: number;
  };
  languages: LanguageStat[];
  modules: ModuleStat[];
  largestFiles: CodeFileStat[];
  commits: CommitStat[];
  contributors: ContributorStat[];
  workingTree: WorkingTreeChange[];
  packages: PackageStat[];
  migrations: MigrationStat[];
  apiModules: RouteModuleStat[];
  testSuites: TestSuiteStat[];
  frontendPages: string[];
}

const IGNORE_DIRS = new Set([
  ".git",
  "node_modules",
  ".next",
  ".venv",
  ".pgdata",
  ".pytest_cache",
  "__pycache__",
  "dist",
  "build",
]);

const IGNORE_FILES = new Set([
  ".DS_Store",
  "package-lock.json",
  "tsconfig.tsbuildinfo",
]);

const EXT_LANGUAGE: Record<string, string> = {
  ".py": "Python",
  ".tsx": "TypeScript (TSX)",
  ".ts": "TypeScript",
  ".sql": "SQL",
  ".css": "CSS",
  ".md": "Markdown",
  ".json": "JSON",
  ".js": "JavaScript",
  ".yml": "YAML",
  ".yaml": "YAML",
  ".csv": "CSV",
  ".ini": "設定檔",
  ".mako": "範本檔",
  ".txt": "純文字",
};

const LANGUAGE_COLORS: Record<string, string> = {
  Python: "#3572A5",
  "TypeScript (TSX)": "#3178C6",
  TypeScript: "#2563EB",
  SQL: "#E38C00",
  Markdown: "#0F766E",
  JSON: "#8B5CF6",
  CSS: "#EC4899",
  JavaScript: "#F59E0B",
  YAML: "#6366F1",
  CSV: "#10B981",
  Docker: "#0EA5E9",
};

const CODE_LANGUAGES = new Set([
  "Python",
  "TypeScript (TSX)",
  "TypeScript",
  "SQL",
  "CSS",
  "JavaScript",
  "Docker",
]);

const PACKAGE_PURPOSES: Record<string, string> = {
  // 前端套件用途說明
  next: "React 全端框架（App Router 與伺服器端渲染）",
  react: "使用者介面元件核心函式庫",
  "react-dom": "React 瀏覽器 DOM 渲染引擎",
  "@line/liff": "LINE LIFF 登入與群組情境整合套件",
  leaflet: "互動式地圖元件與定位選點功能",
  "@types/leaflet": "Leaflet 地圖 TypeScript 型別定義",
  "lucide-react": "輕量向量圖示元件庫",
  clsx: "條件式 CSS 類別名稱組合工具",
  "tailwind-merge": "智慧合併 Tailwind CSS 樣式衝突",
  tailwindcss: "實用優先（Utility-First）CSS 設計框架",
  typescript: "靜態型別檢查與現代語法編譯器",
  autoprefixer: "自動補齊跨瀏覽器 CSS 前綴",
  postcss: "CSS 轉換與建置處理管線",
  "@types/node": "Node.js 執行環境 TypeScript 型別定義",
  "@types/react": "React TypeScript 型別定義",
  "@types/react-dom": "React DOM TypeScript 型別定義",
  // 後端套件用途說明
  fastapi: "高效能非同步 Python API 框架",
  "uvicorn[standard]": "ASGI 伺服器，負責執行 FastAPI 服務",
  SQLAlchemy: "Python ORM 與資料庫查詢建構工具",
  alembic: "資料庫結構（Schema）版本遷移管理工具",
  "psycopg[binary]": "PostgreSQL 資料庫驅動程式（v3）",
  pydantic: "API 請求與回應資料結構驗證引擎",
  "pydantic-settings": "環境變數與系統設定管理模組",
  httpx: "非同步 HTTP 用戶端（外部呼叫與測試）",
  dash: "後台營運統計互動式儀表板框架",
  a2wsgi: "ASGI 與 WSGI 應用程式橋接中介層",
  pytest: "Python 自動化單元與整合測試框架",
  pgserver: "免安裝 Docker 的內嵌式 PostgreSQL 開發伺服器",
};

function runGit(repoRoot: string, args: string[]): string {
  try {
    return execFileSync("git", args, {
      cwd: repoRoot,
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return "";
  }
}

function resolveRepoRoot(): string {
  const cwd = process.cwd();
  const parent = path.resolve(cwd, "..");
  if (fs.existsSync(path.join(parent, ".git"))) {
    return parent;
  }
  if (fs.existsSync(path.join(cwd, ".git"))) {
    return cwd;
  }
  return parent;
}

function classifyModule(relPath: string): { module: string; category: ModuleStat["category"] } {
  const parts = relPath.split(path.sep);
  const top = parts[0];
  if (top === "frontend") {
    const mod = parts.length > 2 ? `frontend/${parts[1]}` : "frontend";
    return { module: mod, category: "前端" };
  }
  if (top === "backend") {
    const mod = parts.length > 2 ? `backend/${parts[1]}` : "backend";
    return { module: mod, category: "後端" };
  }
  if (top === "docs") {
    const mod = parts.length > 2 ? `docs/${parts[1]}` : "docs";
    return { module: mod, category: "文件" };
  }
  if (top === "data" || top === "docker") {
    const mod = parts.length > 2 ? `${top}/${parts[1]}` : top;
    return { module: mod, category: "資料與設定" };
  }
  return { module: "專案根目錄", category: relPath.endsWith(".md") ? "文件" : "資料與設定" };
}

function parseRequirements(filePath: string, scope: PackageStat["scope"]): PackageStat[] {
  if (!fs.existsSync(filePath)) return [];
  const raw = fs.readFileSync(filePath, "utf-8");
  const list: PackageStat[] = [];
  for (const line of raw.split(/\r?\n/)) {
    const cleaned = line.split("#")[0].trim();
    if (!cleaned || cleaned.startsWith("-r") || cleaned.startsWith("--")) continue;
    const match = cleaned.match(/^([A-Za-z0-9_.\-\[\]]+)\s*(.*)$/);
    if (!match) continue;
    const [, name, versionRaw] = match;
    list.push({
      name,
      version: versionRaw.trim() || "latest",
      ecosystem: "Backend (Python)",
      scope,
      purpose: PACKAGE_PURPOSES[name] ?? "後端核心與輔助功能套件",
    });
  }
  return list;
}

function collectGitCommits(repoRoot: string): {
  commits: CommitStat[];
  contributors: ContributorStat[];
} {
  const logOutput = runGit(repoRoot, [
    "log",
    "--numstat",
    "--pretty=format:COMMIT_MARKER|%h|%ai|%an|%s",
  ]);
  if (!logOutput) return { commits: [], contributors: [] };

  const commits: CommitStat[] = [];
  const contribMap = new Map<string, ContributorStat>();
  let current: CommitStat | null = null;

  for (const line of logOutput.split(/\r?\n/)) {
    if (line.startsWith("COMMIT_MARKER|")) {
      if (current) commits.push(current);
      const [, hash, date, author, ...subjectParts] = line.split("|");
      current = {
        hash,
        date,
        author,
        subject: subjectParts.join("|"),
        filesChanged: 0,
        insertions: 0,
        deletions: 0,
      };
    } else if (current && line.trim()) {
      const parts = line.split("\t");
      if (parts.length >= 3) {
        const ins = parts[0] === "-" ? 0 : Number.parseInt(parts[0], 10) || 0;
        const del = parts[1] === "-" ? 0 : Number.parseInt(parts[1], 10) || 0;
        current.filesChanged += 1;
        current.insertions += ins;
        current.deletions += del;
      }
    }
  }
  if (current) commits.push(current);

  for (const c of commits) {
    const existing = contribMap.get(c.author) ?? {
      author: c.author,
      commits: 0,
      insertions: 0,
      deletions: 0,
    };
    existing.commits += 1;
    existing.insertions += c.insertions;
    existing.deletions += c.deletions;
    contribMap.set(c.author, existing);
  }

  return {
    commits,
    contributors: Array.from(contribMap.values()).sort((a, b) => b.commits - a.commits),
  };
}

function collectWorkingTree(repoRoot: string): WorkingTreeChange[] {
  const statusOut = runGit(repoRoot, ["status", "--porcelain"]);
  if (!statusOut) return [];

  const diffOut = runGit(repoRoot, ["diff", "--numstat"]);
  const diffMap = new Map<string, { ins: number; del: number }>();
  for (const line of diffOut.split(/\r?\n/)) {
    if (!line.trim()) continue;
    const [insStr, delStr, filePath] = line.split("\t");
    if (!filePath) continue;
    diffMap.set(filePath, {
      ins: insStr === "-" ? 0 : Number.parseInt(insStr, 10) || 0,
      del: delStr === "-" ? 0 : Number.parseInt(delStr, 10) || 0,
    });
  }

  const labelMap: Record<string, string> = {
    M: "已修改",
    A: "已新增",
    D: "已刪除",
    "??": "未追蹤新檔",
    R: "已重新命名",
  };

  const changes: WorkingTreeChange[] = [];
  for (const line of statusOut.split(/\r?\n/)) {
    if (!line.trim()) continue;
    const code = line.slice(0, 2).trim() || "M";
    const filePath = line.slice(3).trim();
    let insertions = diffMap.get(filePath)?.ins ?? 0;
    const deletions = diffMap.get(filePath)?.del ?? 0;

    if (code === "??") {
      const full = path.join(repoRoot, filePath);
      if (fs.existsSync(full) && fs.statSync(full).isFile()) {
        try {
          const content = fs.readFileSync(full, "utf-8");
          insertions = content.split(/\r?\n/).length;
        } catch {
          insertions = 0;
        }
      }
    }

    changes.push({
      status: code,
      statusLabel: labelMap[code] ?? "變更中",
      path: filePath,
      insertions,
      deletions,
    });
  }

  return changes.sort((a, b) => b.insertions + b.deletions - (a.insertions + a.deletions));
}

export function collectTechReport(): TechReportData {
  const repoRoot = resolveRepoRoot();
  const branch = runGit(repoRoot, ["rev-parse", "--abbrev-ref", "HEAD"]) || "main";

  const langMap = new Map<string, { files: number; lines: number; bytes: number }>();
  const modMap = new Map<
    string,
    { files: number; lines: number; category: ModuleStat["category"] }
  >();
  const codeFiles: CodeFileStat[] = [];
  const migrations: MigrationStat[] = [];
  const apiModules: RouteModuleStat[] = [];
  const testSuites: TestSuiteStat[] = [];
  const frontendPages: string[] = [];

  let totalFiles = 0;
  let totalLines = 0;
  let codeLines = 0;
  let docLines = 0;
  let totalBytes = 0;
  let apiEndpoints = 0;
  let testCases = 0;
  let frontendComponentsCount = 0;

  function walk(dir: string) {
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }

    for (const entry of entries) {
      if (entry.isDirectory()) {
        if (IGNORE_DIRS.has(entry.name)) continue;
        walk(path.join(dir, entry.name));
        continue;
      }
      if (!entry.isFile() || IGNORE_FILES.has(entry.name)) continue;

      const fullPath = path.join(dir, entry.name);
      const relPath = path.relative(repoRoot, fullPath);
      const ext = path.extname(entry.name).toLowerCase();
      const language = entry.name.endsWith("Dockerfile")
        ? "Docker"
        : EXT_LANGUAGE[ext] ?? "其他";

      let content = "";
      let lines = 0;
      let bytes = 0;
      try {
        bytes = fs.statSync(fullPath).size;
        content = fs.readFileSync(fullPath, "utf-8");
        lines = content ? content.split(/\r?\n/).length : 0;
      } catch {
        // 忽略不可讀取之二進位或權限受限檔案
      }

      totalFiles += 1;
      totalLines += lines;
      totalBytes += bytes;

      if (CODE_LANGUAGES.has(language)) {
        codeLines += lines;
        codeFiles.push({ path: relPath, language, lines, bytes });
      }
      if (language === "Markdown") {
        docLines += lines;
      }

      const lStat = langMap.get(language) ?? { files: 0, lines: 0, bytes: 0 };
      lStat.files += 1;
      lStat.lines += lines;
      lStat.bytes += bytes;
      langMap.set(language, lStat);

      const { module: modName, category } = classifyModule(relPath);
      const mStat = modMap.get(modName) ?? { files: 0, lines: 0, category };
      mStat.files += 1;
      mStat.lines += lines;
      modMap.set(modName, mStat);

      // 收集 API 端點統計
      if (relPath.startsWith(`backend${path.sep}app${path.sep}api${path.sep}`) && ext === ".py") {
        const matches = content.match(/@router\.(?:get|post|put|patch|delete)\(/g);
        const count = matches ? matches.length : 0;
        if (count > 0) {
          apiEndpoints += count;
          apiModules.push({ file: relPath, endpoints: count, lines });
        }
      }

      // 收集資料庫遷移檔案
      if (
        relPath.startsWith(`backend${path.sep}alembic${path.sep}versions${path.sep}`) &&
        ext === ".py"
      ) {
        const rev = entry.name.split("_")[0] || entry.name;
        migrations.push({ revision: rev, filename: entry.name, lines });
      }

      // 收集自動化測試統計
      if (
        relPath.startsWith(`backend${path.sep}tests${path.sep}`) &&
        entry.name.startsWith("test_") &&
        ext === ".py"
      ) {
        const matches = content.match(/^\s*(?:async\s+)?def\s+test_/gm);
        const count = matches ? matches.length : 0;
        testCases += count;
        testSuites.push({
          file: relPath,
          kind: relPath.includes(`${path.sep}unit${path.sep}`) ? "單元測試" : "整合測試",
          testCount: count,
          lines,
        });
      }

      // 收集前端頁面與元件
      if (
        relPath.startsWith(`frontend${path.sep}app${path.sep}`) &&
        entry.name === "page.tsx"
      ) {
        const route =
          "/" +
          relPath
            .replace(/^frontend\/app\//, "")
            .replace(/\/?page\.tsx$/, "");
        frontendPages.push(route === "/" ? "/" : route.replace(/\/$/, ""));
      }
      if (
        relPath.startsWith(`frontend${path.sep}components${path.sep}`) &&
        (ext === ".tsx" || ext === ".ts")
      ) {
        frontendComponentsCount += 1;
      }
    }
  }

  walk(repoRoot);

  // 收集套件統計（前端 package.json + package-lock.json，後端 requirements*.txt）
  const packages: PackageStat[] = [];
  let frontendDirectPackages = 0;
  let resolvedNpmPackages = 0;

  const pkgJsonPath = path.join(repoRoot, "frontend", "package.json");
  if (fs.existsSync(pkgJsonPath)) {
    const pkg = JSON.parse(fs.readFileSync(pkgJsonPath, "utf-8")) as {
      dependencies?: Record<string, string>;
      devDependencies?: Record<string, string>;
    };
    for (const [name, version] of Object.entries(pkg.dependencies ?? {})) {
      frontendDirectPackages += 1;
      packages.push({
        name,
        version,
        ecosystem: "Frontend (npm)",
        scope: "正式依賴",
        purpose: PACKAGE_PURPOSES[name] ?? "前端功能依賴套件",
      });
    }
    for (const [name, version] of Object.entries(pkg.devDependencies ?? {})) {
      frontendDirectPackages += 1;
      packages.push({
        name,
        version,
        ecosystem: "Frontend (npm)",
        scope: "開發與測試",
        purpose: PACKAGE_PURPOSES[name] ?? "前端建置與開發工具",
      });
    }
  }

  const pkgLockPath = path.join(repoRoot, "frontend", "package-lock.json");
  if (fs.existsSync(pkgLockPath)) {
    try {
      const lock = JSON.parse(fs.readFileSync(pkgLockPath, "utf-8")) as {
        packages?: Record<string, unknown>;
      };
      resolvedNpmPackages = Object.keys(lock.packages ?? {}).filter((k) => k !== "").length;
    } catch {
      resolvedNpmPackages = 0;
    }
  }

  const backendProd = parseRequirements(
    path.join(repoRoot, "backend", "requirements.txt"),
    "正式依賴"
  );
  const backendDev = parseRequirements(
    path.join(repoRoot, "backend", "requirements-dev.txt"),
    "開發與測試"
  );
  packages.push(...backendProd, ...backendDev);
  const backendDirectPackages = backendProd.length + backendDev.length;

  const { commits, contributors } = collectGitCommits(repoRoot);
  const workingTree = collectWorkingTree(repoRoot);
  const uncommittedInsertions = workingTree.reduce((acc, item) => acc + item.insertions, 0);
  const uncommittedDeletions = workingTree.reduce((acc, item) => acc + item.deletions, 0);

  const languages: LanguageStat[] = Array.from(langMap.entries())
    .map(([language, stat]) => ({
      language,
      files: stat.files,
      lines: stat.lines,
      bytes: stat.bytes,
      percent: totalLines > 0 ? Number(((stat.lines / totalLines) * 100).toFixed(1)) : 0,
      color: LANGUAGE_COLORS[language] ?? "#94A3B8",
    }))
    .sort((a, b) => b.lines - a.lines);

  const modules: ModuleStat[] = Array.from(modMap.entries())
    .map(([modName, stat]) => ({
      module: modName,
      files: stat.files,
      lines: stat.lines,
      percent: totalLines > 0 ? Number(((stat.lines / totalLines) * 100).toFixed(1)) : 0,
      category: stat.category,
    }))
    .sort((a, b) => b.lines - a.lines);

  const largestFiles = codeFiles.sort((a, b) => b.lines - a.lines).slice(0, 15);
  migrations.sort((a, b) => a.revision.localeCompare(b.revision));
  apiModules.sort((a, b) => b.endpoints - a.endpoints);
  testSuites.sort((a, b) => b.testCount - a.testCount);
  frontendPages.sort();

  return {
    generatedAt: new Date().toISOString(),
    repoName: path.basename(repoRoot),
    branch,
    summary: {
      totalFiles,
      totalLines,
      codeLines,
      docLines,
      totalBytes,
      totalCommits: commits.length,
      uncommittedFiles: workingTree.length,
      uncommittedInsertions,
      uncommittedDeletions,
      directPackages: frontendDirectPackages + backendDirectPackages,
      frontendDirectPackages,
      backendDirectPackages,
      resolvedNpmPackages,
      apiEndpoints,
      testCases,
      testFiles: testSuites.length,
      migrationsCount: migrations.length,
      frontendPagesCount: frontendPages.length,
      frontendComponentsCount,
    },
    languages,
    modules,
    largestFiles,
    commits,
    contributors,
    workingTree,
    packages,
    migrations,
    apiModules,
    testSuites,
    frontendPages,
  };
}
