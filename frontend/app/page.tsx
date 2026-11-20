"use client";
// Screen 1 - create a dining session: a title, when, where, how many. Everything else is one tap or folded away.
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { Dispatch, FormEvent, SetStateAction, useEffect, useMemo, useState } from "react";

import { BottomBar, Chip, ErrorBox, Hint, Logo, Seg } from "@/components/ui";
import { createSession, getLocations } from "@/lib/api";
import { COVERAGE, distanceM } from "@/lib/geo";
import { getIdentity } from "@/lib/liff";
import type { LocationPreset } from "@/lib/types";

const MapPicker = dynamic(() => import("@/components/MapPicker"), { ssr: false, loading: () => <p className="muted">地圖載入中…</p> });

const PERIODS = [["12:00", "午餐"], ["15:00", "下午茶"], ["18:30", "晚餐"], ["21:00", "宵夜"]] as const;
const DEADLINES = [[6, "6 小時"], [12, "12 小時"], [24, "1 天"], [48, "2 天"], [72, "3 天"]] as const;
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const toggle = (setter: Dispatch<SetStateAction<Set<string>>>, v: string) => setter((cur) => { const n = new Set(cur); n.has(v) ? n.delete(v) : n.add(v); return n; });

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

  const next14 = useMemo(() => Array.from({ length: 14 }, (_, i) => { const d = new Date(Date.now() + (i + 1) * 86400000); return { iso: iso(d), label: `${d.getMonth() + 1}/${d.getDate()}（${"日一二三四五六"[d.getDay()]}）` }; }), []);

  useEffect(() => {
    getLocations().then((r) => setLocations(r.locations)).catch((e) => setError(e.message));
    setDate(iso(new Date(Date.now() + 3 * 86400000)));
  }, []);

  const slots = [...days].sort().flatMap((d) => [...periods].sort().map((p) => `${d}T${p}:00+08:00`));
  const far = pin ? distanceM(pin.lat, pin.lon, COVERAGE.lat, COVERAGE.lon) > COVERAGE.radiusM : false;

  function useMyLocation() {
    setError(null);
    if (!navigator.geolocation) { setError("這個瀏覽器不支援定位，請在地圖上點選。"); return; }
    navigator.geolocation.getCurrentPosition(
      (p) => { setPin({ lat: p.coords.latitude, lon: p.coords.longitude }); setPinLabel((l) => l || "我的位置"); setShowMap(true); },
      () => setError("無法取得位置，請在地圖上點選。"), { timeout: 8000 });
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (mode === "poll" && slots.length < 2) { setError("請至少選 2 個時段（日期 × 時段）。"); return; }
    setBusy(true);
    setError(null);
    try {
      const me = await getIdentity();
      const place = pin ? { meeting_lat: pin.lat, meeting_lon: pin.lon, location_label: pinLabel.trim() || "地圖選點" } : { location_preset: location };
      const s = await createSession({
        title: title.trim(), party_size: size, line_group_id: me.groupId, host_line_user_id: me.userId, host_id_token: me.idToken, ...place,
        needs_pets: pets, needs_kids: kids,
        ...(mode === "fixed" ? { date, time } : { time_mode: "poll" as const, time_slots: slots, time_deadline_hours: deadline }),
      });
      router.push(`/s/${s.session_id}/constraints`);                     // straight to your own needs (the host is a participant too)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "4px 0 12px" }}>
        <Logo size={44} />
        <div><h1 style={{ margin: 0 }}>揪呷</h1><div className="muted">2–20 人聚餐，30 秒收集需求</div></div>
      </div>

      <div className="card">
        <label htmlFor="title" style={{ marginTop: 0 }}>聚餐名稱</label>
        <input id="title" required maxLength={80} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="例如：高中同學聚餐" />

        <label>時間</label>
        <Seg label="時間怎麼決定" value={mode} onChange={setMode} options={[["fixed", "我來決定"], ["poll", "大家投票"]]} />
        {mode === "fixed" ? (
          <div className="row" style={{ marginTop: 10 }}>
            <input id="date" aria-label="日期" type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
            <input id="time" aria-label="時間" type="time" required value={time} onChange={(e) => setTime(e.target.value)} />
          </div>
        ) : (
          <div data-testid="poll-setup" style={{ marginTop: 10 }}>
            <div className="tiny" style={{ marginBottom: 6 }}>可能的日期</div>
            <div className="chips">{next14.map((d) => <Chip key={d.iso} on={days.has(d.iso)} onClick={() => toggle(setDays, d.iso)}>{d.label}</Chip>)}</div>
            <div className="tiny" style={{ margin: "10px 0 6px" }}>時段</div>
            <div className="chips">{PERIODS.map(([v, l]) => <Chip key={v} on={periods.has(v)} onClick={() => toggle(setPeriods, v)}>{l}</Chip>)}</div>
            <div className="row" style={{ marginTop: 10, alignItems: "center" }}>
              <span className="muted" data-testid="slot-count">{slots.length} 個時段{slots.length < 2 ? "（至少 2 個）" : ""}</span>
              <select id="deadline" aria-label="投票截止" value={deadline} onChange={(e) => setDeadline(Number(e.target.value))}>{DEADLINES.map(([h, l]) => <option key={h} value={h}>{l}後截止</option>)}</select>
            </div>
          </div>
        )}

        <label htmlFor="loc">集合地點</label>
        <select id="loc" value={pin ? "map" : location} onChange={(e) => { if (e.target.value === "map") setShowMap(true); else { setPin(null); setLocation(e.target.value); } }}>
          {locations.map((l) => <option key={l.key} value={l.key}>{l.label}</option>)}
          <option value="map">📍 在地圖上選擇…</option>
        </select>
        <div className="row" style={{ marginTop: 8 }}>
          <button type="button" className="small" onClick={() => setShowMap((v) => !v)}>{showMap ? "收起地圖" : "🗺 地圖選點"}</button>
          <button type="button" className="small" onClick={useMyLocation}>📡 我的位置</button>
        </div>
        {showMap && <div style={{ marginTop: 8 }}><MapPicker value={pin} onPick={(lat, lon) => { setPin({ lat, lon }); setPinLabel((l) => l || "地圖選點"); }} /></div>}
        {pin && (
          <>
            <input id="pinlabel" aria-label="地點名稱" style={{ marginTop: 8 }} maxLength={80} value={pinLabel} onChange={(e) => setPinLabel(e.target.value)} placeholder="地點名稱" />
            {far && <div className="status warn" data-testid="far-warning">⚠ 超出鹽埕區（目前只有這裡有餐廳資料）</div>}
          </>
        )}

        <label>人數</label>
        <div className="stepper" id="size">
          <button type="button" aria-label="減少一人" onClick={() => setSize((n) => Math.max(2, n - 1))}>−</button>
          <b data-testid="size">{size} 人</b>
          <button type="button" aria-label="增加一人" onClick={() => setSize((n) => Math.min(20, n + 1))}>＋</button>
        </div>

        <label>有人攜伴嗎？</label>
        <div className="chips" data-testid="needs">
          <Chip on={pets} onClick={() => setPets((v) => !v)}>🐾 帶寵物</Chip>
          <Chip on={kids} onClick={() => setKids((v) => !v)}>🧒 帶小孩</Chip>
        </div>
        {(pets || kids) && (
          <Hint label="會怎麼影響推薦">
            {pets && "店家明確不讓寵物入內的餐廳會被排除。"}{pets && kids && " "}{kids && "帶小孩只會提醒有沒有兒童座椅或兒童餐，不排除餐廳。"}目前多數餐廳沒有這類資料，會標示「資訊不足」，請先向店家確認。
          </Hint>
        )}
      </div>
      <ErrorBox message={error} />
      <BottomBar><button className="primary" disabled={busy || !title.trim()}>{busy ? "建立中…" : "建立並填我的需求 →"}</button></BottomBar>
    </form>
  );
}
