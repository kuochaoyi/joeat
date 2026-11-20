"use client";
// 推薦結果卡片：店名、一行狀態、重要警示永遠留在表面，其餘細節收在「查看原因」
// 安全鐵律：未知過敏原或重要警示絕對不可藏在摺疊區；任何地方絕不出現「安全」字樣。
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Crown,
  ExternalLink,
  Flag,
  MapPin,
  OctagonAlert,
  Phone,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useState } from "react";

import { useToast } from "@/components/Toast";
import { GameButton } from "@/components/ui";
import { ReportKind, reportRestaurant } from "@/lib/api";
import { cn } from "@/lib/cn";
import { getStoredParticipant } from "@/lib/storage";
import type { Need, RestaurantRecommendation, Warning } from "@/lib/types";

const ORDER = { critical: 0, high: 1, normal: 2 } as const;
const LEVEL_STYLE = {
  critical: "bg-crit-soft text-crit border-crit/30",
  high: "bg-warn-soft text-warn border-warn/30",
  normal: "bg-chip text-muted border-line",
} as const;
const LEVEL_TEXT = { critical: "重要", high: "注意", normal: "提醒" } as const;
const KINDS: [ReportKind, string][] = [
  ["wrong_info", "資訊有誤"],
  ["allergic_reaction", "吃了出現過敏反應"],
  ["closed", "歇業 / 搬遷"],
  ["other", "其他"],
];
const NEED_SHORT: Record<Need["status"], [string, string]> = {
  yes: ["可以", "bg-ok-soft text-ok"],
  maybe: ["可能可以", "bg-warn-soft text-warn"],
  no: ["沒有", "bg-warn-soft text-warn"],
  unknown: ["資訊不足", "bg-chip text-muted"],
};

const isUnknownRow = (w: Warning, unknown: string[]) =>
  (w.code === "attribute_unknown" || w.code === "attribute_likely_absent") &&
  !!w.display &&
  unknown.includes(w.display);

function StatusBanner({ r }: { r: RestaurantRecommendation }) {
  const hc = r.hard_constraint;
  const bad = r.warnings.some((w) => w.level === "critical");
  const critical = new Set(
    r.warnings
      .filter((w) => w.level === "critical" && isUnknownRow(w, hc.unknown_attributes))
      .map((w) => w.display)
  );
  const names = [...hc.unknown_attributes]
    .sort((a, b) => Number(critical.has(b)) - Number(critical.has(a)))
    .map((n) => (critical.has(n) ? `${n}（重要）` : n));

  let tone: "ok" | "warn" | "crit" | "none" = "ok";
  let text = "已知資料沒有衝突";
  if (hc.status === "no_constraints") {
    tone = "none";
    text = "沒有人設定限制";
  } else if (hc.status === "suspected_conflict") {
    tone = "crit";
    text = "有資料顯示可能衝突（未確認）";
  } else if (hc.status === "partial_conflict") {
    tone = "warn";
    text = "只有部分餐點含有不想吃的食材";
  } else if (names.length > 0) {
    tone = "warn";
    text = `資料不足：${names.join("、")}`;
  } else if (bad) {
    tone = "warn";
    text = "有重要提醒";
  }

  return (
    <div
      data-testid="status"
      className={cn(
        "my-3 flex items-start gap-2 rounded-2xl border-l-4 px-3.5 py-2.5 text-sm font-bold",
        tone === "ok" && "border-ok bg-ok-soft text-ok",
        tone === "warn" && "border-warn bg-warn-soft text-warn",
        tone === "crit" && "border-crit bg-crit-soft text-crit",
        tone === "none" && "border-muted/40 bg-chip text-muted"
      )}
    >
      {tone === "ok" && <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />}
      {tone === "warn" && <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />}
      {tone === "crit" && <OctagonAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />}
      <span>{text}</span>
    </div>
  );
}

