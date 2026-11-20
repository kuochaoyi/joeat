"use client";
// Final vote: a slider for EVERY restaurant on the Top 3 (😕 would rather not ... 😋 really want to) or "anything is fine".
// Nobody sees who voted what; the totals appear when the vote closes (everyone voted, deadline, or the host closes it).
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Back, BottomBar, Chip, ErrorBox, Meter } from "@/components/ui";
import { useParticipant } from "@/hooks/useParticipant";
import { ApiError, closeVote, getVote, putBallot, startVote } from "@/lib/api";
import type { Vote } from "@/lib/types";

const when = (iso: string) => new Date(iso).toLocaleString("zh-TW", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
const HOURS = [[1, "1 小時"], [6, "6 小時"], [12, "12 小時"], [24, "1 天"], [48, "2 天"]] as const;
const NEED_BADGE: Record<string, string> = { yes: "ok", maybe: "high", no: "high", unknown: "normal" };

export default function VotePage() {
  const { id } = useParams<{ id: string }>();
  const { participant, error: joinError } = useParticipant(id);
  const [vote, setVote] = useState<Vote | null | undefined>(undefined);        // undefined = loading, null = no vote yet
  const [scores, setScores] = useState<Record<string, number>>({});
  const [anyOk, setAnyOk] = useState<Record<string, boolean>>({});
  const [touched, setTouched] = useState(false);
  const [hours, setHours] = useState(24);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const adopt = useCallback((v: Vote) => {
    setVote(v);
    setScores((cur) => { const n = { ...cur }; for (const o of v.options) if (n[o.restaurant_id] === undefined) n[o.restaurant_id] = o.my_score ?? 5; return n; });
    setAnyOk((cur) => { const n = { ...cur }; for (const o of v.options) if (n[o.restaurant_id] === undefined) n[o.restaurant_id] = o.my_any_ok; return n; });
  }, []);

  const load = useCallback(async () => {
    try { adopt(await getVote(id, participant?.participant_id)); }
    catch (e) { if (e instanceof ApiError && e.status === 404) setVote(null); else setError(e instanceof Error ? e.message : String(e)); }
  }, [id, participant, adopt]);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);

  async function start() {
    if (!participant) return;
    setBusy(true); setError(null);
    try { adopt(await startVote(id, participant.participant_id, hours)); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  }
  async function submit() {
    if (!participant || !vote) return;
    setBusy(true); setError(null);
    try {
      adopt(await putBallot(vote.vote_id, participant.participant_id, vote.options.map((o) => ({ restaurant_id: o.restaurant_id, score: scores[o.restaurant_id] ?? 5, any_ok: !!anyOk[o.restaurant_id] }))));
      setTouched(false);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  }
  async function closeNow() {
    if (!participant || !vote) return;
    setBusy(true); setError(null);
    try { adopt(await closeVote(vote.vote_id, participant.participant_id)); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  }

  const winner = vote?.result?.find((r) => r.restaurant_id === vote.winner_restaurant_id);
  const top = Math.max(1, ...(vote?.result?.map((r) => r.total) ?? [1]));
  return (
    <div>
      <Back href={`/s/${id}`}>回到聚餐</Back>
      <h1>最後投票 🗳</h1>
      <ErrorBox message={joinError || error} />

      {vote === null && (
        <div className="card" data-testid="no-vote">
          <p style={{ marginTop: 0 }}>每間餐廳拉一下「想去的程度」，不用三選一。</p>
          <select aria-label="投票截止" value={hours} onChange={(e) => setHours(Number(e.target.value))}>{HOURS.map(([h, l]) => <option key={h} value={h}>{l}後截止</option>)}</select>
          <button className="primary" style={{ width: "100%", marginTop: 12 }} onClick={start} disabled={busy || !participant} data-testid="start-vote">發起投票</button>
          <div className="tiny" style={{ marginTop: 8 }}>需要先有推薦結果；由主揪發起。</div>
        </div>
      )}

      {vote && vote.status === "open" && (
        <>
          <div className="muted">{when(vote.closes_at)} 截止 · 沒有人看得到你投給誰</div>
          <Meter value={vote.voted} total={vote.joined} />
          <div className="tiny" style={{ marginBottom: 6 }}>已投 {vote.voted} / {vote.joined} 人</div>
          {vote.options.map((o) => {
            const any = !!anyOk[o.restaurant_id];
            const v = scores[o.restaurant_id] ?? 5;
            return (
              <div className="card" key={o.restaurant_id} data-testid={`opt-${o.rank}`}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                  <div><h2 style={{ margin: 0 }}>#{o.rank} {o.name}</h2><div className="muted">{o.cuisines.join("、") || "料理類型未知"} · {o.distance_m != null ? `${o.distance_m} 公尺` : "距離未知"}</div></div>
                  <b style={{ fontSize: "1.5rem", color: any ? "var(--muted)" : "var(--brand)" }}>{any ? "都可以" : v}</b>
                </div>
                {(o.warnings.length > 0 || o.needs.length > 0) && (
                  <div className="chips" style={{ margin: "8px 0 0" }}>
                    {o.warnings.slice(0, 2).map((w, i) => <span key={i} className={`badge ${w.level === "critical" ? "crit" : "high"}`}>{w.text.length > 18 ? `${w.text.slice(0, 18)}…` : w.text}</span>)}
                    {o.needs.map((n, i) => <span key={`n${i}`} className={`badge ${NEED_BADGE[n.status] ?? "normal"}`}>{n.name}</span>)}
                  </div>
                )}
                <div style={{ marginTop: 12, opacity: any ? 0.35 : 1 }}>
                  <input type="range" min={0} max={10} step={1} value={v} disabled={any} aria-label={`${o.name} 想去的程度`}
                    onChange={(e) => { setTouched(true); const n = Number(e.target.value); setScores((cur) => ({ ...cur, [o.restaurant_id]: n })); }} />
                  <div className="row tiny" style={{ justifyContent: "space-between" }}><span>😕 不太想</span><span style={{ textAlign: "right" }}>很想去 😋</span></div>
                </div>
                <div style={{ marginTop: 8 }}>
                  <Chip on={any} onClick={() => { setTouched(true); setAnyOk((cur) => ({ ...cur, [o.restaurant_id]: !cur[o.restaurant_id] })); }}>🤷 都可以</Chip>
                </div>
              </div>
            );
          })}
          <button className="link" style={{ width: "100%" }} onClick={closeNow} disabled={busy} data-testid="close-vote">結束投票並公布（主揪）</button>
          <BottomBar>
            <button className="primary" onClick={submit} disabled={busy || !participant} data-testid="submit-ballot">{busy ? "送出中…" : vote.i_voted ? (touched ? "更新我的票" : "已投票 ✓（可再改）") : "送出我的票"}</button>
          </BottomBar>
        </>
      )}

      {vote && vote.status === "closed" && (
        <div data-testid="vote-result">
          {winner ? (
            <div className="hero"><div className="muted">今晚吃</div><h1>🎉 {winner.name}</h1>{vote.tie_broken && <div className="muted">同分，由推薦排名較前的勝出</div>}</div>
          ) : <div className="card">投票結束，但沒有人投票，所以還沒有決定。</div>}
          {vote.result?.map((r) => (
            <div className="card" key={r.restaurant_id}>
              <div style={{ display: "flex", justifyContent: "space-between" }}><b>{r.name}{r.restaurant_id === vote.winner_restaurant_id ? " 👑" : ""}</b><b>{r.total}</b></div>
              <div className="meter"><i style={{ width: `${Math.round((r.total / top) * 100)}%` }} /></div>
              <div className="score"><span>平均 {r.average ?? "—"}</span><span>{r.voters} 人投票</span><span>😋 {r.keen}</span><span>😕 {r.unhappy}</span><span>🤷 {r.any_ok}</span></div>
            </div>
          ))}
          <div className="tiny">只公布每間餐廳的統計，看不到個別的票。</div>
        </div>
      )}
    </div>
  );
}
