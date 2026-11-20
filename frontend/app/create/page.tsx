"use client";
// 畫面 1：建立聚餐 — 分區遊戲化任務卡，30 秒開團
import {
  AlertTriangle,
  ArrowLeft,
  CalendarClock,
  Crosshair,
  Map as MapIcon,
  MapPin,
  Minus,
  Plus,
  Sparkles,
  Users,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Dispatch, FormEvent, SetStateAction, useEffect, useMemo, useState } from "react";

import { BottomBar, Chip, ErrorBox, GameButton, Hint, Logo, Seg } from "@/components/ui";
import { createSession, getLocations } from "@/lib/api";
import { cn } from "@/lib/cn";
import { COVERAGE, distanceM } from "@/lib/geo";
import { getIdentity } from "@/lib/liff";
import type { LocationPreset } from "@/lib/types";

const MapPicker = dynamic(() => import("@/components/MapPicker"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[280px] items-center justify-center rounded-2xl border-2 border-line bg-chip text-sm font-semibold text-muted">
      地圖載入中…
    </div>
  ),
});

const PERIODS = [
  ["12:00", "☀️ 午餐"],
  ["15:00", "🧁 下午茶"],
  ["18:30", "🌙 晚餐"],
  ["21:00", "🍢 宵夜"],
] as const;

const DEADLINES = [
  [6, "6 小時"],
  [12, "12 小時"],
  [24, "1 天"],
  [48, "2 天"],
  [72, "3 天"],
] as const;

const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const toggle = (setter: Dispatch<SetStateAction<Set<string>>>, v: string) =>
  setter((cur) => {
    const n = new Set(cur);
    n.has(v) ? n.delete(v) : n.add(v);
    return n;
  });