/** 回報資料錯誤：送進審核佇列，查證前不會自動改變結果 */
function ReportForm({ r, sessionId }: { r: RestaurantRecommendation; sessionId: string }) {
  const { showToast } = useToast();
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<ReportKind>("wrong_info");
  const [attr, setAttr] = useState("");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const pid = getStoredParticipant(sessionId);
  if (!pid) return null;

  const attributes = new Map<string, string>();
  r.declarations.forEach((d) => attributes.set(d.attribute, d.display));
  r.warnings.forEach((w) => {
    if (w.attribute && w.display) attributes.set(w.attribute, w.display);
  });

  async function send() {
    setBusy(true);
    setMsg(null);
    try {
      const res = await reportRestaurant(r.restaurant_id, {
        participant_id: pid as string,
        kind,
        attribute_code: attr || undefined,
        note: note.trim() || undefined,
      });
      setMsg({ ok: true, text: res.message });
      showToast("已收到回報，將由人工查證");
      setOpen(false);
      setNote("");
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    }
    setBusy(false);
  }

  return (
    <div className="mt-3 border-t border-line pt-2.5">
      {!open && (
        <button
          type="button"
          data-testid={`report-open-${r.rank}`}
          onClick={() => { setOpen(true); setMsg(null); }}
          className="inline-flex items-center gap-1.5 rounded-xl px-2 py-1.5 text-xs font-semibold text-muted transition hover:bg-chip hover:text-crit"
        >
          <Flag className="h-3.5 w-3.5" aria-hidden="true" />
          回報資料錯誤
        </button>
      )}
      {open && (
        <div className="mt-2 space-y-2 rounded-2xl border border-line bg-chip p-3.5 animate-pop-in">
          <div className="text-xs font-extrabold text-ink">回報「{r.name}」的資料問題</div>
          <select
            aria-label="哪裡有問題"
            value={kind}
            onChange={(e) => setKind(e.target.value as ReportKind)}
            className="h-11 w-full rounded-xl border-2 border-line bg-surface px-3 text-sm font-medium text-ink"
          >
            {KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <select
            aria-label="和哪一項有關"
            value={attr}
            onChange={(e) => setAttr(e.target.value)}
            className="h-11 w-full rounded-xl border-2 border-line bg-surface px-3 text-sm font-medium text-ink"
          >
            <option value="">整體 / 不確定</option>
            {[...attributes].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <input
            aria-label="說明"
            placeholder="補充說明（選填）"
            maxLength={300}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="h-11 w-full rounded-xl border-2 border-line bg-surface px-3 text-sm text-ink"
          />
          <p className="text-[0.74rem] text-muted">交給審核人員查證，查證前不會改變結果。每人 24 小時最多 3 次。</p>
          <div className="flex gap-2">
            <GameButton type="button" variant="primary" size="sm" className="flex-1" disabled={busy} onClick={send}>
              {busy ? "送出中…" : "送出回報"}
            </GameButton>
            <GameButton type="button" variant="secondary" size="sm" className="flex-1" onClick={() => setOpen(false)}>
              取消
            </GameButton>
          </div>
        </div>
      )}
      {msg && (
        <div
          data-testid={`report-msg-${r.rank}`}
          className={cn("mt-1.5 text-xs font-semibold", msg.ok ? "text-ok" : "text-crit")}
        >
          {msg.text}
        </div>
      )}
    </div>
  );
}

function ScorePill({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="flex flex-col rounded-xl border border-line bg-chip/80 px-2.5 py-1.5 text-center">
      <span className="text-[0.68rem] font-semibold text-muted">{label}</span>
      <span className="text-sm font-extrabold text-ink">{value}</span>
    </div>
  );
}

export function RestaurantCard({ r, sessionId }: { r: RestaurantRecommendation; sessionId: string }) {
  const [open, setOpen] = useState(false);
  const sorted: Warning[] = [...r.warnings]
    .filter((w) => !isUnknownRow(w, r.hard_constraint.unknown_attributes))
    .sort((a, b) => ORDER[a.level] - ORDER[b.level]);
  const inline = sorted.filter((w) => w.level !== "normal").slice(0, 2);
  const more = sorted.length - inline.length;
  const sc = r.score;
  const isFirst = r.rank === 1;
  const mapsQuery = encodeURIComponent(`${r.name} ${r.address ?? "高雄市鹽埕區"}`);

  return (
    <article
      data-testid={`rec-${r.rank}`}
      className={cn(
        "my-3.5 rounded-3xl border-2 bg-surface p-4 transition-all animate-pop-in",
        isFirst
          ? "border-brand shadow-card-pop ring-4 ring-brand/10"
          : "border-line shadow-card"
      )}
    >
      {/* 排名與分數頂列 */}
      <div className="mb-2 flex items-center justify-between gap-2">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-extrabold",
            isFirst
              ? "bg-gradient-to-r from-brand-2 to-brand text-white shadow-sm"
              : "bg-chip text-muted"
          )}
        >
          {isFirst && <Crown className="h-3.5 w-3.5" aria-hidden="true" />}
          {isFirst ? "最符合大家" : `第 ${r.rank} 名`}
        </span>
        <span className="inline-flex items-center gap-1 rounded-full bg-brand-soft px-3 py-1 text-xs font-black text-brand">
          <Sparkles className="h-3 w-3" aria-hidden="true" />
          {sc.total} 分
        </span>
      </div>

      {/* 店名與基本資訊 */}
      <h2 className="m-0 text-xl font-black tracking-tight text-ink">{r.name}</h2>
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs font-semibold text-muted">
        <span>{r.cuisines.join("、") || "料理類型未知"}</span>
        <span aria-hidden="true">·</span>
        <span className="inline-flex items-center gap-0.5">
          <MapPin className="h-3.5 w-3.5 text-brand/80" aria-hidden="true" />
          {r.distance_m != null ? `距離 ${r.distance_m} 公尺` : "距離未知"}
        </span>
      </div>

      {/* 安全狀態列（永不收合） */}
      <StatusBanner r={r} />

      {/* 重要／注意警示（永不收合） */}
      {inline.length > 0 && (
        <div className="my-2 space-y-1.5">
          {inline.map((w, i) => (
            <div key={i} className="flex items-start gap-2 text-xs leading-relaxed text-ink">
              <span className={cn("mt-0.5 shrink-0 rounded-full border px-2 py-0.5 text-[0.68rem] font-extrabold", LEVEL_STYLE[w.level])}>
                {LEVEL_TEXT[w.level]}
              </span>
              <span>{w.text}</span>
            </div>
          ))}
        </div>
      )}

      {/* 攜伴需求膠囊 */}
      {r.needs.length > 0 && (
        <div className="my-2.5 flex flex-wrap gap-1.5" data-testid={`needs-${r.rank}`}>
          {r.needs.map((n) => (
            <span
              key={n.code}
              className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold", NEED_SHORT[n.status][1])}
            >
              {n.code === "pets" ? "🐾" : "🧒"} {n.name}：{NEED_SHORT[n.status][0]}
            </span>
          ))}
        </div>
      )}

      {/* 店家聲明膠囊 */}
      {r.declarations.length > 0 && (
        <div className="my-2.5 flex flex-wrap gap-1.5" data-testid={`declarations-${r.rank}`}>
          {r.declarations.map((d) => (
            <span
              key={d.attribute}
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold",
                d.verified ? "bg-ok-soft text-ok" : "bg-chip text-muted"
              )}
            >
              <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
              店家聲明{d.verified ? "・已驗證" : ""}：{d.display}
            </span>
          ))}
        </div>
      )}

      {/* 展開／收起按鈕 */}
      <button
        type="button"
        aria-expanded={open}
        data-testid={`more-${r.rank}`}
        onClick={() => setOpen((v) => !v)}
        className="mt-2 flex min-h-[40px] w-full items-center justify-center gap-1.5 rounded-2xl border-2 border-line bg-chip/60 px-3 text-xs font-extrabold text-ink transition hover:border-brand/40 hover:bg-brand-soft/40 cursor-pointer"
      >
        <span>{open ? "收起詳細說明" : `查看原因${more > 0 ? `（還有 ${more} 則提醒）` : ""}`}</span>
        <ChevronDown className={cn("h-4 w-4 transition-transform duration-200", open && "rotate-180")} aria-hidden="true" />
      </button>

      {/* 展開內容區 */}
      {open && (
        <div className="mt-3.5 space-y-3.5 border-t-2 border-dashed border-line pt-3.5 animate-pop-in" data-testid={`detail-${r.rank}`}>
          <div>
            <h3 className="mb-1.5 text-xs font-extrabold uppercase tracking-wider text-brand">為什麼推薦</h3>
            <ul className="m-0 list-none space-y-1 p-0 text-sm text-ink">
              {r.reasons.map((t, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" aria-hidden="true" />
                  <span>{t}</span>
                </li>
              ))}
            </ul>
          </div>

          {sorted.length > inline.length && (
            <div>
              <h3 className="mb-1.5 text-xs font-extrabold text-warn">其他提醒</h3>
              <div className="space-y-1.5">
                {sorted
                  .filter((w) => !inline.includes(w))
                  .map((w, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs leading-relaxed text-ink">
                      <span className={cn("mt-0.5 shrink-0 rounded-full border px-2 py-0.5 text-[0.68rem] font-extrabold", LEVEL_STYLE[w.level])}>
                        {LEVEL_TEXT[w.level]}
                      </span>
                      <span>{w.text}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {(r.declarations.length > 0 || r.needs.some((n) => n.status !== "unknown")) && (
            <div>
              <h3 className="mb-1.5 text-xs font-extrabold text-ok">店家說的</h3>
              <div className="space-y-1 text-xs leading-relaxed text-ink">
                {r.declarations.map((d) => <div key={d.attribute}>・{d.text}</div>)}
                {r.needs.filter((n) => n.status !== "unknown").map((n) => <div key={n.code}>・{n.name}：{n.text}</div>)}
              </div>
            </div>
          )}

          {/* 分數拆解網格 */}
          <div>
            <h3 className="mb-1.5 text-xs font-extrabold text-muted">分數組成</h3>
            <div className="grid grid-cols-5 gap-1.5">
              <ScorePill label="料理" value={sc.cuisine} />
              <ScorePill label="距離" value={sc.distance} />
              <ScorePill label="可信度" value={sc.data_confidence} />
              <ScorePill label="評價" value="—" />
              <ScorePill label="價格" value="—" />
            </div>
          </div>

          {/* 地址、電話與 Google 地圖捷徑 */}
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-chip/70 px-3 py-2.5 text-xs text-muted">
            <div className="space-y-0.5">
              <div className="flex items-center gap-1 font-medium text-ink">
                <MapPin className="h-3.5 w-3.5 shrink-0 text-brand" aria-hidden="true" />
                <span>{r.address || "地址未知"}</span>
              </div>
              {r.phone && (
                <div className="flex items-center gap-1">
                  <Phone className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  <a href={`tel:${r.phone}`} className="underline">{r.phone}</a>
                </div>
              )}
            </div>
            <a
              href={`https://www.google.com/maps/search/?api=1&query=${mapsQuery}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-xl border border-line bg-surface px-2.5 py-1.5 text-xs font-bold text-brand no-underline shadow-sm hover:border-brand"
            >
              地圖
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          </div>

          <ReportForm r={r} sessionId={sessionId} />
        </div>
      )}
    </article>
  );
}
