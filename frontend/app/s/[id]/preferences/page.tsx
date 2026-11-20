"use client";
// 畫面 4：想吃的料理 — 活潑 2 欄美食卡片網格，沒點＝都可以
import { Check, Eraser, Sparkles, Utensils } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Back, BottomBar, ErrorBox, GameButton, JourneyHeader, SkeletonCard } from "@/components/ui";
import { useParticipant } from "@/hooks/useParticipant";
import { getAnswers, getCuisines, getDietMeta, submitPreferences } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { CuisineMeta } from "@/lib/types";

const LOOK: Record<string, [string, string]> = {
  台式: ["🥢", "家常 · 便當"],
  中式: ["🥟", "合菜 · 麵點"],
  日式: ["🍣", "壽司 · 拉麵"],
  韓式: ["🥘", "炸雞 · 鍋物"],
  火鍋: ["🍲", "麻辣 · 涮涮"],
  燒肉: ["🥩", "炭火 · 居酒屋"],
  熱炒: ["🍳", "熱鬧 · 小酌"],
  小吃: ["🍜", "麵 · 米粉"],
  義式: ["🍝", "披薩 · 義大利麵"],
  歐式: ["🥐", "早午餐 · 輕食"],
  美式: ["🍔", "漢堡 · 排餐"],
  東南亞: ["🍛", "泰式 · 越式"],
  印度料理: ["🍛", "咖哩 · 烤餅"],
  甜點: ["🍰", "蛋糕 · 冰品"],
  咖啡廳: ["☕", "咖啡 · 輕食"],
};

export default function PreferencesPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { participant, error: joinError } = useParticipant(id);
  const [meta, setMeta] = useState<CuisineMeta | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [wasSubmitted, setWasSubmitted] = useState(false);
  const [fromType, setFromType] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getCuisines().then(setMeta).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!participant) return;
    const apply = new URLSearchParams(window.location.search).get("apply") === "type";
    getAnswers(participant.participant_id)
      .then(async (a) => {
        if (a.preferences_submitted) {
          setWasSubmitted(true);
          setPicked(
            new Set(
              a.preferences
                .filter((p) => p.stance === "love" || p.stance === "ok")
                .map((p) => p.cuisine_tag)
            )
          );
        }
        if (a.diet_type && (apply || !a.preferences_submitted)) {
          const t = (await getDietMeta()).types.find((x) => x.code === a.diet_type);
          if (t) {
            setPicked(new Set(t.suggested_cuisines));
            setFromType(`${t.emoji} ${t.name}`);
          }
        }
      })
      .catch(() => undefined);
  }, [participant]);

  const toggle = (tag: string) =>
    setPicked((s) => {
      const n = new Set(s);
      n.has(tag) ? n.delete(tag) : n.add(tag);
      return n;
    });

  async function save() {
    if (!participant) return;
    setBusy(true);
    setError(null);
    try {
      await submitPreferences(
        participant.participant_id,
        [...picked].map((cuisine_tag) => ({ cuisine_tag, stance: "love" as const }))
      );
      router.push(`/s/${id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3.5">
      <Back href={`/s/${id}`}>回到聚餐</Back>
      <JourneyHeader current="preferences" />

      <header className="flex items-start justify-between gap-2">
        <div>
          <h1 className="m-0 flex items-center gap-2 text-2xl font-black text-ink">
            <Utensils className="h-6 w-6 text-brand" aria-hidden="true" />
            今天想吃什麼？
          </h1>
          <p className="m-0 mt-1 text-sm font-medium text-muted">點選想吃的，沒點的代表都可以喔</p>
        </div>
        <span className="shrink-0 rounded-full bg-brand-soft px-3 py-1 text-xs font-black text-brand">
          已選 {picked.size}
        </span>
      </header>

      <ErrorBox message={joinError || error} />

      {fromType && (
        <div
          data-testid="type-note"
          className="flex items-center gap-2 rounded-2xl border-2 border-brand/30 bg-brand-soft px-3.5 py-2.5 text-xs font-bold text-brand animate-pop-in"
        >
          <Sparkles className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>已依「{fromType}」幫你預選，隨時可以增減！</span>
        </div>
      )}

      {!meta ? (
        <SkeletonCard lines={4} />
      ) : (
        <div className="grid grid-cols-2 gap-2.5" data-testid="cuisines">
          {meta.chips.map((c) => {
            const [emoji, sub] = LOOK[c.tag] ?? ["🍽", ""];
            const isOn = picked.has(c.tag);
            return (
              <button
                key={c.tag}
                type="button"
                aria-pressed={isOn}
                onClick={() => toggle(c.tag)}
                className={cn(
                  "relative flex min-h-[72px] items-center gap-2.5 rounded-2xl border-2 p-3 text-left transition-all cursor-pointer active:scale-[0.97]",
                  isOn
                    ? "border-brand bg-brand-soft shadow-card-pop"
                    : "border-line bg-surface shadow-card hover:border-brand/40"
                )}
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-2xl transition-transform",
                    isOn ? "bg-surface shadow-sm scale-105" : "bg-chip"
                  )}
                >
                  {emoji}
                </span>
                <span className="min-w-0 flex-1">
                  <b className={cn("block truncate text-sm font-extrabold", isOn ? "text-brand" : "text-ink")}>
                    {c.label}
                  </b>
                  {sub && <small className="block truncate text-[0.72rem] font-medium text-muted">{sub}</small>}
                </span>
                {isOn && (
                  <span
                    aria-hidden="true"
                    className="absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-brand text-white shadow-sm animate-badge-bounce"
                  >
                    <Check className="h-3.5 w-3.5 stroke-[3]" />
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      <BottomBar>
        <GameButton type="button" variant="secondary" onClick={() => setPicked(new Set())} disabled={busy || picked.size === 0}>
          <Eraser className="h-4 w-4" aria-hidden="true" />
          清除
        </GameButton>
        <GameButton type="button" variant="primary" className="flex-1" onClick={save} disabled={busy || !participant} data-testid="save">
          {busy
            ? "儲存中…"
            : picked.size === 0
              ? wasSubmitted
                ? "我都好，更新"
                : "我都好，完成"
              : `${wasSubmitted ? "更新" : "完成"}（已選 ${picked.size}）`}
        </GameButton>
      </BottomBar>
    </div>
  );
}