export default function CreateSessionPage() {
  const router = useRouter();
  const [locations, setLocations] = useState<LocationPreset[]>([]);
  const [title, setTitle] = useState("");
  const [mode, setMode] = useState<"fixed" | "poll">("fixed");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("18:30");
  const [days, setDays] = useState<Set<string>>(new Set());
  const [periods, setPeriods] = useState<Set<string>>(new Set(["18:30"]));
  const [deadline, setDeadline] = useState(24);
  const [location, setLocation] = useState("yancheng_pu");
  const [pin, setPin] = useState<{ lat: number; lon: number } | null>(null);
  const [pinLabel, setPinLabel] = useState("");
  const [showMap, setShowMap] = useState(false);
  const [size, setSize] = useState(3);
  const [pets, setPets] = useState(false);
  const [kids, setKids] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const next14 = useMemo(
    () =>
      Array.from({ length: 14 }, (_, i) => {
        const d = new Date(Date.now() + (i + 1) * 86400000);
        const wd = d.getDay();
        return {
          iso: iso(d),
          md: `${d.getMonth() + 1}/${d.getDate()}`,
          wd: `週${"日一二三四五六"[wd]}`,
          weekend: wd === 0 || wd === 6,
        };
      }),
    []
  );

  useEffect(() => {
    getLocations()
      .then((r) => setLocations(r.locations))
      .catch((e) => setError(e.message));
    setDate(iso(new Date(Date.now() + 3 * 86400000)));
  }, []);

  const slots = [...days]
    .sort()
    .flatMap((d) => [...periods].sort().map((p) => `${d}T${p}:00+08:00`));
  const far = pin ? distanceM(pin.lat, pin.lon, COVERAGE.lat, COVERAGE.lon) > COVERAGE.radiusM : false;

  function useMyLocation() {
    setError(null);
    if (!navigator.geolocation) {
      setError("這個瀏覽器不支援定位，請在地圖上點選。");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setPin({ lat: p.coords.latitude, lon: p.coords.longitude });
        setPinLabel((l) => l || "我的位置");
        setShowMap(true);
      },
      () => setError("無法取得位置，請在地圖上點選。"),
      { timeout: 8000 }
    );
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (mode === "poll" && slots.length < 2) {
      setError("請至少選 2 個時段（日期 × 時段）。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const me = await getIdentity();
      const place = pin
        ? { meeting_lat: pin.lat, meeting_lon: pin.lon, location_label: pinLabel.trim() || "地圖選點" }
        : { location_preset: location };
      const s = await createSession({
        title: title.trim(),
        party_size: size,
        line_group_id: me.groupId,
        host_line_user_id: me.userId,
        host_id_token: me.idToken,
        ...place,
        needs_pets: pets,
        needs_kids: kids,
        ...(mode === "fixed"
          ? { date, time }
          : { time_mode: "poll" as const, time_slots: slots, time_deadline_hours: deadline }),
      });
      router.push(`/s/${s.session_id}/constraints`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3.5">
      {/* 返回作業首頁連結 */}
      <nav aria-label="返回導覽">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 text-xs font-bold text-muted no-underline transition hover:border-brand hover:text-brand"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          返回作業首頁
        </Link>
      </nav>

      {/* 品牌活力歡迎頂欄 */}
      <header className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-2 to-brand p-5 text-white shadow-hero">
        <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-white/15 blur-xl" />
        <div className="relative flex items-center gap-3.5">
          <div className="rounded-2xl bg-white/20 p-1 backdrop-blur-sm">
            <Logo size={48} />
          </div>
          <div>
            <div className="inline-flex items-center gap-1 rounded-full bg-white/20 px-2.5 py-0.5 text-[0.72rem] font-extrabold tracking-wide">
              <Sparkles className="h-3 w-3" aria-hidden="true" />
              高雄鹽埕聚餐神器
            </div>
            <h1 className="m-0 mt-1 text-2xl font-black tracking-tight">揪呷 JOEAT</h1>
            <p className="m-0 text-xs font-medium text-white/90">2–20 人聚餐，30 秒收集底線與口味！</p>
          </div>
        </div>
      </header>

      {/* 卡片 1：聚餐名稱與人數 */}
      <section className="rounded-3xl border-2 border-line bg-surface p-4 shadow-card">
        <label htmlFor="title" className="mb-1.5 flex items-center gap-1.5 text-sm font-extrabold text-ink">
          <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-brand-soft text-xs font-black text-brand">1</span>
          這次要揪什麼局？
        </label>
        <input
          id="title"
          required
          maxLength={80}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="例如：高中同學聚餐、系辦慶功宴"
          className="h-12 w-full rounded-2xl border-2 border-line bg-bg px-3.5 text-base font-semibold text-ink transition focus:border-brand focus:bg-surface focus:outline-none"
        />

        <div className="mt-4">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-sm font-extrabold text-ink">
              <Users className="h-4 w-4 text-brand" aria-hidden="true" />
              預計人數
            </span>
            <span className="text-xs font-semibold text-muted">2–20 人</span>
          </div>
          <div id="size" className="flex items-center justify-between rounded-2xl border-2 border-line bg-bg p-1.5">
            <button
              type="button"
              aria-label="減少一人"
              disabled={size <= 2}
              onClick={() => setSize((n) => Math.max(2, n - 1))}
              className="flex h-11 w-12 items-center justify-center rounded-xl border-2 border-line bg-surface text-ink transition hover:border-brand disabled:opacity-40 cursor-pointer active:scale-95"
            >
              <Minus className="h-5 w-5 stroke-[2.5]" />
            </button>
            <div className="text-center">
              <b data-testid="size" className="text-xl font-black text-brand">{size} 人</b>
              <div className="mt-0.5 flex justify-center gap-1" aria-hidden="true">
                {Array.from({ length: Math.min(size, 10) }).map((_, i) => (
                  <span key={i} className="h-1.5 w-1.5 rounded-full bg-brand/70" />
                ))}
                {size > 10 && <span className="text-[0.6rem] font-bold leading-none text-brand">+</span>}
              </div>
            </div>
            <button
              type="button"
              aria-label="增加一人"
              disabled={size >= 20}
              onClick={() => setSize((n) => Math.min(20, n + 1))}
              className="flex h-11 w-12 items-center justify-center rounded-xl border-2 border-line bg-surface text-ink transition hover:border-brand disabled:opacity-40 cursor-pointer active:scale-95"
            >
              <Plus className="h-5 w-5 stroke-[2.5]" />
            </button>
          </div>
        </div>
      </section>

      {/* 卡片 2：時間設定 */}
      <section className="rounded-3xl border-2 border-line bg-surface p-4 shadow-card">
        <div className="mb-2 flex items-center gap-1.5 text-sm font-extrabold text-ink">
          <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-brand-soft text-xs font-black text-brand">2</span>
          <CalendarClock className="h-4 w-4 text-brand" aria-hidden="true" />
          聚餐時間
        </div>
        <Seg
          label="時間怎麼決定"
          value={mode}
          onChange={setMode}
          options={[
            ["fixed", "我來決定"],
            ["poll", "大家投票"],
          ]}
        />
        {mode === "fixed" ? (
          <div className="mt-3 grid grid-cols-2 gap-2.5">
            <input
              id="date"
              aria-label="日期"
              type="date"
              required
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="h-12 w-full rounded-2xl border-2 border-line bg-bg px-3 text-sm font-bold text-ink focus:border-brand focus:bg-surface focus:outline-none"
            />
            <input
              id="time"
              aria-label="時間"
              type="time"
              required
              value={time}
              onChange={(e) => setTime(e.target.value)}
              className="h-12 w-full rounded-2xl border-2 border-line bg-bg px-3 text-sm font-bold text-ink focus:border-brand focus:bg-surface focus:outline-none"
            />
          </div>
        ) : (
          <div data-testid="poll-setup" className="mt-3 space-y-3 animate-pop-in">
            <div>
              <div className="mb-1.5 text-xs font-bold text-muted">勾選可能的日期（未來 14 天）</div>
              <div className="grid grid-cols-4 gap-1.5 sm:grid-cols-5">
                {next14.map((d) => {
                  const on = days.has(d.iso);
                  return (
                    <button
                      key={d.iso}
                      type="button"
                      aria-pressed={on}
                      onClick={() => toggle(setDays, d.iso)}
                      className={cn(
                        "flex flex-col items-center justify-center rounded-xl border-2 py-2 text-center transition cursor-pointer active:scale-95",
                        on
                          ? "border-brand bg-brand-soft text-brand shadow-sm"
                          : "border-line bg-bg text-ink hover:border-brand/40"
                      )}
                    >
                      <span className="text-xs font-extrabold">{d.md}</span>
                      <span className={cn("text-[0.68rem] font-semibold", on ? "text-brand" : d.weekend ? "text-crit" : "text-muted")}>
                        {d.wd}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
            <div>
              <div className="mb-1.5 text-xs font-bold text-muted">勾選時段</div>
              <div className="flex flex-wrap gap-2">
                {PERIODS.map(([v, l]) => (
                  <Chip key={v} on={periods.has(v)} onClick={() => toggle(setPeriods, v)}>
                    {l}
                  </Chip>
                ))}
              </div>
            </div>
            <div className="flex items-center justify-between gap-2 rounded-2xl bg-chip px-3 py-2">
              <span className="text-xs font-bold text-ink" data-testid="slot-count">
                共 <b className="text-brand">{slots.length}</b> 個時段
                {slots.length < 2 && <span className="text-crit">（至少 2 個）</span>}
              </span>
              <select
                id="deadline"
                aria-label="投票截止"
                value={deadline}
                onChange={(e) => setDeadline(Number(e.target.value))}
                className="h-9 rounded-xl border-2 border-line bg-surface px-2.5 text-xs font-bold text-ink"
              >
                {DEADLINES.map(([h, l]) => (
                  <option key={h} value={h}>{l}後截止</option>
                ))}
              </select>
            </div>
          </div>
        )}
      </section>

      {/* 卡片 3：集合地點 */}
      <section className="rounded-3xl border-2 border-line bg-surface p-4 shadow-card">
        <label htmlFor="loc" className="mb-2 flex items-center gap-1.5 text-sm font-extrabold text-ink">
          <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-brand-soft text-xs font-black text-brand">3</span>
          <MapPin className="h-4 w-4 text-brand" aria-hidden="true" />
          集合地點
        </label>
        <select
          id="loc"
          value={pin ? "map" : location}
          onChange={(e) => {
            if (e.target.value === "map") setShowMap(true);
            else {
              setPin(null);
              setLocation(e.target.value);
            }
          }}
          className="h-12 w-full rounded-2xl border-2 border-line bg-bg px-3 text-sm font-bold text-ink focus:border-brand focus:bg-surface focus:outline-none"
        >
          {locations.map((l) => (
            <option key={l.key} value={l.key}>{l.label}</option>
          ))}
          <option value="map">📍 在地圖上選擇…</option>
        </select>
        <div className="mt-2.5 grid grid-cols-2 gap-2">
          <GameButton type="button" variant="secondary" size="sm" onClick={() => setShowMap((v) => !v)}>
            <MapIcon className="h-4 w-4 text-brand" aria-hidden="true" />
            {showMap ? "收起地圖" : "地圖選點"}
          </GameButton>
          <GameButton type="button" variant="secondary" size="sm" onClick={useMyLocation}>
            <Crosshair className="h-4 w-4 text-brand" aria-hidden="true" />
            我的位置
          </GameButton>
        </div>
        {showMap && (
          <div className="mt-3 overflow-hidden rounded-2xl border-2 border-line animate-pop-in">
            <MapPicker
              value={pin}
              onPick={(lat, lon) => {
                setPin({ lat, lon });
                setPinLabel((l) => l || "地圖選點");
              }}
            />
          </div>
        )}
        {pin && (
          <div className="mt-2.5 space-y-2">
            <input
              id="pinlabel"
              aria-label="地點名稱"
              maxLength={80}
              value={pinLabel}
              onChange={(e) => setPinLabel(e.target.value)}
              placeholder="幫這個地點取個名字（例如：駁二大義倉庫）"
              className="h-11 w-full rounded-2xl border-2 border-line bg-bg px-3 text-sm font-semibold text-ink focus:border-brand focus:bg-surface focus:outline-none"
            />
            {far && (
              <div
                data-testid="far-warning"
                className="flex items-start gap-2 rounded-2xl border-l-4 border-warn bg-warn-soft px-3 py-2 text-xs font-bold text-warn"
              >
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>超出鹽埕區（目前只有這裡有餐廳資料）</span>
              </div>
            )}
          </div>
        )}
      </section>

      {/* 卡片 4：攜伴需求 */}
      <section className="rounded-3xl border-2 border-line bg-surface p-4 shadow-card">
        <div className="mb-2 flex items-center gap-1.5 text-sm font-extrabold text-ink">
          <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-brand-soft text-xs font-black text-brand">4</span>
          有人攜伴嗎？（選填）
        </div>
        <div className="grid grid-cols-2 gap-2.5" data-testid="needs">
          <button
            type="button"
            aria-pressed={pets}
            onClick={() => setPets((v) => !v)}
            className={cn(
              "flex items-center justify-center gap-2 rounded-2xl border-2 py-3 text-sm font-extrabold transition cursor-pointer active:scale-95",
              pets ? "border-brand bg-brand-soft text-brand shadow-sm" : "border-line bg-bg text-muted hover:text-ink"
            )}
          >
            <span className="text-lg" aria-hidden="true">🐾</span> 帶寵物
          </button>
          <button
            type="button"
            aria-pressed={kids}
            onClick={() => setKids((v) => !v)}
            className={cn(
              "flex items-center justify-center gap-2 rounded-2xl border-2 py-3 text-sm font-extrabold transition cursor-pointer active:scale-95",
              kids ? "border-brand bg-brand-soft text-brand shadow-sm" : "border-line bg-bg text-muted hover:text-ink"
            )}
          >
            <span className="text-lg" aria-hidden="true">🧒</span> 帶小孩
          </button>
        </div>
        {(pets || kids) && (
          <Hint label="會怎麼影響推薦">
            {pets && "店家明確不讓寵物入內的餐廳會被排除。"}
            {pets && kids && " "}
            {kids && "帶小孩只會提醒有沒有兒童座椅或兒童餐，不排除餐廳。"}
            目前多數餐廳沒有這類資料，會標示「資訊不足」，請先向店家確認。
          </Hint>
        )}
      </section>

      <ErrorBox message={error} />

      <BottomBar>
        <GameButton type="submit" variant="primary" className="w-full" disabled={busy || !title.trim()}>
          {busy ? "開團中…" : "建立並填我的需求 →"}
        </GameButton>
      </BottomBar>
    </form>
  );
}
