"use client";
// Screen 2 - hard constraints, one question per card. Every question needs an explicit answer ("none" is an answer), so "did I finish?" has a clear
// answer. Never shown to the other participants. Re-opening shows what you saved. Long explanations are folded into small "ⓘ" hints.
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Back, BottomBar, Chip, ErrorBox, Hint, PrivacyNote } from "@/components/ui";
import { useParticipant } from "@/hooks/useParticipant";
import { getAnswers, getAttributes, submitConstraints } from "@/lib/api";
import type { AttributeMeta } from "@/lib/types";

const ALLERGENS = ["peanut", "tree_nut", "shellfish", "milk", "egg", "sesame", "soy", "gluten"];
const INGREDIENTS = ["beef", "pork", "seafood", "offal", "raw_food"];
// religion / diet rules: the member's own reason decides how strictly the system treats it (religion = safety-type)
const RULES: { key: string; code: string; reason?: string; label: string }[] = [
  { key: "religion_beef", code: "beef", reason: "religion", label: "不吃牛（宗教）" },
  { key: "religion_pork", code: "pork", reason: "religion", label: "不吃豬（宗教）" },
  { key: "halal", code: "halal", label: "清真" },
  { key: "vegetarian", code: "vegetarian", reason: "belief_diet", label: "素食" },
  { key: "vegan", code: "vegan", reason: "belief_diet", label: "純素" },
  { key: "gluten_free", code: "gluten_free", label: "無麩質" },
];
const BUDGET_MIN = 100, BUDGET_MAX = 1500;

type Q = { sel: Set<string>; none: boolean };
const empty = (): Q => ({ sel: new Set(), none: false });
const answered = (q: Q) => q.none || q.sel.size > 0;

function Question({ title, q, setQ, options, hint, testid }: { title: string; q: Q; setQ: (q: Q) => void; options: { key: string; label: string; risk?: string }[]; hint?: string; testid: string }) {
  const toggle = (k: string) => { const sel = new Set(q.sel); sel.has(k) ? sel.delete(k) : sel.add(k); setQ({ sel, none: false }); };
  return (
    <section className="card" data-testid={testid}>
      <h2>{title} {answered(q) ? <span style={{ color: "var(--ok)" }}>✓</span> : <span className="tiny">請回答</span>}</h2>
      <div className="chips">
        <Chip on={q.none} onClick={() => setQ({ sel: new Set(), none: !q.none })}>沒有</Chip>
        {options.map((o) => <Chip key={o.key} on={q.sel.has(o.key)} risk={o.risk} onClick={() => toggle(o.key)}>{o.label}</Chip>)}
      </div>
      {hint && <Hint>{hint}</Hint>}
    </section>
  );
}

export default function ConstraintsPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { participant, error: joinError } = useParticipant(id);
  const [meta, setMeta] = useState<AttributeMeta | null>(null);
  const [allergy, setAllergy] = useState<Q>(empty());
  const [ingredient, setIngredient] = useState<Q>(empty());
  const [diet, setDiet] = useState<Q>(empty());
  const [strict, setStrict] = useState(false);
  const [budgetOn, setBudgetOn] = useState(false);
  const [budget, setBudget] = useState(400);
  const [wasSubmitted, setWasSubmitted] = useState(false);
  const [prefsDone, setPrefsDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { getAttributes().then(setMeta).catch((e) => setError(e.message)); }, []);

  // re-opening: show what was saved so it can be edited
  useEffect(() => {
    if (!participant) return;
    getAnswers(participant.participant_id).then((a) => {
      setPrefsDone(a.preferences_submitted);
      if (!a.constraints_submitted) return;
      setWasSubmitted(true);
      const al = new Set<string>(), ing = new Set<string>(), dt = new Set<string>();
      for (const c of a.constraints) {
        if (c.reason === "religion" && (c.attribute_code === "beef" || c.attribute_code === "pork")) dt.add(`religion_${c.attribute_code}`);
        else if (ALLERGENS.includes(c.attribute_code)) al.add(c.attribute_code);
        else if (INGREDIENTS.includes(c.attribute_code)) ing.add(c.attribute_code);
        else { const r = RULES.find((x) => x.code === c.attribute_code); if (r) dt.add(r.key); }
      }
      setAllergy({ sel: al, none: al.size === 0 }); setIngredient({ sel: ing, none: ing.size === 0 }); setDiet({ sel: dt, none: dt.size === 0 });
      setStrict(a.strict_allergy);
      if (a.budget_max_per_person) { setBudgetOn(true); setBudget(Math.min(Math.max(a.budget_max_per_person, BUDGET_MIN), BUDGET_MAX)); }
    }).catch(() => undefined);
  }, [participant]);

  const label = (code: string) => meta?.groups.flatMap((g) => g.items).find((i) => i.attribute_code === code)?.label ?? code;
  const ready = answered(allergy) && answered(ingredient) && answered(diet);
  const left = [allergy, ingredient, diet].filter((q) => !answered(q)).length;

  async function save() {
    if (!participant || !ready) return;
    setBusy(true); setError(null);
    try {
      const items = new Map<string, { attribute_code: string; reason?: string }>();
      for (const c of ingredient.sel) items.set(c, { attribute_code: c });
      for (const c of allergy.sel) items.set(c, { attribute_code: c, reason: "allergy" });
      for (const k of diet.sel) { const r = RULES.find((x) => x.key === k)!; items.set(r.code, { attribute_code: r.code, reason: r.reason }); }   // a religious reason wins over "just don't like it"
      await submitConstraints(participant.participant_id, [...items.values()], strict && allergy.sel.size > 0, budgetOn ? budget : null);
      router.push(prefsDone ? `/s/${id}` : `/s/${id}/preferences`);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); setBusy(false); }
  }

  return (
    <div>
      <Back href={`/s/${id}`}>回到聚餐</Back>
      <h1>先告訴我們你的底線 🛡</h1>
      <div style={{ margin: "4px 0 8px" }}><PrivacyNote text="只有你看得到" /></div>
      <ErrorBox message={joinError || error} />

      <Question testid="q-allergy" title="是否有以下過敏原？" q={allergy} setQ={setAllergy} options={ALLERGENS.map((c) => ({ key: c, label: label(c), risk: "critical" }))}
        hint="目前只能比對這 8 類。其他過敏原（例如魚類、水果）請入座前直接問店家。" />
      {allergy.sel.size > 0 && (
        <label className="card" style={{ display: "flex", gap: 10, alignItems: "center", fontWeight: 400, margin: "12px 0" }} data-testid="strict-option">
          <input type="checkbox" checked={strict} onChange={(e) => setStrict(e.target.checked)} />
          <span style={{ flex: 1 }}><b>嚴格過敏模式</b><span className="tiny" style={{ display: "block" }}>只推薦店家已確認不含的餐廳，可能沒有結果</span></span>
        </label>
      )}

      <Question testid="q-ingredient" title="有絕對不吃的食材嗎？" q={ingredient} setQ={setIngredient} options={INGREDIENTS.map((c) => ({ key: c, label: label(c) }))} />
      <Question testid="q-diet" title="有宗教或飲食規範嗎？" q={diet} setQ={setDiet} options={RULES.map((r) => ({ key: r.key, label: r.label }))} hint="信仰上的禁忌會被視為更嚴格的限制（連共用鍋具都在意）。" />

      <section className="card" data-testid="budget">
        <h2>每人預算 <span className="tiny">選填</span></h2>
        <div className="chips">
          <Chip on={!budgetOn} onClick={() => setBudgetOn(false)}>不設定</Chip>
          <Chip on={budgetOn} onClick={() => setBudgetOn(true)}>設定上限</Chip>
        </div>
        {budgetOn && (
          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: "1.3rem", fontWeight: 800 }} data-testid="budget-value">{budget >= BUDGET_MAX ? `${BUDGET_MAX} 以上` : `$${budget}`} <span className="muted">/ 人</span></div>
            <input type="range" min={BUDGET_MIN} max={BUDGET_MAX} step={50} value={budget} aria-label="每人預算上限" onChange={(e) => setBudget(Number(e.target.value))} />
          </div>
        )}
        <Hint>參考用：不會排除任何餐廳，目前也沒有價格資料可比對。</Hint>
      </section>

      <p className="disclaimer">資料不足會明確標「資訊不足」，不代表安全；過敏請務必再向店家確認。</p>
      <BottomBar>
        <button className="narrow" onClick={() => { setAllergy(empty()); setIngredient(empty()); setDiet(empty()); setStrict(false); setBudgetOn(false); }} disabled={busy}>重填</button>
        <button className="primary" onClick={save} disabled={busy || !participant || !ready} data-testid="save">
          {busy ? "儲存中…" : !ready ? `還有 ${left} 題` : wasSubmitted ? "更新" : "下一步：選料理 →"}
        </button>
      </BottomBar>
    </div>
  );
}
