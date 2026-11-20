"use client";
// 畫面 6：時間票選 — 互動時段卡、即時人數長條圖與主揪結算防呆確認
import { Calendar, Check, Clock, Crown, Lock } from "lucide-react";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useToast } from "@/components/Toast";
import { Back, BottomBar, ErrorBox, GameButton, Meter, SkeletonCard } from "@/components/ui";
import { useParticipant } from "@/hooks/useParticipant";
import { closeTimePoll, getTimePoll, putTimeVotes } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { TimePoll } from "@/lib/types";

const day = (iso: string) =>
  new Date(iso).toLocaleDateString("zh-TW", { month: "numeric", day: "numeric", weekday: "short" });
const hm = (iso: string) =>
  new Date(iso).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false });
const full = (iso: string) =>
  new Date(iso).toLocaleString("zh-TW", {
    month: "numeric",
    day: "numeric",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

export default function TimePollPage() {
  const { id } = useParams<{ id: string }>();
  const { showToast } = useToast();
  const { participant, error: joinError } = useParticipant(id);
  const [poll, setPoll] = useState<TimePoll | null>(null);
  const [mine, setMine] = useState<Set<number>>(new Set());
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const p = await getTimePoll(id, participant?.participant_id);
      setPoll(p);
      if (!dirty) setMine(new Set(p.options.filter((o) => o.mine).map((o) => o.option_id)));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [id, participant, dirty]);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const toggle = (oid: number) => {
    setDirty(true);
    setSaved(false);
    setMine((s) => {
      const n = new Set(s);
      n.has(oid) ? n.delete(oid) : n.add(oid);
      return n;
    });
  };

  async function save() {
    if (!participant) return;
    setBusy(true);
    setError(null);
    try {
      setPoll(await putTimeVotes(participant.participant_id, [...mine]));
      setDirty(false);
      setSaved(true);
      showToast("已儲存你可以的時間！");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  }

  async function closeNow() {
    if (!participant) return;
    setBusy(true);
    setError(null);
    try {
      setPoll(await closeTimePoll(id, participant.participant_id));
      showToast("時間投票已結算！");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  }

  const days = poll ? [...new Set(poll.options.map((o) => day(o.starts_at)))] : [];
  const top = poll ? Math.max(0, ...poll.options.map((o) => o.count)) : 0;
  const totalExpected = poll ? poll.party_size ?? poll.joined : 0;

  return (
    <div className="space-y-3.5">
      <Back href={`/s/${id}`}>回到聚餐</Back>

      <header>
        <h1 className="m-0 flex items-center gap-2 text-2xl font-black text-ink">
          <Clock className="h-6 w-6 text-brand" aria-hidden="true" />
          什麼時候可以？
        </h1>
      </header>

      <ErrorBox message={joinError || error} />

      {!poll ? (
        <SkeletonCard lines={4} />
      ) : (
        <>
          {poll.closed ? (
            <section
              data-testid="poll-result"
              className="rounded-3xl bg-gradient-to-br from-brand-2 to-brand p-5 text-white shadow-hero animate-pop-in"
            >
              {poll.meal_time ? (
                <>
                  <div className="inline-flex items-center gap-1 rounded-full bg-white/20 px-2.5 py-0.5 text-xs font-extrabold">
                    <Crown className="h-3.5 w-3.5" aria-hidden="true" />
                    就這個時間！
                  </div>
                  <h2 className="m-0 mt-2 text-2xl font-black">{full(poll.meal_time)}</h2>
                </>
              ) : (
                <div className="text-sm font-bold">投票結束，但沒有人勾選時間。</div>
              )}
            </section>
          ) : (
            <section className="rounded-3xl border-2 border-line bg-surface p-4 shadow-card">
              <div className="flex items-baseline justify-between text-xs font-bold">
                <span className="text-ink">勾選所有你可以的時段</span>
                <span className="text-brand">
                  {poll.responded} / {totalExpected} 人已填
                </span>
              </div>
              <Meter value={poll.responded} total={totalExpected} />
              <div className="flex flex-wrap items-center justify-between gap-1 text-[0.74rem] text-muted">
                <span>{poll.deadline ? `${full(poll.deadline)} 截止` : "尚未設定截止時間"}</span>
                <span className="inline-flex items-center gap-1">
                  <Lock className="h-3 w-3" aria-hidden="true" />
                  只顯示人數，看不到是誰
                </span>
              </div>
            </section>
          )}

          {days.map((d) => (
            <section key={d} className="rounded-3xl border-2 border-line bg-surface p-4 shadow-card">
              <h2 className="mb-3 flex items-center gap-1.5 text-base font-black text-ink">
                <Calendar className="h-4 w-4 text-brand" aria-hidden="true" />
                {d}
              </h2>
              <div className="space-y-2">
                {poll.options
                  .filter((o) => day(o.starts_at) === d)
                  .map((o) => {
                    const checked = mine.has(o.option_id);
                    const isWinner = o.option_id === poll.chosen_option_id;
                    const isTop = o.count === top && top > 0;
                    const pct = totalExpected > 0 ? Math.min(100, Math.round((o.count / totalExpected) * 100)) : 0;

                    return (
                      <label
                        key={o.option_id}
                        className={cn(
                          "relative flex cursor-pointer items-center gap-3 overflow-hidden rounded-2xl border-2 p-3 transition-all",
                          poll.closed && "cursor-default",
                          isWinner
                            ? "border-ok bg-ok-soft/40"
                            : checked
                              ? "border-brand bg-brand-soft/60 shadow-sm"
                              : "border-line bg-bg hover:border-brand/40"
                        )}
                      >
                        {/* 底部淡淡的人數比例背景條 */}
                        <span
                          aria-hidden="true"
                          className={cn(
                            "pointer-events-none absolute inset-y-0 left-0 opacity-20 transition-all duration-300",
                            isTop ? "bg-ok" : "bg-brand"
                          )}
                          style={{ width: `${pct}%` }}
                        />
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={poll.closed}
                          onChange={() => toggle(o.option_id)}
                          aria-label={`${d} ${hm(o.starts_at)}`}
                          className="sr-only"
                        />
                        <span
                          aria-hidden="true"
                          className={cn(
                            "relative flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border-2 transition-all",
                            checked
                              ? "border-brand bg-brand text-white"
                              : "border-line bg-surface text-transparent"
                          )}
                        >
                          <Check className="h-4 w-4 stroke-[3]" />
                        </span>
                        <span className="relative flex-1 text-base font-extrabold text-ink">
                          {hm(o.starts_at)}
                          {isWinner && (
                            <span className="ml-2 inline-flex items-center gap-0.5 rounded-full bg-ok-soft px-2 py-0.5 text-xs font-black text-ok">
                              獲選
                            </span>
                          )}
                        </span>
                        <span
                          className={cn(
                            "relative inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-extrabold",
                            isTop ? "bg-ok-soft text-ok" : "bg-surface text-muted border border-line"
                          )}
                        >
                          {isTop && <Crown className="h-3 w-3" aria-hidden="true" />}
                          {o.count} 人
                        </span>
                      </label>
                    );
                  })}
              </div>
            </section>
          ))}

          {!poll.closed && participant && (
            <button
              type="button"
              onClick={() => setConfirmClose(true)}
              disabled={busy}
              data-testid="close-poll"
              className="w-full rounded-2xl py-2.5 text-center text-xs font-bold text-muted underline-offset-4 transition hover:text-brand hover:underline cursor-pointer"
            >
              結束投票並決定時間（主揪專用）
            </button>
          )}

          {!poll.closed && (
            <BottomBar>
              <GameButton
                type="button"
                variant="primary"
                className="w-full"
                onClick={save}
                disabled={busy || !participant || !dirty}
                data-testid="save-time"
              >
                {busy ? "儲存中…" : saved ? "已儲存 ✓" : dirty ? `儲存我的時間（已選 ${mine.size}）` : "勾選時段後儲存"}
              </GameButton>
            </BottomBar>
          )}
        </>
      )}

      <ConfirmDialog
        open={confirmClose}
        title="確定要結束時間投票嗎？"
        description="結束後系統會立刻選出最多人可以的時段，大家就不能再更改時間囉。"
        confirmLabel="結束並決定時間"
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
