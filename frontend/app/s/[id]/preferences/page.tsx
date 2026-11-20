"use client";
// Screen 3 - soft preferences: tap the cuisines you want. Not tapped = anything is fine. Re-opening shows your taps.
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Back, BottomBar, ErrorBox } from "@/components/ui";
import { useParticipant } from "@/hooks/useParticipant";
import { getAnswers, getCuisines, getDietMeta, submitPreferences } from "@/lib/api";
import type { CuisineMeta } from "@/lib/types";

// emoji + two or three example dishes, purely decorative (the tag itself is what is saved)
const LOOK: Record<string, [string, string]> = {
  台式: ["🥢", "家常 · 便當"], 中式: ["🥟", "合菜 · 麵點"], 日式: ["🍣", "壽司 · 拉麵"], 韓式: ["🥘", "炸雞 · 鍋物"], 火鍋: ["🍲", "麻辣 · 涮涮"], 燒肉: ["🥩", "炭火 · 居酒屋"],
  熱炒: ["🍳", "熱鬧 · 小酌"], 小吃: ["🍜", "麵 · 米粉"], 義式: ["🍝", "披薩 · 義大利麵"], 歐式: ["🥐", "早午餐 · 輕食"], 美式: ["🍔", "漢堡 · 排餐"],
  東南亞: ["🍛", "泰式 · 越式"], 印度料理: ["🍛", "咖哩 · 烤餅"], 甜點: ["🍰", "蛋糕 · 冰品"], 咖啡廳: ["☕", "咖啡 · 輕食"],
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

  useEffect(() => { getCuisines().then(setMeta).catch((e) => setError(e.message)); }, []);
  useEffect(() => {
    if (!participant) return;
    const apply = new URLSearchParams(window.location.search).get("apply") === "type";          // coming from the quiz result: use the suggestions
    getAnswers(participant.participant_id).then(async (a) => {
      if (a.preferences_submitted) {
        setWasSubmitted(true);
        setPicked(new Set(a.preferences.filter((p) => p.stance === "love" || p.stance === "ok").map((p) => p.cuisine_tag)));
      }
      if (a.diet_type && (apply || !a.preferences_submitted)) {                                // never silently overwrite saved preferences
        const t = (await getDietMeta()).types.find((x) => x.code === a.diet_type);
        if (t) { setPicked(new Set(t.suggested_cuisines)); setFromType(`${t.emoji} ${t.name}`); }
      }
    }).catch(() => undefined);
  }, [participant]);

  const toggle = (tag: string) => setPicked((s) => { const n = new Set(s); n.has(tag) ? n.delete(tag) : n.add(tag); return n; });

  async function save() {
    if (!participant) return;
    setBusy(true); setError(null);
    try {
      await submitPreferences(participant.participant_id, [...picked].map((cuisine_tag) => ({ cuisine_tag, stance: "love" as const })));
      router.push(`/s/${id}`);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); setBusy(false); }
  }

  return (
    <div>
      <Back href={`/s/${id}`}>回到聚餐</Back>
      <h1>今天想吃什麼？ 🍜</h1>
      <div className="muted">點選想吃的，沒點的都可以</div>
      <ErrorBox message={joinError || error} />
      {fromType && <div className="status brand" data-testid="type-note" style={{ background: "var(--brand-soft)", color: "var(--brand)" }}>已依「{fromType}」預選，可自己改</div>}
      <div className="grid2" style={{ margin: "12px 0" }} data-testid="cuisines">
        {meta?.chips.map((c) => {
          const [e, sub] = LOOK[c.tag] ?? ["🍽", ""];
          return (
            <button key={c.tag} type="button" className={`pick${picked.has(c.tag) ? " on" : ""}`} aria-pressed={picked.has(c.tag)} onClick={() => toggle(c.tag)}>
              <span className="e" aria-hidden="true">{e}</span><span>{c.label}{sub && <small>{sub}</small>}</span>
            </button>
          );
        })}
      </div>
      <BottomBar>
        <button className="narrow" onClick={() => setPicked(new Set())} disabled={busy}>清除</button>
        <button className="primary" onClick={save} disabled={busy || !participant} data-testid="save">
          {busy ? "儲存中…" : picked.size === 0 ? "我都好，完成" : `完成（已選 ${picked.size}）`}
        </button>
      </BottomBar>
    </div>
  );
}
