"use client";
// Time poll: tick every time you can make. Everyone sees only how many people ticked each slot; the host may close early.
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Back, BottomBar, ErrorBox, Meter } from "@/components/ui";
import { useParticipant } from "@/hooks/useParticipant";
import { closeTimePoll, getTimePoll, putTimeVotes } from "@/lib/api";
import type { TimePoll } from "@/lib/types";

const day = (iso: string) => new Date(iso).toLocaleDateString("zh-TW", { month: "numeric", day: "numeric", weekday: "short" });
const hm = (iso: string) => new Date(iso).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false });
const full = (iso: string) => new Date(iso).toLocaleString("zh-TW", { month: "numeric", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false });

export default function TimePollPage() {
  const { id } = useParams<{ id: string }>();
  const { participant, error: joinError } = useParticipant(id);
  const [poll, setPoll] = useState<TimePoll | null>(null);
  const [mine, setMine] = useState<Set<number>>(new Set());
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const p = await getTimePoll(id, participant?.participant_id);
      setPoll(p);
      if (!dirty) setMine(new Set(p.options.filter((o) => o.mine).map((o) => o.option_id)));
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }, [id, participant, dirty]);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);

  const toggle = (oid: number) => { setDirty(true); setSaved(false); setMine((s) => { const n = new Set(s); n.has(oid) ? n.delete(oid) : n.add(oid); return n; }); };

  async function save() {
    if (!participant) return;
    setBusy(true); setError(null);
    try { setPoll(await putTimeVotes(participant.participant_id, [...mine])); setDirty(false); setSaved(true); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  }
  async function closeNow() {
    if (!participant) return;
    setBusy(true); setError(null);
    try { setPoll(await closeTimePoll(id, participant.participant_id)); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  }

  const days = poll ? [...new Set(poll.options.map((o) => day(o.starts_at)))] : [];
  const top = poll ? Math.max(0, ...poll.options.map((o) => o.count)) : 0;
  return (
    <div>
      <Back href={`/s/${id}`}>回到聚餐</Back>
      <h1>什麼時候可以？ 🕒</h1>
      <ErrorBox message={joinError || error} />
      {poll && (
        <>
          {poll.closed ? (
            <div className="hero" data-testid="poll-result">
              {poll.meal_time ? <><div className="muted">就這個時間</div><h1>{full(poll.meal_time)}</h1></> : <div>投票結束，但沒有人勾選時間。</div>}
            </div>
          ) : (
            <>
              <div className="muted">勾選所有你可以的時段{poll.deadline ? ` · ${full(poll.deadline)} 截止` : ""}</div>
              <Meter value={poll.responded} total={poll.party_size ?? poll.joined} />
              <div className="tiny">已有 {poll.responded} / {poll.party_size ?? poll.joined} 人回答 · 只顯示人數，看不到是誰</div>
            </>
          )}
          {days.map((d) => (
            <div key={d} className="card">
              <h2>{d}</h2>
              <div className="stack">
                {poll.options.filter((o) => day(o.starts_at) === d).map((o) => (
                  <label key={o.option_id} style={{ display: "flex", gap: 12, alignItems: "center", margin: 0, fontWeight: o.option_id === poll.chosen_option_id ? 800 : 500 }}>
                    <input type="checkbox" checked={mine.has(o.option_id)} disabled={poll.closed} onChange={() => toggle(o.option_id)} aria-label={`${d} ${hm(o.starts_at)}`} />
                    <span style={{ flex: 1 }}>{hm(o.starts_at)}{o.option_id === poll.chosen_option_id ? " ✅" : ""}</span>
                    <span className={`badge ${o.count === top && top > 0 ? "ok" : "normal"}`}>{o.count} 人</span>
                  </label>
                ))}
              </div>
            </div>
          ))}
          {!poll.closed && participant && <button className="link" style={{ width: "100%" }} onClick={closeNow} disabled={busy} data-testid="close-poll">結束投票並決定時間（主揪）</button>}
          {!poll.closed && (
            <BottomBar>
              <button className="primary" onClick={save} disabled={busy || !participant || !dirty} data-testid="save-time">{busy ? "儲存中…" : saved ? "已儲存 ✓" : dirty ? "儲存我的時間" : "勾選後儲存"}</button>
            </BottomBar>
          )}
        </>
      )}
    </div>
  );
}
