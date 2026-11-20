import type {
  Answers, AttributeMeta, CuisineMeta, DietComposition, DietMeta, DietType, LocationPreset, Participant, Progress, Recommendation, Session, Stance, TimePoll, Vote,
} from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public extra: Record<string, unknown> = {}) {
    super(message);
  }
}

const ZH_ERRORS: Record<string, string> = {
  session_full: "這場聚餐的人數已滿，無法再加入。",
  session_expired: "這場聚餐已過期。",
  session_closed: "這場聚餐已關閉。",
  incomplete: "還有人沒填完。可以等大家填完，或選「不等了」。",
  no_participants: "還沒有人加入。",
  not_found: "找不到這筆資料（連結可能不正確）。",
  unknown_attribute: "有不認得的限制項目。",
  unknown_cuisine: "有不認得的料理類型。",
  rate_limited: "你今天回報太多次了（24 小時內最多 3 次），明天再試。",
  already_reported: "你今天已經回報過這一項了。",
  queue_full: "這家店已經有很多待處理的回報，審核人員會處理，不需要再回報。",
  not_a_candidate: "只能回報出現在你這場聚餐結果裡的餐廳。",
  host_only: "這個動作只有主揪可以做。",
  not_a_member: "你不在這場聚餐裡。",
  poll_closed: "時間投票已經結束。",
  poll_needs_options: "請至少選 2 個可能的時段。",
  slot_in_the_past: "時段不能是過去的時間。",
  vote_open: "已經有一場進行中的投票。",
  vote_closed: "投票已經結束。",
  no_recommendation: "請先產生推薦，再發起投票。",
  nothing_to_vote_on: "目前沒有可以投票的餐廳。",
  incomplete_ballot: "每間餐廳都要表態（可選「都可以」）。",
  outside_taiwan: "集合地點必須在台灣。",
  bad_coordinates: "地圖座標不完整。",
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "network", "連不上伺服器，請確認後端已啟動。");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok && ZH_ERRORS[body.error]) throw new ApiError(res.status, body.error, ZH_ERRORS[body.error], body);
  if (!res.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map((d: { msg: string }) => d.msg).join("；") : body.detail;
    throw new ApiError(res.status, body.error || "error", body.message || detail || `HTTP ${res.status}`, body);
  }
  return body as T;
}

const post = <T,>(path: string, data?: unknown) => api<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });

export const getAttributes = () => api<AttributeMeta>("/meta/attributes");
export const getCuisines = () => api<CuisineMeta>("/meta/cuisines");
export const getLocations = () => api<{ locations: LocationPreset[] }>("/meta/locations");

export const createSession = (data: {
  title: string; date?: string; time?: string; location_preset?: string; location_label?: string; meeting_lat?: number; meeting_lon?: number;
  party_size: number; line_group_id?: string; host_line_user_id?: string; host_id_token?: string;
  time_mode?: "fixed" | "poll"; time_slots?: string[]; time_deadline_hours?: number; needs_pets?: boolean; needs_kids?: boolean;
}) => post<Session>("/sessions", data);
export const getSession = (id: string) => api<Session>(`/sessions/${id}`);
export const joinSession = (id: string, data: { line_user_id: string; label?: string; id_token?: string }) => post<Participant>(`/sessions/${id}/participants`, data);
export const getProgress = (id: string, participantId?: string | null) =>
  api<Progress>(`/sessions/${id}/progress${participantId ? `?participant_id=${participantId}` : ""}`);
export const getParticipant = (pid: string) => api<Participant>(`/participants/${pid}`);

export const submitConstraints = (pid: string, items: { attribute_code: string; reason?: string }[], strictAllergy = false, budget: number | null = null) =>
  post<{ saved: number; participant: Participant }>(`/participants/${pid}/constraints`, { items, strict_allergy: strictAllergy, budget_max_per_person: budget });
export const putNeeds = (sid: string, pid: string, needsPets: boolean, needsKids: boolean) =>
  put<{ needs_pets: boolean; needs_kids: boolean }>(`/sessions/${sid}/needs`, { participant_id: pid, needs_pets: needsPets, needs_kids: needsKids });
export const getDietMeta = () => api<DietMeta>("/meta/diet-types");
export const putDietType = (pid: string, answers: Record<string, string>) => put<DietType>(`/participants/${pid}/diet-type`, { answers });
export const getDietComposition = (sid: string) => api<DietComposition>(`/sessions/${sid}/diet-types`);
export const getAnswers = (pid: string) => api<Answers>(`/participants/${pid}/answers`);

const put = <T,>(path: string, data: unknown) => api<T>(path, { method: "PUT", body: JSON.stringify(data) });
export const getTimePoll = (sid: string, pid?: string | null) => api<TimePoll>(`/sessions/${sid}/time-poll${pid ? `?participant_id=${pid}` : ""}`);
export const putTimeVotes = (pid: string, optionIds: number[]) => put<TimePoll>(`/participants/${pid}/time-votes`, { option_ids: optionIds });
export const closeTimePoll = (sid: string, pid: string) => post<TimePoll>(`/sessions/${sid}/time-poll/close`, { participant_id: pid });
export const startVote = (sid: string, pid: string, hours: number) => post<Vote>(`/sessions/${sid}/votes`, { participant_id: pid, closes_in_hours: hours });
export const getVote = (sid: string, pid?: string | null) => api<Vote>(`/sessions/${sid}/votes/current${pid ? `?participant_id=${pid}` : ""}`);
export const putBallot = (voteId: string, pid: string, scores: { restaurant_id: string; score: number; any_ok: boolean }[]) =>
  put<Vote>(`/votes/${voteId}/ballot`, { participant_id: pid, scores });
export const closeVote = (voteId: string, pid: string) => post<Vote>(`/votes/${voteId}/close`, { participant_id: pid });

export type ReportKind = "wrong_info" | "allergic_reaction" | "closed" | "other";
export const reportRestaurant = (restaurantId: string, data: { participant_id: string; kind: ReportKind; attribute_code?: string; note?: string }) =>
  post<{ report_id: number; message: string }>(`/restaurants/${restaurantId}/reports`, data);
export const submitPreferences = (pid: string, items: { cuisine_tag: string; stance: Stance }[]) =>
  post<{ saved: number; participant: Participant }>(`/participants/${pid}/preferences`, { items });

export const runRecommendation = (id: string, allowPartial = false) =>
  post<Recommendation>(`/sessions/${id}/recommendations?include_excluded=true`, { allow_partial: allowPartial });
export const getRecommendation = (id: string) => api<Recommendation>(`/sessions/${id}/recommendations?include_excluded=true`);
