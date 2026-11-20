"use client";
// 畫面 5：飲食類型測驗（飲食 MBTI）— 單題推進互動卡片 ＋ 遊戲化吃貨角色結果卡
import { ArrowLeft, ArrowRight, Check, RotateCcw, Sparkles, Utensils } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Back, BottomBar, ErrorBox, GameButton, Meter, SkeletonCard } from "@/components/ui";
import { useParticipant } from "@/hooks/useParticipant";
import { getAnswers, getDietMeta, putDietType } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { DietMeta, DietType } from "@/lib/types";

export default function DietTypePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { participant, error: joinError } = useParticipant(id);
  const [meta, setMeta] = useState<DietMeta | null>(null);
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [step, setStep] = useState(0);
  const [result, setResult] = useState<DietType | null>(null);
  const [retaking, setRetaking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getDietMeta().then(setMeta).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!participant || !meta) return;
    getAnswers(participant.participant_id)
      .then((a) => {
        const t = meta.types.find((x) => x.code === a.diet_type);
        if (t) setResult(t);
      })
      .catch(() => undefined);
  }, [participant, meta]);

  const questions = meta?.questions ?? [];
  const total = questions.length || 9;
  const done = Object.keys(picked).length;
  const currentQ = questions[step];

  function choose(qId: string, val: string) {
    setPicked((cur) => ({ ...cur, [qId]: val }));
    // 自動順暢推進到下一題（最後一題留在當頁等待點擊揭曉）
    if (step < total - 1) {
      setTimeout(() => setStep((s) => Math.min(total - 1, s + 1)), 180);
    }
  }

  async function submit() {
    if (!participant) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await putDietType(participant.participant_id, picked));
      setRetaking(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  }

  if (result && !retaking) {
    return (
      <div data-testid="type-result" className="space-y-4">
        <Back href={`/s/${id}`}>回到聚餐</Back>

        {/* 吃貨角色收藏卡 */}
        <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-2 via-brand to-brand-dark p-6 text-center text-white shadow-hero animate-pop-in">
          <div className="pointer-events-none absolute -left-8 -top-8 h-32 w-32 rounded-full bg-white/15 blur-xl" />
          <div className="pointer-events-none absolute -bottom-10 -right-10 h-40 w-40 rounded-full bg-white/10 blur-2xl" />
          <div className="relative">
            <span className="inline-flex items-center gap-1 rounded-full bg-white/20 px-3 py-1 text-xs font-extrabold">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              你的吃貨角色卡
            </span>
            <div className="mx-auto my-4 flex h-24 w-24 items-center justify-center rounded-3xl bg-white/20 text-6xl shadow-inner backdrop-blur-sm animate-badge-bounce">
              {result.emoji}
            </div>
            <h1 className="m-0 text-3xl font-black tracking-tight">{result.name}</h1>
            <p className="mx-auto mt-2.5 max-w-xs text-sm font-medium leading-relaxed text-white/95">
              {result.summary}
            </p>
          </div>
        </section>

        {/* 推薦料理建議 */}
        <section className="rounded-3xl border-2 border-line bg-surface p-4 shadow-card">
          <h2 className="mb-2.5 flex items-center gap-1.5 text-base font-black text-ink">
            <Utensils className="h-4 w-4 text-brand" aria-hidden="true" />
            適合你的料理
          </h2>
          <div className="flex flex-wrap gap-2">
            {result.suggested_cuisines.map((c) => (
              <span
                key={c}
                className="inline-flex items-center rounded-full border-2 border-brand/25 bg-brand-soft px-3.5 py-1.5 text-sm font-extrabold text-brand"
              >
                {c}
              </span>
            ))}
          </div>
          <p className="mt-3 mb-0 text-xs text-muted">
            只是趣味建議：不會影響你的限制，也不會自動改變推薦結果。
          </p>
        </section>

        <Link
          href={`/s/${id}`}
          className="flex min-h-[44px] w-full items-center justify-center rounded-2xl border-2 border-line bg-surface text-sm font-bold text-muted no-underline transition hover:text-ink"
        >
          先不用，回聚餐主頁
        </Link>

        <BottomBar>
          <GameButton
            type="button"
            variant="secondary"
            onClick={() => {
              setPicked({});
              setStep(0);
              setRetaking(true);
            }}
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            重測
          </GameButton>
          <GameButton
            type="button"
            variant="primary"
            className="flex-1"
            onClick={() => router.push(`/s/${id}/preferences?apply=type`)}
            data-testid="apply"
          >
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            用這些當我的偏好
          </GameButton>
        </BottomBar>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Back href={`/s/${id}`}>回到聚餐</Back>

      <header>
        <div className="flex items-center justify-between">
          <h1 className="m-0 text-2xl font-black text-ink">你是哪一種吃貨？ 🍜</h1>
          <span className="rounded-full bg-brand-soft px-3 py-1 text-xs font-black text-brand">
            {Math.min(step + 1, total)} / {total}
          </span>
        </div>
        <p className="m-0 mt-1 text-xs font-semibold text-muted">9 題小測驗，直覺選比較像你的就行</p>
        <Meter value={done} total={total} />
      </header>

      <ErrorBox message={joinError || error} />

      {/* 題號快速跳轉點點 */}
      {questions.length > 0 && (
        <div className="flex items-center justify-center gap-1.5" role="tablist" aria-label="測驗題號">
          {questions.map((q, idx) => {
            const answered = !!picked[q.id];
            const isNow = idx === step;
            return (
              <button
                key={q.id}
                type="button"
                aria-label={`第 ${idx + 1} 題${answered ? "（已答）" : ""}`}
                onClick={() => setStep(idx)}
                className={cn(
                  "h-2.5 rounded-full transition-all cursor-pointer",
                  isNow ? "w-7 bg-brand" : answered ? "w-2.5 bg-ok" : "w-2.5 bg-line"
                )}
              />
            );
          })}
        </div>
      )}

      {/* 單題互動測驗卡片 */}
      {!currentQ ? (
        <SkeletonCard lines={4} />
      ) : (
        <section
          key={currentQ.id}
          data-testid={`quiz-${currentQ.id}`}
          className="rounded-3xl border-2 border-line bg-surface p-5 shadow-card animate-pop-in"
        >
          <span className="inline-block rounded-full bg-brand-soft px-2.5 py-0.5 text-xs font-black text-brand">
            Q{step + 1}
          </span>
          <h2 className="mt-2.5 mb-4 text-lg font-black leading-snug text-ink">
            {currentQ.text}
          </h2>
          <div className="space-y-2.5">
            {currentQ.options.map((o) => {
              const active = picked[currentQ.id] === o.value;
              return (
                <button
                  key={o.value}
                  type="button"
                  aria-pressed={active}
                  onClick={() => choose(currentQ.id, o.value)}
                  className={cn(
                    "flex min-h-[56px] w-full items-center justify-between gap-3 rounded-2xl border-2 px-4 py-3 text-left text-sm font-bold transition-all cursor-pointer active:scale-[0.98]",
                    active
                      ? "border-brand bg-brand-soft text-brand shadow-card-pop"
                      : "border-line bg-bg text-ink hover:border-brand/50 hover:bg-surface"
                  )}
                >
                  <span>{o.label}</span>
                  {active && (
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand text-white animate-badge-bounce">
                      <Check className="h-3.5 w-3.5 stroke-[3]" />
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* 卡片內上下題切換 */}
          <div className="mt-4 flex items-center justify-between border-t border-line pt-3">
            <button
              type="button"
              disabled={step === 0}
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              className="inline-flex items-center gap-1 rounded-xl px-2.5 py-1.5 text-xs font-bold text-muted transition hover:bg-chip hover:text-ink disabled:opacity-35 cursor-pointer"
            >
              <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
              上一題
            </button>
            <button
              type="button"
              disabled={step >= total - 1}
              onClick={() => setStep((s) => Math.min(total - 1, s + 1))}
              className="inline-flex items-center gap-1 rounded-xl px-2.5 py-1.5 text-xs font-bold text-muted transition hover:bg-chip hover:text-ink disabled:opacity-35 cursor-pointer"
            >
              下一題
              <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        </section>
      )}

      <BottomBar>
        <GameButton
          type="button"
          variant="primary"
          className="w-full"
          disabled={busy || !participant || done < total}
          onClick={submit}
          data-testid="submit-quiz"
        >
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          {busy ? "分析吃貨基因中…" : done < total ? `還差 ${total - done} 題（已答 ${done}/${total}）` : "揭曉我的吃貨類型！"}
        </GameButton>
      </BottomBar>
    </div>
  );
}
