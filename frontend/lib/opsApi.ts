// 審核後台 API 用戶端：金鑰與姓名存放於 sessionStorage（僅限目前分頁），搭配簽章 Cookie 存取 Python Dash。
import { API_BASE, ApiError } from "./api";

const AUTH_KEY = "joeat:ops";
const ADMINS_KEY = "joeat:ops:admins";

export interface OpsAuth {
  key: string;
  user: string;
}

export interface OpsCounts {
  pending_declarations: number;
  open_reports: number;
  open_incidents: number;
  active_claims: number;
  total_restaurants: number;
  total_sessions: number;
}

export interface OpsSummaryDeclaration {
  declaration_id: number;
  status: string;
  restaurant: string;
  submitted_at: string | null;
  verification_level: string;
  verification_method: string;
  is_demo: boolean;
  answered_items: number;
  conflict_count: number;
}

export interface OpsSummary {
  user: string;
  counts: OpsCounts;
  recent_pending_declarations: OpsSummaryDeclaration[];
}

export interface LocalAdminRecord {
  id: string;
  name: string;
  role: string;
  active: boolean;
  createdAt: string;
}

export const getOpsAuth = (): OpsAuth | null => {
  if (typeof window === "undefined") return null;
  try {
    return JSON.parse(window.sessionStorage.getItem(AUTH_KEY) || "null");
  } catch {
    return null;
  }
};

export const setOpsAuth = (a: OpsAuth | null) => {
  if (typeof window === "undefined") return;
  if (a) window.sessionStorage.setItem(AUTH_KEY, JSON.stringify(a));
  else window.sessionStorage.removeItem(AUTH_KEY);
};

export async function ops<T>(path: string, init?: RequestInit): Promise<T> {
  const a = getOpsAuth();
  if (!a) throw new ApiError(401, "no_auth", "請先輸入金鑰與管理員姓名");
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/ops${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "X-Ops-Key": a.key,
        "X-Ops-User": encodeURIComponent(a.user),
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError(0, "network", "連不上伺服器，請確認後端服務已啟動");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(body.detail)
      ? body.detail.map((d: { msg: string }) => d.msg).join("；")
      : body.detail;
    throw new ApiError(res.status, body.error || "error", body.message || detail || `HTTP ${res.status}`, body);
  }
  return body as T;
}

export const post = <T,>(path: string, data?: unknown) =>
  ops<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });

export const getOpsSummary = () => ops<OpsSummary>("/summary");

/** 換取 Python Dash 儀表板專用的 HttpOnly 簽章 Cookie。 */
export async function createDashSession(): Promise<void> {
  const a = getOpsAuth();
  if (!a) return;
  await fetch(`${API_BASE}/ops/dash-session`, {
    method: "POST",
    credentials: "include",
    cache: "no-store",
    headers: {
      "X-Ops-Key": a.key,
      "X-Ops-User": encodeURIComponent(a.user),
    },
  }).catch(() => undefined);
}

/** 登出時同步清除 Python Dash 簽章 Cookie。 */
export async function clearDashSession(): Promise<void> {
  await fetch(`${API_BASE}/ops/dash-logout`, {
    method: "POST",
    credentials: "include",
    cache: "no-store",
  }).catch(() => undefined);
}

export const getDashUrl = () => `${API_BASE}/ops/dash/`;

// ------------------------------------------------------------------ 本機管理員名冊（方案 A：不更動資料庫）
export function getLocalAdmins(): LocalAdminRecord[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(ADMINS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveLocalAdmins(list: LocalAdminRecord[]): LocalAdminRecord[] {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(ADMINS_KEY, JSON.stringify(list));
  }
  return list;
}

export function addLocalAdmin(name: string, role: string): LocalAdminRecord[] {
  const trimmed = name.trim();
  const list = getLocalAdmins();
  if (list.some((a) => a.name.toLowerCase() === trimmed.toLowerCase())) {
    throw new Error(`管理員「${trimmed}」已在名冊中`);
  }
  const next: LocalAdminRecord = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    name: trimmed,
    role: role.trim() || "審核員",
    active: true,
    createdAt: new Date().toISOString(),
  };
  return saveLocalAdmins([next, ...list]);
}

export function toggleLocalAdmin(id: string): LocalAdminRecord[] {
  const list = getLocalAdmins().map((a) => (a.id === id ? { ...a, active: !a.active } : a));
  return saveLocalAdmins(list);
}

export function isLocalAdminDisabled(name: string): boolean {
  const trimmed = name.trim().toLowerCase();
  if (!trimmed) return false;
  return getLocalAdmins().some((a) => a.name.toLowerCase() === trimmed && !a.active);
}
