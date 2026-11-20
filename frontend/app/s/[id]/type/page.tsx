"use client";
// Dining type quiz ("飲食 MBTI"): 9 quick questions, 3 axes, 8 types. Fun + a shortcut to tick cuisines; it never changes the recommendation or any limit.
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Back, BottomBar, ErrorBox, Meter } from "@/components/ui";
import { useParticipant } from "@/hooks/useParticipant";
import { getAnswers, getDietMeta, putDietType } from "@/lib/api";
import type { DietMeta, DietType } from "@/lib/types";

export default function DietTypePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { participant, error: joinError } = useParticipant(id);
  const [meta, setMeta] = useState<DietMeta | null>(null);
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [result, setResult] = useState<DietType | null>(null);
  const [retaking, setRetaking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { getDietMeta().then(setMeta).catch((e) => setError(e.message)); }, []);
  useEffect(() => {
    if (!participant || !meta) return;
    getAnswers(participant.participant_id).then((a) => { const t = meta.types.find((x) => x.code === a.diet_type); if (t) setResult(t); }).catch(() => undefined);
  }, [participant, meta]);

  const total = meta?.questions.length ?? 9;
  const done = Object.keys(picked).length;

  async function submit() {
    if (!participant) return;
    setBusy(true); setError(null);
    try { setResult(await putDietType(participant.participant_id, picked)); setRetaking(false); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  }

  if (result && !retaking) {
    return (
      <div data-testid="type-result">
        <Back href={`/s/${id}`}>回到聚餐</Back>
        <div className="hero">
          <div className="muted">你的飲食類型</div>
          <h1 style={{ fontSize: "1.6rem" }}>{result.emoji} {result.name}</h1>
          <div>{result.summary}</div>
        </div>
        <div className="card">
          <h2>適合你的料理</h2>
          <div className="chips">{result.suggested_cuisines.map((c) => <span key={c} className="badge brand" style={{ height: 30, fontSize: ".88rem" }}>{c}</span>)}</div>
          <div className="tiny" style={{ marginTop: 8 }}>只是建議：不影響限制，也不會自動改變推薦。</div>
        </div>
        <BottomBar>
          <button className="narrow" onClick={() => { setPicked({}); setRetaking(true); }}>重測</button>
          <button className="primary" onClick={() => router.push(`/s/${id}/preferences?apply=type`)} data-testid="apply">用這些當我的偏好</button>
        </BottomBar>
        <Link className="btn small" style={{ width: "100%", marginTop: 8 }} href={`/s/${id}`}>先不用</Link>
      </div>
    );
  }

  return (
    <div>
      <Back href={`/s/${id}`}>回到聚餐</Back>
      <h1>你是哪一種吃貨？ 🍜</h1>
      <div className="muted">9 題，每題選比較像你的 · 約 1 分鐘</div>
      <Meter value={done} total={total} />
      <ErrorBox message={joinError || error} />
      {meta?.questions.map((q, i) => (
        <section className="card" key={q.id} data-testid={`quiz-${q.id}`}>
          <h2 style={{ fontSize: ".95rem" }}>{i + 1}. {q.text}</h2>
          <div className="stack">
            {q.options.map((o) => (
              <button key={o.value} type="button" aria-pressed={picked[q.id] === o.value} className={picked[q.id] === o.value ? "primary" : ""} style={{ justifyContent: "flex-start", textAlign: "left" }}
                onClick={() => setPicked((cur) => ({ ...cur, [q.id]: o.value }))}>{o.label}</button>
            ))}
          </div>
        </section>
      ))}
      <BottomBar>
        <button className="primary" disabled={busy || !participant || done < total} onClick={submit} data-testid="submit-quiz">{busy ? "計算中…" : done < total ? `已答 ${done}/${total}` : "看我的類型"}</button>
      </BottomBar>
    </div>
  );
}
