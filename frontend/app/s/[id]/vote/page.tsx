"use client";
// 畫面 8：最後投票 — 動態心情色階 0–10 拉桿、防誤觸結算確認與開獎慶祝畫面
import { Crown, Lock, MapPin, PartyPopper, Sparkles, Vote as VoteIcon } from "lucide-react";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useToast } from "@/components/Toast";
import {
  Back,
  BottomBar,
  Chip,
  ErrorBox,
  GameButton,
  JourneyHeader,
  Meter,
  SkeletonCard,
} from "@/components/ui";
import { useParticipant } from "@/hooks/useParticipant";
import { ApiError, closeVote, getVote, putBallot, startVote } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { Vote } from "@/lib/types";

const when = (iso: string) =>
  new Date(iso).toLocaleString("zh-TW", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

const HOURS = [
  [1, "1 小時"],
  [6, "6 小時"],
  [12, "12 小時"],
  [24, "1 天"],
  [48, "2 天"],
] as const;

const NEED_BADGE: Record<string, string> = {
  yes: "bg-ok-soft text-ok",
  maybe: "bg-warn-soft text-warn",
  no: "bg-warn-soft text-warn",
  unknown: "bg-chip text-muted",
};

/** 依 0–10 分回傳活潑心情表情、文字與代表色 */
function getMood(score: number) {
  if (score <= 2) return { emoji: "😕", label: "不太想", color: "#64748b", badge: "bg-chip text-muted" };
  if (score <= 4) return { emoji: "😐", label: "還好", color: "#d97706", badge: "bg-warn-soft text-warn" };
  if (score <= 6) return { emoji: "🙂", label: "可以喔", color: "#ea580c", badge: "bg-brand-soft text-brand" };
  if (score <= 8) return { emoji: "😋", label: "很想吃", color: "#ff6b35", badge: "bg-brand-soft text-brand" };
  return { emoji: "🤩", label: "非吃不可！", color: "#e11d48", badge: "bg-crit-soft text-crit" };
}

export default function VotePage() {
  const { id } = useParams<{ id: string }>();
  const { showToast } = useToast();
  const { participant, error: joinError } = useParticipant(id);
  const [vote, setVote] = useState<Vote | null | undefined>(undefined);
  const [scores, setScores] = useState<Record<string, number>>({});
  const [anyOk, setAnyOk] = useState<Record<string, boolean>>({});
  const [touched, setTouched] = useState(false);
  const [hours, setHours] = useState(24);
  const [confirmClose, setConfirmClose] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const adopt = useCallback((v: Vote) => {
    setVote(v);
    setScores((cur) => {
      const n = { ...cur };
      for (const o of v.options) if (n[o.restaurant_id] === undefined) n[o.restaurant_id] = o.my_score ?? 5;
      return n;
    });
    setAnyOk((cur) => {
      const n = { ...cur };
      for (const o of v.options) if (n[o.restaurant_id] === undefined) n[o.restaurant_id] = o.my_any_ok;
      return n;
    });
  }, []);

  const load = useCallback(async () => {
    try {
      adopt(await getVote(id, participant?.participant_id));
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setVote(null);
      else setError(e instanceof Error ? e.message : String(e));
    }
  }, [id, participant, adopt]);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  async function start() {
    if (!participant) return;
    setBusy(true);
    setError(null);
    try {
      adopt(await startVote(id, participant.participant_id, hours));
      showToast("投票已開啟，快邀請大家來拉分數！");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  }

  async function submit() {
    if (!participant || !vote) return;
    setBusy(true);
    setError(null);
    try {
      adopt(
        await putBallot(
          vote.vote_id,
          participant.participant_id,
          vote.options.map((o) => ({
            restaurant_id: o.restaurant_id,
            score: scores[o.restaurant_id] ?? 5,
            any_ok: !!anyOk[o.restaurant_id],
          }))
        )
      );
      setTouched(false);
      showToast("投票送出成功！");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  }

  async function closeNow() {
    if (!participant || !vote) return;
    setBusy(true);
    setError(null);
    try {
      adopt(await closeVote(vote.vote_id, participant.participant_id));
      showToast("開獎完成！");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  }

  const winner = vote?.result?.find((r) => r.restaurant_id === vote.winner_restaurant_id);
  const top = Math.max(1, ...(vote?.result?.map((r) => r.total) ?? [1]));

  return (
    <div className="space-y-3.5">
      <Back href={`/s/${id}`}>回到聚餐</Back>
      <JourneyHeader current="vote" />

      <header>
        <h1 className="m-0 flex items-center gap-2 text-2xl font-black text-ink">
          <VoteIcon className="h-6 w-6 text-brand" aria-hidden="true" />
          最後投票
        </h1>
      </header>

      <ErrorBox message={joinError || error} />

      {vote === undefined && <SkeletonCard lines={4} />}

      {vote === null && (
        <section
          data-testid="no-vote"
          className="rounded-3xl border-2 border-line bg-surface p-5 shadow-card animate-pop-in"
        >
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-soft text-2xl">
            🗳
          </div>
          <h2 className="m-0 text-lg font-black text-ink">拉分數決定今晚吃哪間！</h2>
          <p className="mt-1 mb-4 text-sm text-muted">
            每間餐廳都能拉 0–10 分表達想去的程度，不用硬性三選一，全程匿名。
          </p>
          <label htmlFor="vote-hours" className="mb-1.5 block text-xs font-extrabold text-muted">
            投票截止時間
          </label>
          <select
            id="vote-hours"
            aria-label="投票截止"
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="h-12 w-full rounded-2xl border-2 border-line bg-bg px-3 text-sm font-bold text-ink"
          >
            {HOURS.map(([h, l]) => (
              <option key={h} value={h}>{l}後截止</option>
            ))}
          </select>
          <GameButton
            type="button"
            variant="primary"
            className="mt-4 w-full"
            onClick={start}
            disabled={busy || !participant}
            data-testid="start-vote"
          >
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            發起投票
          </GameButton>
          <div className="mt-2.5 text-center text-xs text-muted">需要先有推薦結果；由主揪發起。</div>
        </section>
      )}

      {vote && vote.status === "open" && (
        <>
          <section className="rounded-3xl border-2 border-line bg-surface p-4 shadow-card">
            <div className="flex items-baseline justify-between text-xs font-bold">
              <span className="text-ink">{when(vote.closes_at)} 截止</span>
              <span className="text-brand">已投 {vote.voted} / {vote.joined} 人</span>
            </div>
            <Meter value={vote.voted} total={vote.joined} />
            <div className="flex items-center gap-1 text-[0.74rem] text-muted">
              <Lock className="h-3 w-3" aria-hidden="true" />
              全程匿名，沒有人看得到你投給誰
            </div>
          </section>

          {vote.options.map((o) => {
            const any = !!anyOk[o.restaurant_id];
            const v = scores[o.restaurant_id] ?? 5;
            const mood = getMood(v);
            return (
              <section
                key={o.restaurant_id}
                data-testid={`opt-${o.rank}`}
                className={cn(
                  "rounded-3xl border-2 bg-surface p-4 shadow-card transition-all",
                  any ? "border-line/70 opacity-85" : "border-line"
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <span className="inline-block rounded-full bg-brand-soft px-2 py-0.5 text-[0.7rem] font-black text-brand">
                      #{o.rank}
                    </span>
                    <h2 className="m-0 mt-1 text-lg font-black text-ink">{o.name}</h2>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-xs font-semibold text-muted">
                      <span>{o.cuisines.join("、") || "料理類型未知"}</span>
                      <span>·</span>
                      <span className="inline-flex items-center gap-0.5">
                        <MapPin className="h-3 w-3" aria-hidden="true" />
                        {o.distance_m != null ? `${o.distance_m} 公尺` : "距離未知"}
                      </span>
                    </div>
                  </div>
                  <div className="shrink-0 text-right">
                    {any ? (
                      <span className="inline-block rounded-2xl bg-chip px-3 py-1.5 text-sm font-black text-muted">
                        🤷 都可以
                      </span>
                    ) : (
                      <div className="flex flex-col items-end">
                        <span className="text-2xl font-black leading-none" style={{ color: mood.color }}>
                          {mood.emoji} {v}
                        </span>
                        <span className={cn("mt-1 rounded-full px-2 py-0.5 text-[0.68rem] font-extrabold", mood.badge)}>
                          {mood.label}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {(o.warnings.length > 0 || o.needs.length > 0) && (
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {o.warnings.slice(0, 2).map((w, i) => (
                      <span
                        key={i}
                        className={cn(
                          "rounded-full px-2.5 py-0.5 text-[0.7rem] font-bold",
                          w.level === "critical" ? "bg-crit-soft text-crit" : "bg-warn-soft text-warn"
                        )}
                      >
                        {w.text.length > 18 ? `${w.text.slice(0, 18)}…` : w.text}
                      </span>
                    ))}
                    {o.needs.map((n, i) => (
                      <span
                        key={`n${i}`}
                        className={cn("rounded-full px-2.5 py-0.5 text-[0.7rem] font-bold", NEED_BADGE[n.status] ?? "bg-chip text-muted")}
                      >
                        {n.name}
                      </span>
                    ))}
                  </div>
                )}

                {/* 動態色階心情拉桿 */}
                <div className={cn("mt-4 transition-opacity", any && "opacity-35")}>
                  <input
                    type="range"
                    className="game-slider"
                    style={{ "--slider-accent": mood.color } as React.CSSProperties}
                    min={0}
                    max={10}
                    step={1}
                    value={v}
                    disabled={any}
                    aria-label={`${o.name} 想去的程度`}
                    onChange={(e) => {
                      setTouched(true);
                      const n = Number(e.target.value);
                      setScores((cur) => ({ ...cur, [o.restaurant_id]: n }));
                    }}
                  />
                  <div className="mt-1.5 flex justify-between text-[0.74rem] font-bold text-muted">
                    <span>😕 不太想 (0)</span>
                    <span>非吃不可 🤩 (10)</span>
                  </div>
                </div>

                <div className="mt-3 flex items-center justify-between border-t border-line pt-2.5">
                  <Chip
                    on={any}
                    onClick={() => {
                      setTouched(true);
                      setAnyOk((cur) => ({ ...cur, [o.restaurant_id]: !cur[o.restaurant_id] }));
                    }}
                  >
                    🤷 這間我都可以
                  </Chip>
                  {any && <span className="text-xs font-semibold text-muted">交給大家決定</span>}
                </div>
              </section>
            );
          })}

          <button
            type="button"
            onClick={() => setConfirmClose(true)}
            disabled={busy}
            data-testid="close-vote"
            className="w-full rounded-2xl py-2.5 text-center text-xs font-bold text-muted underline-offset-4 transition hover:text-brand hover:underline cursor-pointer"
          >
            結束投票並公布結果（主揪專用）
          </button>

          <BottomBar>
            <GameButton
              type="button"
              variant="primary"
              className="w-full"
              onClick={submit}
              disabled={busy || !participant}
              data-testid="submit-ballot"
            >
              {busy
                ? "送出中…"
                : vote.i_voted
                  ? touched
                    ? "更新我的票"
                    : "已投票 ✓（隨時可改）"
                  : "送出我的票！"}
            </GameButton>
          </BottomBar>
        </>
      )}

      {vote && vote.status === "closed" && (
        <div data-testid="vote-result" className="space-y-3.5 animate-pop-in">
          {winner ? (
            <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-2 via-brand to-brand-dark p-6 text-center text-white shadow-hero">
              <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-white/15 blur-xl" />
              <div className="relative">
                <span className="inline-flex items-center gap-1 rounded-full bg-white/20 px-3 py-1 text-xs font-extrabold">
                  <PartyPopper className="h-3.5 w-3.5" aria-hidden="true" />
                  開獎！這次就吃這間
                </span>
                <h2 className="m-0 mt-3 text-3xl font-black tracking-tight">🎉 {winner.name}</h2>
                {vote.tie_broken && (
                  <p className="m-0 mt-2 text-xs font-semibold text-white/90">
                    同分，由系統推薦排名較前的勝出
                  </p>
                )}
              </div>
            </section>
          ) : (
            <section className="rounded-3xl border-2 border-line bg-surface p-5 text-center text-sm font-bold text-muted shadow-card">
              投票結束，但沒有人投票，所以還沒有決定。
            </section>
          )}

          {vote.result?.map((r) => {
            const isWin = r.restaurant_id === vote.winner_restaurant_id;
            return (
              <section
                key={r.restaurant_id}
                className={cn(
                  "rounded-3xl border-2 bg-surface p-4 shadow-card",
                  isWin ? "border-brand ring-4 ring-brand/10" : "border-line"
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <b className="flex items-center gap-1.5 text-base font-black text-ink">
                    {isWin && <Crown className="h-4 w-4 text-brand" aria-hidden="true" />}
                    {r.name}
                  </b>
                  <span className="rounded-full bg-brand-soft px-3 py-0.5 text-sm font-black text-brand">
                    總分 {r.total}
                  </span>
                </div>
                <Meter value={r.total} total={top} />
                <div className="mt-2 flex flex-wrap gap-1.5 text-xs font-bold">
                  <span className="rounded-lg bg-chip px-2 py-1 text-ink">平均 {r.average ?? "—"}</span>
                  <span className="rounded-lg bg-chip px-2 py-1 text-muted">{r.voters} 人投票</span>
                  <span className="rounded-lg bg-brand-soft px-2 py-1 text-brand">😋 {r.keen}</span>
                  <span className="rounded-lg bg-chip px-2 py-1 text-muted">😕 {r.unhappy}</span>
                  <span className="rounded-lg bg-chip px-2 py-1 text-muted">🤷 {r.any_ok}</span>
                </div>
              </section>
            );
          })}

          <div className="px-1 text-xs text-muted">只公布每間餐廳的統計，看不到個別的票。</div>
        </div>
      )}

      <ConfirmDialog
        open={confirmClose}
        title="確定要現在開獎嗎？"
        description="結束投票後會立刻統計總分並公布獲勝餐廳，大家就不能再改票囉。"
        confirmLabel="立刻結束並開獎"
        cancelLabel="再等一下"
        onConfirm={() => {
          setConfirmClose(false);
          closeNow();
        }}
        onCancel={() => setConfirmClose(false)}
      />
    </div>
  );
}
