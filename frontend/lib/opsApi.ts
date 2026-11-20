// Reviewer / operator API client. Key and name live in sessionStorage (this tab only). This is the pilot-grade gate described in docs/decisions/0001.
import { API_BASE, ApiError } from "./api";

const K = "joeat:ops";
export const getOpsAuth = (): { key: string; user: string } | null => {
  if (typeof window === "undefined") return null;
  try { return JSON.parse(window.sessionStorage.getItem(K) || "null"); } catch { return null; }
};
export const setOpsAuth = (a: { key: string; user: string } | null) => (a ? window.sessionStorage.setItem(K, JSON.stringify(a)) : window.sessionStorage.removeItem(K));

export async function ops<T>(path: string, init?: RequestInit): Promise<T> {
  const a = getOpsAuth();
  if (!a) throw new ApiError(401, "no_auth", "請先輸入金鑰與姓名");
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/ops${path}`, { ...init, cache: "no-store", headers: { "Content-Type": "application/json", "X-Ops-Key": a.key, "X-Ops-User": encodeURIComponent(a.user) } });
  } catch {
    throw new ApiError(0, "network", "連不上伺服器");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map((d: { msg: string }) => d.msg).join("；") : body.detail;
    throw new ApiError(res.status, body.error || "error", body.message || detail || `HTTP ${res.status}`, body);
  }
  return body as T;
}
export const post = <T,>(path: string, data?: unknown) => ops<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });
