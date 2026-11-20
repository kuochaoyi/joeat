"use client";
// 畫面 3：我的限制 — 每題獨立卡片，必須明確作答（「沒有」也是一種回答），重填有防呆確認
import { Check, CheckCircle2, RotateCcw, ShieldAlert, ShieldCheck, Wallet } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import {
  Back,
  BottomBar,
  Chip,
  ErrorBox,
  GameButton,
  Hint,
  JourneyHeader,
  PrivacyNote,
} from "@/components/ui";
import { useParticipant } from "@/hooks/useParticipant";
import { getAnswers, getAttributes, submitConstraints } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { AttributeMeta } from "@/lib/types";

const ALLERGENS = ["peanut", "tree_nut", "shellfish", "milk", "egg", "sesame", "soy", "gluten"];
const INGREDIENTS = ["beef", "pork", "seafood", "offal", "raw_food"];
// 載入中預設中文對照，避免 API 回傳前短暫閃過英文鍵名
const FALLBACK_LABEL: Record<string, string> = {
  peanut: "花生",
  tree_nut: "堅果",
  shellfish: "甲殼類",
  milk: "奶類",
  egg: "蛋",
  sesame: "芝麻",
  soy: "大豆",
  gluten: "麩質",
  beef: "牛肉",
  pork: "豬肉",
  seafood: "海鮮",
  offal: "內臟",
  raw_food: "生食",
};
const RULES: { key: string; code: string; reason?: string; label: string }[] = [
  { key: "religion_beef", code: "beef", reason: "religion", label: "不吃牛（宗教）" },
  { key: "religion_pork", code: "pork", reason: "religion", label: "不吃豬（宗教）" },
  { key: "halal", code: "halal", label: "清真" },
  { key: "vegetarian", code: "vegetarian", reason: "belief_diet", label: "素食" },
  { key: "vegan", code: "vegan", reason: "belief_diet", label: "純素" },
  { key: "gluten_free", code: "gluten_free", label: "無麩質" },
];
const BUDGET_MIN = 100;
const BUDGET_MAX = 1500;

type Q = { sel: Set<string>; none: boolean };
const empty = (): Q => ({ sel: new Set(), none: false });
const answered = (q: Q) => q.none || q.sel.size > 0;

function Question({
  step,
  title,
  q,
  setQ,
  options,
  hint,
  testid,
}: {
  step: number;
  title: string;
  q: Q;
  setQ: (q: Q) => void;
  options: { key: string; label: string; risk?: string }[];
  hint?: string;
  testid: string;
}) {
  const isDone = answered(q);
  const toggle = (k: string) => {
    const sel = new Set(q.sel);
    sel.has(k) ? sel.delete(k) : sel.add(k);
    setQ({ sel, none: false });
  };

  return (
    <section
      data-testid={testid}
      className={cn(
        "rounded-3xl border-2 bg-surface p-4 shadow-card transition-colors",
        isDone ? "border-ok/40" : "border-line"
      )}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="m-0 flex items-center gap-2 text-base font-black text-ink">
          <span
            className={cn(
              "flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-xs font-black",
              isDone ? "bg-ok-soft text-ok" : "bg-brand-soft text-brand"
            )}
          >
            {step}
          </span>
          {title}
        </h2>
        {isDone ? (
          <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-ok-soft px-2.5 py-0.5 text-xs font-extrabold text-ok animate-badge-bounce">
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
            已答
          </span>
        ) : (
          <span className="shrink-0 rounded-full bg-brand-soft px-2.5 py-0.5 text-xs font-extrabold text-brand">
            請回答
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <Chip on={q.none} onClick={() => setQ({ sel: new Set(), none: !q.none })}>
          沒有
        </Chip>
        {options.map((o) => (
          <Chip key={o.key} on={q.sel.has(o.key)} risk={o.risk} onClick={() => toggle(o.key)}>
            {o.label}
          </Chip>
        ))}
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
  const [confirmReset, setConfirmReset] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getAttributes().then(setMeta).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!participant) return;
    getAnswers(participant.participant_id)
      .then((a) => {
        setPrefsDone(a.preferences_submitted);
        if (!a.constraints_submitted) return;
        setWasSubmitted(true);
        const al = new Set<string>();
        const ing = new Set<string>();
        const dt = new Set<string>();
        for (const c of a.constraints) {
          if (c.reason === "religion" && (c.attribute_code === "beef" || c.attribute_code === "pork")) {
            dt.add(`religion_${c.attribute_code}`);
          } else if (ALLERGENS.includes(c.attribute_code)) {
            al.add(c.attribute_code);
          } else if (INGREDIENTS.includes(c.attribute_code)) {
            ing.add(c.attribute_code);
          } else {
            const r = RULES.find((x) => x.code === c.attribute_code);
            if (r) dt.add(r.key);
          }
        }
        setAllergy({ sel: al, none: al.size === 0 });
        setIngredient({ sel: ing, none: ing.size === 0 });
        setDiet({ sel: dt, none: dt.size === 0 });
        setStrict(a.strict_allergy);
        if (a.budget_max_per_person) {
          setBudgetOn(true);
          setBudget(Math.min(Math.max(a.budget_max_per_person, BUDGET_MIN), BUDGET_MAX));
        }
      })
      .catch(() => undefined);
  }, [participant]);

  const label = (code: string) =>
    meta?.groups.flatMap((g) => g.items).find((i) => i.attribute_code === code)?.label ?? FALLBACK_LABEL[code] ?? code;
  const doneCount = [allergy, ingredient, diet].filter(answered).length;
  const ready = doneCount === 3;
  const left = 3 - doneCount;

  async function save() {
    if (!participant || !ready) return;
    setBusy(true);
    setError(null);
    try {
      const items = new Map<string, { attribute_code: string; reason?: string }>();
      for (const c of ingredient.sel) items.set(c, { attribute_code: c });
      for (const c of allergy.sel) items.set(c, { attribute_code: c, reason: "allergy" });
      for (const k of diet.sel) {
        const r = RULES.find((x) => x.key === k)!;
        items.set(r.code, { attribute_code: r.code, reason: r.reason });
      }
      await submitConstraints(
        participant.participant_id,
        [...items.values()],
        strict && allergy.sel.size > 0,
        budgetOn ? budget : null
      );
      router.push(prefsDone ? `/s/${id}` : `/s/${id}/preferences`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3.5">
      <Back href={`/s/${id}`}>回到聚餐</Back>
      <JourneyHeader current="constraints" />

      <header className="flex items-start justify-between gap-2">
        <div>
          <h1 className="m-0 flex items-center gap-2 text-2xl font-black text-ink">
            <ShieldCheck className="h-6 w-6 text-brand" aria-hidden="true" />
            先告訴我們你的底線
          </h1>
          <div className="mt-1.5">
            <PrivacyNote text="只有你看得到，不會公開給朋友" />
          </div>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full px-3 py-1 text-xs font-black",
            ready ? "bg-ok-soft text-ok" : "bg-brand-soft text-brand"
          )}
        >
          {doneCount} / 3 題
        </span>
      </header>

      <ErrorBox message={joinError || error} />

      <Question
        step={1}
        testid="q-allergy"
        title="是否有以下過敏原？"
        q={allergy}
        setQ={setAllergy}
        options={ALLERGENS.map((c) => ({ key: c, label: label(c), risk: "critical" }))}
        hint="目前只能比對這 8 類。其他過敏原（例如魚類、水果）請入座前直接問店家。"
      />

      {allergy.sel.size > 0 && (
        <label
          data-testid="strict-option"
          className="flex cursor-pointer items-start gap-3 rounded-3xl border-2 border-crit/40 bg-crit-soft/60 p-4 shadow-sm animate-pop-in"
        >
          <input
            type="checkbox"
            checked={strict}
            onChange={(e) => setStrict(e.target.checked)}
            className="sr-only"
          />
          <span
            aria-hidden="true"
            className={cn(
              "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border-2 transition-all",
              strict ? "border-crit bg-crit text-white" : "border-crit/50 bg-surface text-transparent"
            )}
          >
            <Check className="h-4 w-4 stroke-[3]" />
          </span>
          <span className="flex-1">
            <span className="flex items-center gap-1.5 text-sm font-black text-crit">
              <ShieldAlert className="h-4 w-4" aria-hidden="true" />
              嚴格過敏模式
            </span>
            <span className="mt-0.5 block text-xs font-medium text-ink/80">
              只推薦店家已確認不含的餐廳，目前可能沒有結果
            </span>
          </span>
        </label>
      )}

      <Question
        step={2}
        testid="q-ingredient"
        title="有絕對不吃的食材嗎？"
        q={ingredient}
        setQ={setIngredient}
        options={INGREDIENTS.map((c) => ({ key: c, label: label(c) }))}
      />

      <Question
        step={3}
        testid="q-diet"
        title="有宗教或飲食規範嗎？"
        q={diet}
        setQ={setDiet}
        options={RULES.map((r) => ({ key: r.key, label: r.label }))}
        hint="信仰上的禁忌會被視為更嚴格的限制（連共用鍋具都在意）。"
      />

      {/* 每人預算（選填軟條件） */}
      <section className="rounded-3xl border-2 border-line bg-surface p-4 shadow-card" data-testid="budget">
        <div className="mb-2.5 flex items-center justify-between">
          <h2 className="m-0 flex items-center gap-1.5 text-base font-black text-ink">
            <Wallet className="h-4 w-4 text-brand" aria-hidden="true" />
            每人預算
          </h2>
          <span className="rounded-full bg-chip px-2.5 py-0.5 text-xs font-bold text-muted">選填</span>
        </div>
        <div className="flex gap-2">
          <Chip on={!budgetOn} onClick={() => setBudgetOn(false)}>不設定</Chip>
          <Chip on={budgetOn} onClick={() => setBudgetOn(true)}>設定上限</Chip>
        </div>
        {budgetOn && (
          <div className="mt-3.5 rounded-2xl bg-chip/70 p-3.5 animate-pop-in">
            <div className="mb-2 flex items-baseline justify-between">
              <span className="text-xs font-bold text-muted">期望上限</span>
              <div className="text-2xl font-black text-brand" data-testid="budget-value">
                {budget >= BUDGET_MAX ? `${BUDGET_MAX} 以上` : `$${budget}`}
                <span className="ml-1 text-xs font-semibold text-muted">/ 人</span>
              </div>
            </div>
            <input
              type="range"
              className="game-slider"
              min={BUDGET_MIN}
              max={BUDGET_MAX}
              step={50}
              value={budget}
              aria-label="每人預算上限"
              onChange={(e) => setBudget(Number(e.target.value))}
            />
            <div className="mt-1.5 flex justify-between text-[0.7rem] font-bold text-muted">
              <span>$100</span>
              <span>$500</span>
              <span>$1000</span>
              <span>$1500+</span>
            </div>
          </div>
        )}
        <Hint>參考用：不會排除任何餐廳，目前也沒有價格資料可比對。</Hint>
      </section>

      {/* 安全免責聲明（常駐不收合） */}
      <p className="px-1 text-xs leading-relaxed text-muted">
        資料不足會明確標「資訊不足」，不代表安全；過敏請務必再向店家確認。
      </p>

      <BottomBar>
        <GameButton
          type="button"
          variant="secondary"
          disabled={busy}
          onClick={() => setConfirmReset(true)}
          aria-label="重填限制"
        >
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          重填
        </GameButton>
        <GameButton
          type="button"
          variant="primary"
          className="flex-1"
          onClick={save}
          disabled={busy || !participant || !ready}
          data-testid="save"
        >
          {busy ? "儲存中…" : !ready ? `還有 ${left} 題沒答` : wasSubmitted ? "更新我的底線" : "下一步：選料理 →"}
        </GameButton>
      </BottomBar>

      <ConfirmDialog
        open={confirmReset}
        title="確定要重填嗎？"
        description="這會清空你剛剛勾選的過敏原、不吃食材、宗教規範與預算設定喔。"
        confirmLabel="全部清空"
        cancelLabel="保留現狀"
        destructive
        onConfirm={() => {
          setAllergy(empty());
          setIngredient(empty());
          setDiet(empty());
          setStrict(false);
          setBudgetOn(false);
          setConfirmReset(false);
        }}
        onCancel={() => setConfirmReset(false)}
      />
    </div>
  );
}
