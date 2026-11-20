"use client";
// 畫面 2：聚餐主頁 — 團隊集氣進度、我的任務清單、邀請朋友與產生推薦
import {
  AlertTriangle,
  Check,
  Clock,
  Copy,
  Crown,
  MapPin,
  MessageCircle,
  Share2,
  Sparkles,
  Users,
  Vote,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useToast } from "@/components/Toast";
import {
  BottomBar,
  Chip,
  ErrorBox,
  GameButton,
  Hint,
  JourneyHeader,
  Meter,
  SkeletonCard,
  StepRow,
} from "@/components/ui";
import { useParticipant } from "@/hooks/useParticipant";
import {
  ApiError,
  getAnswers,
  getDietComposition,
  getDietMeta,
  getParticipant,
  getProgress,
  getSession,
  putNeeds,
  runRecommendation,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { shareText } from "@/lib/liff";
import type { DietComposition, DietType, Participant, Progress, Session } from "@/lib/types";

const fmt = (iso: string) =>
  new Date(iso).toLocaleString("zh-TW", {
    month: "numeric",
    day: "numeric",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

export default function SessionHub() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { showToast } = useToast();
  const { participant, error: joinError } = useParticipant(id);
  const [session, setSession] = useState<Session | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [me, setMe] = useState<Participant | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [canNativeShare, setCanNativeShare] = useState(false);
  const [myType, setMyType] = useState<DietType | null>(null);
  const [group, setGroup] = useState<DietComposition | null>(null);
  const [types, setTypes] = useState<DietType[]>([]);

  const refresh = useCallback(async () => {
    try {
      const [s, p] = await Promise.all([getSession(id), getProgress(id, participant?.participant_id)]);
      setSession(s);
      setProgress(p);
      if (participant) setMe(await getParticipant(participant.participant_id));
      setGroup(await getDietComposition(id));
      if (participant) {
        const a = await getAnswers(participant.participant_id);
        setMyType(types.find((t) => t.code === a.diet_type) ?? null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [id, participant, types]);

  useEffect(() => {
    getDietMeta().then((m) => setTypes(m.types)).catch(() => undefined);
  }, []);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [refresh]);
  useEffect(() => {
    setCanNativeShare(typeof navigator !== "undefined" && typeof navigator.share === "function");
  }, []);

  async function generate(allowPartial: boolean) {
    setBusy(true);
    setError(null);
    try {
      await runRecommendation(id, allowPartial);
      router.push(`/s/${id}/results`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  }

  async function toggleNeed(which: "pets" | "kids") {
    if (!session || !participant) return;
    setError(null);
    try {
      const n = await putNeeds(
        id,
        participant.participant_id,
        which === "pets" ? !session.needs_pets : session.needs_pets,
        which === "kids" ? !session.needs_kids : session.needs_kids
      );
      setSession({ ...session, needs_pets: n.needs_pets, needs_kids: n.needs_kids });
      showToast("已更新攜伴條件");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const link = typeof window !== "undefined" ? `${window.location.origin}/s/${id}` : "";
  const text = `來填「${session?.title ?? "聚餐"}」的飲食限制與偏好：\n${link}`;
  async function copy() {
    await navigator.clipboard?.writeText(link);
    setCopied(true);
    showToast("聚餐邀請連結已複製！");
    setTimeout(() => setCopied(false), 2000);
  }
  async function shareLine() {
    if (!(await shareText(text))) await copy();
  }
  async function shareNative() {
    try {
      await navigator.share({ title: session?.title ?? "揪呷", text, url: link });
    } catch {
      /* 使用者取消分享 */
    }
  }

  const cDone = !!me?.constraints_submitted;
  const pDone = !!me?.preferences_submitted;
  const poll = session?.time_mode === "poll";
  const finished = progress ? progress.participants.filter((p) => p.constraints_done && p.preferences_done).length : 0;
  const total = Math.max(progress?.party_size ?? 0, progress?.joined ?? 0);
  const when = session?.meal_time
    ? fmt(session.meal_time)
    : poll
      ? session?.time_closed
        ? "時間未定"
        : "時間投票中"
      : "";

  return (
    <div className="space-y-3.5">
      <JourneyHeader current="hub" />

      {/* 聚餐任務 Hero 儀表板 */}
      {!session ? (
        <SkeletonCard lines={2} />
      ) : (
        <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-2 to-brand p-5 text-white shadow-hero animate-pop-in">
          <div className="pointer-events-none absolute -right-10 -top-10 h-36 w-36 rounded-full bg-white/15 blur-xl" />
          <div className="relative">
            <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
              <span className="inline-flex items-center gap-1 rounded-full bg-white/20 px-2.5 py-0.5 text-xs font-extrabold">
                <Users className="h-3.5 w-3.5" aria-hidden="true" />
                {session.party_size} 人局
              </span>
              {me?.is_host && (
                <span className="inline-flex items-center gap-1 rounded-full bg-white/25 px-2.5 py-0.5 text-xs font-extrabold">
                  <Crown className="h-3.5 w-3.5" aria-hidden="true" />
                  主揪
                </span>
              )}
              {session.needs_pets && (
                <span className="rounded-full bg-white/20 px-2.5 py-0.5 text-xs font-bold">🐾 帶寵物</span>
              )}
              {session.needs_kids && (
                <span className="rounded-full bg-white/20 px-2.5 py-0.5 text-xs font-bold">🧒 帶小孩</span>
              )}
            </div>
            <h1 className="m-0 text-2xl font-black tracking-tight">{session.title}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs font-semibold text-white/90">
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
                {session.location_label ?? session.area ?? "—"}
              </span>
              {when && (
                <span className="inline-flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                  {when}
                </span>
              )}
            </div>
          </div>
        </section>
      )}

      {session?.outside_coverage && (
        <div
          data-testid="far-warning"
          className="flex items-start gap-2 rounded-2xl border-l-4 border-warn bg-warn-soft px-3.5 py-2.5 text-xs font-bold text-warn"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>集合點超出鹽埕區（目前只有這裡有餐廳資料）</span>
        </div>
      )}

      <ErrorBox message={joinError || error} />

      {/* 團隊集氣進度卡 */}
      <section className="rounded-3xl border-2 border-line bg-surface p-4 shadow-card" data-testid="progress">
        <div className="flex items-baseline justify-between">
          <h2 className="m-0 flex items-center gap-1.5 text-base font-black text-ink">
            🔥 大家的集氣進度
          </h2>
          <span className="rounded-full bg-brand-soft px-2.5 py-0.5 text-sm font-black text-brand">
            {finished} / {total || "?"} 人
          </span>
        </div>
        <Meter value={finished} total={total} />
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {progress?.participants.map((p, i) => {
            const ready = p.constraints_done && p.preferences_done;
            return (
              <span
                key={i}
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-bold",
                  ready
                    ? "border-ok/30 bg-ok-soft text-ok"
                    : "border-line bg-chip text-muted"
                )}
              >
                {ready ? (
                  <Check className="h-3.5 w-3.5 stroke-[3]" aria-hidden="true" />
                ) : (
                  <span className="h-2 w-2 animate-pulse rounded-full bg-brand/60" aria-hidden="true" />
                )}
                {p.label}
                {p.is_me ? "（我）" : ""}
              </span>
            );
          })}
        </div>
        <Hint>只顯示完成與否，看不到別人填了什麼。</Hint>
      </section>

      {/* 我的任務清單 */}
      <div>
        <div className="mb-1 px-1 text-xs font-extrabold uppercase tracking-wider text-muted">
          我的任務清單
        </div>
        <StepRow
          href={`/s/${id}/constraints`}
          icon="🛡"
          title="我的限制"
          sub={cDone ? "已填寫，點一下可修改" : "過敏、不吃、宗教（必答）"}
          done={cDone}
          badgeText="第一步"
          testid="step-constraints"
        />
        <StepRow
          href={`/s/${id}/preferences`}
          icon="🍜"
          title="想吃的料理"
          sub={pDone ? "已填寫，點一下可修改" : "點選想吃的，沒點都可以"}
          done={pDone}
          badgeText={cDone ? "下一步" : undefined}
          testid="step-preferences"
        />
        {poll && (
          <StepRow
            href={`/s/${id}/time`}
            icon="🕒"
            title="選我可以的時間"
            sub={session?.time_closed ? "投票已結束，點一下看結果" : "勾選所有可以的時段"}
            badgeText={session?.time_closed ? undefined : "投票中"}
            testid="step-time"
          />
        )}
        <StepRow
          href={`/s/${id}/type`}
          icon={myType?.emoji ?? "🎲"}
          title={myType ? `${myType.emoji} ${myType.name}` : "飲食類型小測驗"}
          sub={myType ? "點一下重測或看建議料理" : "1 分鐘 9 題，好玩又幫你預選料理（選填）"}
          badgeText={myType ? undefined : "趣味"}
          testid="step-type"
        />
      </div>

      {/* 團隊口味組成（至少 2 人測完才顯示） */}
      {group && !group.hidden && (
        <section data-testid="group-types" className="rounded-3xl border-2 border-line bg-surface p-4 shadow-card">
          <h2 className="mb-2 text-sm font-black text-ink">🎭 這團的吃貨組成</h2>
          <div className="flex flex-wrap gap-1.5">
            {group.types.map((t) => (
              <span
                key={t.code}
                className="inline-flex items-center gap-1 rounded-full bg-brand-soft px-3 py-1 text-xs font-extrabold text-brand"
              >
                {t.emoji} {t.name} × {t.count}
              </span>
            ))}
          </div>
          <Hint label="看看這團的口味拉鋸">
            <div className="space-y-2 py-1">
              {group.axes.map((a) => {
                const sum = Math.max(1, a.a.count + a.b.count);
                const pctA = Math.round((a.a.count / sum) * 100);
                return (
                  <div key={a.key}>
                    <div className="mb-0.5 flex justify-between text-[0.72rem] font-bold">
                      <span>{a.a.label} ({a.a.count})</span>
                      <span>({a.b.count}) {a.b.label}</span>
                    </div>
                    <div className="flex h-2 overflow-hidden rounded-full bg-surface">
                      <div className="bg-brand" style={{ width: `${pctA}%` }} />
                      <div className="bg-ok/70 flex-1" />
                    </div>
                  </div>
                );
              })}
              <div className="pt-1 text-[0.7rem] text-muted">只顯示人數，不顯示是誰。</div>
            </div>
          </Hint>
        </section>
      )}

      {/* 主揪攜伴開關 */}
      {me?.is_host && (
        <section className="rounded-3xl border-2 border-line bg-surface p-4 shadow-card" data-testid="needs-card">
          <h2 className="mb-2 text-sm font-black text-ink">這次有人攜伴嗎？（主揪設定）</h2>
          <div className="flex flex-wrap gap-2">
            <Chip on={!!session?.needs_pets} onClick={() => toggleNeed("pets")}>🐾 帶寵物</Chip>
            <Chip on={!!session?.needs_kids} onClick={() => toggleNeed("kids")}>🧒 帶小孩</Chip>
          </div>
          <Hint>改了之後要重新產生推薦才會套用。</Hint>
        </section>
      )}

      {/* 邀請朋友 */}
      <section className="rounded-3xl border-2 border-line bg-surface p-4 shadow-card" data-testid="share">
        <h2 className="mb-2.5 text-sm font-black text-ink">📣 邀請朋友一起填</h2>
        <div className="flex gap-2">
          <GameButton type="button" variant="line" size="sm" className="flex-1" onClick={shareLine}>
            <MessageCircle className="h-4 w-4" aria-hidden="true" />
            LINE
          </GameButton>
          <GameButton type="button" variant="secondary" size="sm" className="flex-1" onClick={copy} data-testid="copy-link">
            {copied ? <Check className="h-4 w-4 text-ok" aria-hidden="true" /> : <Copy className="h-4 w-4 text-brand" aria-hidden="true" />}
            {copied ? "已複製" : "複製連結"}
          </GameButton>
          {canNativeShare && (
            <GameButton type="button" variant="secondary" size="sm" onClick={shareNative} aria-label="用手機分享">
              <Share2 className="h-4 w-4 text-brand" aria-hidden="true" />
            </GameButton>
          )}
        </div>
        <Hint label="沒有 LINE 群組也可以">複製連結，貼到任何聊天室傳給朋友就行。</Hint>
      </section>

      {/* 快捷入口：上次推薦 & 最後投票 */}
      <div className="grid grid-cols-2 gap-2.5 pt-1">
        <Link
          href={`/s/${id}/results`}
          className="flex min-h-[44px] items-center justify-center gap-1.5 rounded-2xl border-2 border-line bg-surface px-3 text-sm font-bold text-ink no-underline shadow-sm transition hover:border-brand/50"
        >
          <Sparkles className="h-4 w-4 text-brand" aria-hidden="true" />
          上次的推薦
        </Link>
        <Link
          href={`/s/${id}/vote`}
          data-testid="step-vote"
          className="flex min-h-[44px] items-center justify-center gap-1.5 rounded-2xl border-2 border-line bg-surface px-3 text-sm font-bold text-ink no-underline shadow-sm transition hover:border-brand/50"
        >
          <Vote className="h-4 w-4 text-brand" aria-hidden="true" />
          最後投票
        </Link>
      </div>

      {/* 底部主行動列 */}
      <BottomBar>
        {progress && !progress.ready_for_recommendation && progress.joined > 0 && (
          <GameButton type="button" variant="secondary" disabled={busy} onClick={() => generate(true)}>
            先推薦
          </GameButton>
        )}
        <GameButton
          type="button"
          variant="primary"
          className="flex-1"
          disabled={busy || !progress?.ready_for_recommendation}
          onClick={() => generate(false)}
        >
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          {busy
            ? "計算中…"
            : progress?.ready_for_recommendation
              ? "產生推薦 Top 3"
              : `等大家填完（還差 ${progress?.missing_count ?? "?"} 人）`}
        </GameButton>
      </BottomBar>
    </div>
  );
}
