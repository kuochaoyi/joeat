// Merchant-facing API client. The invitation token is sent in a header (never in a URL we call), see backend/app/api/merchant.py.
import { API_BASE, ApiError } from "./api";

export interface FormItem {
  attribute_code: string; name: string; type: "avoid" | "require"; risk_level: string; question: string;
  answers: { value: string; label: string }[];
  cross_contact: { question: string; options: { value: string; label: string }[]; asked_when: string } | null;
  certificate: boolean;
}
export interface FormSpec {
  sections: { key: string; title: string; items: FormItem[] }[]; default_answer: string; validity_days: number; intro: string;
  attestation: { version: string; template: string }; legal_review: { status: string; note: string };
}
export interface DeclItem { attribute_code: string; answer: string; cross_contact_status: string; note: string | null; certificate_ref: string | null }
export interface Declaration {
  declaration_id: number; status: string; valid_days: number; menu_as_of: string | null; menu_url: string | null; declared_role: string | null;
  attestation_version: string | null; submitted_at: string | null; review_note: string | null; reviewed_at: string | null; editable: boolean; items: DeclItem[];
}
export interface MerchantMe {
  restaurant: { name: string; address: string | null; phone: string | null }; claim_status: string; can_declare: boolean; demo: boolean;
  claimant_role: string | null; declaration: Declaration | null; message: string | null;
}
export interface PreviewLine { attribute_code: string; text: string; effect: "confirmed" | "possible" | "contains"; state: string }
export interface Preview { lines: PreviewLine[]; unanswered_note: string; counts: Record<string, number>; verification_note: string; demo: boolean }

async function call<T>(token: string | null, path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, cache: "no-store", headers: { "Content-Type": "application/json", ...(token ? { "X-Claim-Token": token } : {}) } });
  } catch {
    throw new ApiError(0, "network", "連不上伺服器，請稍後再試。");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map((d: { msg: string }) => d.msg).join("；") : body.detail;
    const zh: Record<string, string> = {
      not_found: "這個連結無效，請確認網址是否完整。", claim_unavailable: "這個邀請已失效，請聯絡揪呷團隊。", not_verified: "我們還在確認身分，完成後您就可以填寫。",
    };
    throw new ApiError(res.status, body.error || "error", zh[body.error] || body.message || detail || `HTTP ${res.status}`, body);
  }
  return body as T;
}
const put = (token: string, path: string, data: unknown) => call<unknown>(token, path, { method: "PUT", body: JSON.stringify(data) });

export const mFormSpec = () => call<FormSpec>(null, "/merchant/form-spec");
export const mMe = (t: string) => call<MerchantMe>(t, "/merchant/me");
export const mStart = (t: string) => call<Declaration>(t, "/merchant/declaration", { method: "POST" });
export const mSaveItems = (t: string, items: DeclItem[]) => put(t, "/merchant/declaration/items", { items });
export const mSaveMenu = (t: string, menu_url: string | null) => put(t, "/merchant/declaration/menu", { menu_url });
export const mPreview = (t: string) => call<Preview>(t, "/merchant/declaration/preview");
export const mSubmit = (t: string, data: { role: string; menu_as_of: string; accepted: boolean; attestation_version: string }) =>
  call<Declaration>(t, "/merchant/declaration/submit", { method: "POST", body: JSON.stringify(data) });
