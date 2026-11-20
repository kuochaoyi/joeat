"use client";
// Session hub: who is done, what is left for me, invite, then the recommendation. One glance, one next step.
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { BottomBar, Chip, ErrorBox, Hint, Meter, StepRow } from "@/components/ui";
import { useParticipant } from "@/hooks/useParticipant";
import { ApiError, getAnswers, getDietComposition, getDietMeta, getParticipant, getProgress, getSession, putNeeds, runRecommendation } from "@/lib/api";
import { shareText } from "@/lib/liff";
import type { DietComposition, DietType, Participant, Progress, Session } from "@/lib/types";

const fmt = (iso: string) => new Date(iso).toLocaleString("zh-TW", { month: "numeric", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false });

export default function SessionHub() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
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
      setSession(s); setProgress(p);
      if (participant) setMe(await getParticipant(participant.participant_id));
      setGroup(await getDietComposition(id));
      if (participant) { const a = await getAnswers(participant.participant_id); setMyType(types.find((t) => t.code === a.diet_type) ?? null); }
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }, [id, participant, types]);

  useEffect(() => { getDietMeta().then((m) => setTypes(m.types)).catch(() => undefined); }, []);
  useEffect(() => { refresh(); const t = setInterval(refresh, 4000); return () => clearInterval(t); }, [refresh]);
  useEffect(() => { setCanNativeShare(typeof navigator !== "undefined" && typeof navigator.share === "function"); }, []);

  async function generate(allowPartial: boolean) {
    setBusy(true); setError(null);
    try { await runRecommendation(id, allowPartial); router.push(`/s/${id}/results`); }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); setBusy(false); }
  }
  async function toggleNeed(which: "pets" | "kids") {
    if (!session || !participant) return;
    setError(null);
    try {
      const n = await putNeeds(id, participant.participant_id, which === "pets" ? !session.needs_pets : session.needs_pets, which === "kids" ? !session.needs_kids : session.needs_kids);
      setSession({ ...session, needs_pets: n.needs_pets, needs_kids: n.needs_kids });
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  // The invitation link works for anybody, with or without a LINE group.
  const link = typeof window !== "undefined" ? `${window.location.origin}/s/${id}` : "";
  const text = `來填「${session?.title ?? "聚餐"}」的飲食限制與偏好：\n${link}`;
  async function copy() { await navigator.clipboard?.writeText(link); setCopied(true); setTimeout(() => setCopied(false), 2000); }
  async function shareLine() { if (!(await shareText(text))) await copy(); }
  async function shareNative() { try { await navigator.share({ title: session?.title ?? "揪呷", text, url: link }); } catch { /* the sheet was closed */ } }

  const cDone = !!me?.constraints_submitted, pDone = !!me?.preferences_submitted;
  const poll = session?.time_mode === "poll";
  const finished = progress ? progress.participants.filter((p) => p.constraints_done && p.preferences_done).length : 0;
  const total = Math.max(progress?.party_size ?? 0, progress?.joined ?? 0);
  const when = session?.meal_time ? fmt(session.meal_time) : poll ? (session?.time_closed ? "時間未定" : "時間投票中") : "";

  return (
    <div>
      <div className="hero">
        <h1>{session?.title ?? "載入中…"}</h1>
        <div className="muted">📍 {session?.location_label ?? session?.area ?? "—"}{when && ` · 🕒 ${when}`}</div>
        <div className="chips" style={{ marginTop: 10 }}>
          <span className="badge">👥 {session?.party_size ?? "?"} 人</span>
          {me?.is_host && <span className="badge">主揪</span>}
          {session?.needs_pets && <span className="badge">🐾 帶寵物</span>}
          {session?.needs_kids && <span className="badge">🧒 帶小孩</span>}
        </div>
      </div>
      {session?.outside_coverage && <div className="status warn" data-testid="far-warning">⚠ 集合點超出鹽埕區（目前只有這裡有餐廳資料）</div>}
      <ErrorBox message={joinError || error} />

      <div className="card" data-testid="progress">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <h2 style={{ margin: 0 }}>大家的進度</h2><b>{finished} / {total || "?"}</b>
        </div>
        <Meter value={finished} total={total} />
        <div className="chips">{progress?.participants.map((p, i) => <span key={i} className={`badge ${p.constraints_done && p.preferences_done ? "ok" : "normal"}`}>{p.constraints_done && p.preferences_done ? "✓" : "…"} {p.label}{p.is_me ? "（我）" : ""}</span>)}</div>
        <Hint>只顯示完成與否，看不到別人填了什麼。</Hint>
      </div>

      <StepRow href={`/s/${id}/constraints`} icon="🛡" title="我的限制" sub={cDone ? "已填寫，點一下可修改" : "過敏、不吃、宗教"} done={cDone} testid="step-constraints" />
      <StepRow href={`/s/${id}/preferences`} icon="🍜" title="想吃的料理" sub={pDone ? "已填寫，點一下可修改" : "勾選就好"} done={pDone} testid="step-preferences" />
      {poll && <StepRow href={`/s/${id}/time`} icon="🕒" title="選我可以的時間" sub={session?.time_closed ? "投票已結束" : "勾選所有可以的時段"} testid="step-time" />}
      <StepRow href={`/s/${id}/type`} icon={myType?.emoji ?? "🎲"} title={myType ? `${myType.emoji} ${myType.name}` : "飲食類型（選填）"} sub={myType ? "點一下重測或看建議料理" : "1 分鐘小測驗"} done={false} testid="step-type" />
      {group && !group.hidden && (
        <div data-testid="group-types" className="card" style={{ margin: "8px 0" }}>
          <div className="chips">{group.types.map((t) => <span key={t.code} className="badge brand">{t.emoji} {t.name} × {t.count}</span>)}</div>
          <Hint label="這團的口味分布">{group.axes.map((a) => <div key={a.key}>{a.a.label} {a.a.count} ：{a.b.count} {a.b.label}</div>)}<div className="tiny">只顯示人數，不顯示是誰。</div></Hint>
        </div>
      )}

      {me?.is_host && (
        <div className="card" data-testid="needs-card">
          <h2>這次有人攜伴嗎？</h2>
          <div className="chips">
            <Chip on={!!session?.needs_pets} onClick={() => toggleNeed("pets")}>🐾 帶寵物</Chip>
            <Chip on={!!session?.needs_kids} onClick={() => toggleNeed("kids")}>🧒 帶小孩</Chip>
          </div>
          <Hint>改了之後要重新產生推薦才會套用。</Hint>
        </div>
      )}

      <div className="card" data-testid="share">
        <h2>邀請朋友</h2>
        <div className="row">
          <button className="line small" onClick={shareLine}>💬 LINE</button>
          <button className="small" onClick={copy} data-testid="copy-link">{copied ? "已複製 ✓" : "📋 複製連結"}</button>
          {canNativeShare && <button className="small" onClick={shareNative}>📤 分享</button>}
        </div>
        <Hint label="沒有 LINE 群組也可以">複製連結，貼到任何地方傳給朋友就行。</Hint>
      </div>

      <div className="row" style={{ marginTop: 4 }}>
        <Link className="btn small" href={`/s/${id}/results`}>上次的推薦</Link>
        <Link className="btn small" href={`/s/${id}/vote`} data-testid="step-vote">🗳 最後投票</Link>
      </div>

      <BottomBar>
        {progress && !progress.ready_for_recommendation && progress.joined > 0 && <button className="narrow" disabled={busy} onClick={() => generate(true)}>先推薦</button>}
        <button className="primary" disabled={busy || !progress?.ready_for_recommendation} onClick={() => generate(false)}>
          {busy ? "計算中…" : progress?.ready_for_recommendation ? "產生推薦 Top 3" : `等大家填完（還差 ${progress?.missing_count ?? "?"} 人）`}
        </button>
      </BottomBar>
    </div>
  );
}
