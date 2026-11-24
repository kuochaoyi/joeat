"use client";
// 揪呷 JOEAT — 遊戲化聚餐日期與時間選擇器（快捷膠囊 + 原生 <dialog> 月曆與時段選擇）
import { Calendar, ChevronLeft, ChevronRight, Clock, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/cn";

interface DateTimePickerProps {
  date: string;
  time: string;
  onDateChange: (nextDate: string) => void;
  onTimeChange: (nextTime: string) => void;
}

const WEEKDAYS = ["日", "一", "二", "三", "四", "五", "六"] as const;

const QUICK_TIMES = [
  { value: "12:00", emoji: "☀️", label: "12:00 午餐" },
  { value: "15:00", emoji: "🧁", label: "15:00 下午茶" },
  { value: "18:00", emoji: "🌙", label: "18:00" },
  { value: "18:30", emoji: "🌙", label: "18:30 晚餐" },
  { value: "19:00", emoji: "🌙", label: "19:00" },
  { value: "21:00", emoji: "🍢", label: "21:00 宵夜" },
] as const;

const MEAL_HOURS = [
  { group: "中午", hours: ["11", "12", "13"] },
  { group: "下午", hours: ["14", "15", "16"] },
  { group: "晚上", hours: ["17", "18", "19", "20"] },
  { group: "宵夜", hours: ["21", "22", "23"] },
] as const;

const EXTRA_HOURS = ["00", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10"] as const;
const MINUTE_STEPS = ["00", "15", "30", "45"] as const;

/** 以本地年月日組成 YYYY-MM-DD，避免時區轉換造成日期偏移 */
function formatIsoDate(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function getTodayParts(): { year: number; month: number; day: number; iso: string } {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth() + 1;
  const day = now.getDate();
  return { year, month, day, iso: formatIsoDate(year, month, day) };
}

function parseIsoDate(iso: string): { year: number; month: number; day: number } | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return null;
  const year = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  return { year, month, day };
}

function addDaysIso(baseYear: number, baseMonth: number, baseDay: number, offset: number): string {
  const d = new Date(baseYear, baseMonth - 1, baseDay + offset);
  return formatIsoDate(d.getFullYear(), d.getMonth() + 1, d.getDate());
}

function getWeekdayIndex(iso: string): number {
  const p = parseIsoDate(iso);
  if (!p) return 0;
  return new Date(p.year, p.month - 1, p.day).getDay();
}

function formatFriendlyDate(iso: string, todayIso: string): {
  main: string;
  badge: string;
  weekend: boolean;
} {
  const p = parseIsoDate(iso);
  if (!p) {
    return { main: "請選擇日期", badge: "", weekend: false };
  }
  const wd = getWeekdayIndex(iso);
  const weekend = wd === 0 || wd === 6;
  const tomorrowIso = (() => {
    const t = parseIsoDate(todayIso);
    return t ? addDaysIso(t.year, t.month, t.day, 1) : "";
  })();
  const afterTomorrowIso = (() => {
    const t = parseIsoDate(todayIso);
    return t ? addDaysIso(t.year, t.month, t.day, 2) : "";
  })();

  let rel = `週${WEEKDAYS[wd]}`;
  if (iso === todayIso) rel = `今天 · 週${WEEKDAYS[wd]}`;
  else if (iso === tomorrowIso) rel = `明天 · 週${WEEKDAYS[wd]}`;
  else if (iso === afterTomorrowIso) rel = `後天 · 週${WEEKDAYS[wd]}`;

  return {
    main: `${p.month}月${p.day}日`,
    badge: rel,
    weekend,
  };
}

function getTimeContext(time: string): { emoji: string; period: string } {
  const [hStr] = time.split(":");
  const h = Number(hStr);
  if (Number.isNaN(h)) return { emoji: "⏰", period: "時間" };
  if (time === "12:00") return { emoji: "☀️", period: "午餐" };
  if (time === "15:00") return { emoji: "🧁", period: "下午茶" };
  if (time === "18:30") return { emoji: "🌙", period: "晚餐" };
  if (time === "21:00") return { emoji: "🍢", period: "宵夜" };
  if (h >= 5 && h < 11) return { emoji: "🌅", period: "早上" };
  if (h >= 11 && h < 14) return { emoji: "☀️", period: "中午" };
  if (h >= 14 && h < 17) return { emoji: "🧁", period: "下午" };
  if (h >= 17 && h < 21) return { emoji: "🌙", period: "晚上" };
  return { emoji: "🍢", period: "宵夜" };
}

/** 替不支援 closedby="any" 的瀏覽器（如部分 Safari 版本）補上點擊外部遮罩關閉 */
function useDialogBackdropDismiss(
  dialogRef: React.RefObject<HTMLDialogElement | null>,
  open: boolean,
  onClose: () => void
) {
  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    if (open && !el.open) {
      el.showModal();
    } else if (!open && el.open) {
      el.close();
    }
  }, [dialogRef, open]);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el || typeof HTMLDialogElement === "undefined" || "closedBy" in HTMLDialogElement.prototype) {
      return;
    }
    let pressedOutside = false;
    const isOutside = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
    };
    const onDown = (e: PointerEvent) => {
      pressedOutside = isOutside(e);
    };
    const onUp = (e: PointerEvent) => {
      if (pressedOutside && isOutside(e)) {
        el.close("cancel");
        onClose();
      }
    };
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointerup", onUp);
    return () => {
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointerup", onUp);
    };
  }, [dialogRef, onClose]);
}

export function DateTimePicker({
  date,
  time,
  onDateChange,
  onTimeChange,
}: DateTimePickerProps) {
  const [dateDialogOpen, setDateDialogOpen] = useState(false);
  const [timeDialogOpen, setTimeDialogOpen] = useState(false);
  const [showEarlyHours, setShowEarlyHours] = useState(false);

  const today = useMemo(() => getTodayParts(), []);
  const parsedSelected = parseIsoDate(date);

  const [viewYear, setViewYear] = useState(parsedSelected?.year ?? today.year);
  const [viewMonth, setViewMonth] = useState(parsedSelected?.month ?? today.month);

  // 開啟月曆時同步將檢視月份切到目前已選日期所在月份
  function openDateDialog() {
    const p = parseIsoDate(date);
    if (p) {
      setViewYear(p.year);
      setViewMonth(p.month);
    } else {
      setViewYear(today.year);
      setViewMonth(today.month);
    }
    setDateDialogOpen(true);
  }

  function openTimeDialog() {
    const [h] = time.split(":");
    setShowEarlyHours(EXTRA_HOURS.includes(h as (typeof EXTRA_HOURS)[number]));
    setTimeDialogOpen(true);
  }

  // 動態計算最多 4 個近期常用日期快捷膠囊（明天、後天、即將到來的週五／週六／週日）
  const quickDates = useMemo(() => {
    const items: { iso: string; label: string; sub: string; weekend: boolean }[] = [];
    const seen = new Set<string>();
    const pushItem = (offset: number, label: string) => {
      const isoVal = addDaysIso(today.year, today.month, today.day, offset);
      if (seen.has(isoVal)) return;
      seen.add(isoVal);
      const p = parseIsoDate(isoVal)!;
      const wd = getWeekdayIndex(isoVal);
      items.push({
        iso: isoVal,
        label,
        sub: `${p.month}/${p.day}`,
        weekend: wd === 0 || wd === 6,
      });
    };

    pushItem(1, "明天");
    pushItem(2, "後天");

    for (let offset = 1; offset <= 7 && items.length < 4; offset += 1) {
      const isoVal = addDaysIso(today.year, today.month, today.day, offset);
      const wd = getWeekdayIndex(isoVal);
      if (wd === 5) pushItem(offset, "週五");
      else if (wd === 6) pushItem(offset, "週六");
      else if (wd === 0) pushItem(offset, "週日");
    }

    return items.slice(0, 4);
  }, [today.day, today.month, today.year]);

  const friendlyDate = formatFriendlyDate(date, today.iso);
  const timeCtx = getTimeContext(time);

  // 計算當月日曆格線
  const calendarCells = useMemo(() => {
    const firstDayWeekday = new Date(viewYear, viewMonth - 1, 1).getDay();
    const daysInMonth = new Date(viewYear, viewMonth, 0).getDate();
    const cells: Array<{ day: number; iso: string; weekday: number; disabled: boolean } | null> = [];

    for (let i = 0; i < firstDayWeekday; i += 1) {
      cells.push(null);
    }
    for (let d = 1; d <= daysInMonth; d += 1) {
      const isoVal = formatIsoDate(viewYear, viewMonth, d);
      const weekday = (firstDayWeekday + d - 1) % 7;
      cells.push({
        day: d,
        iso: isoVal,
        weekday,
        disabled: isoVal < today.iso,
      });
    }
    return cells;
  }, [today.iso, viewMonth, viewYear]);

  const canGoPrevMonth =
    viewYear > today.year || (viewYear === today.year && viewMonth > today.month);

  function goPrevMonth() {
    if (!canGoPrevMonth) return;
    if (viewMonth === 1) {
      setViewYear((y) => y - 1);
      setViewMonth(12);
    } else {
      setViewMonth((m) => m - 1);
    }
  }

  function goNextMonth() {
    if (viewMonth === 12) {
      setViewYear((y) => y + 1);
      setViewMonth(1);
    } else {
      setViewMonth((m) => m + 1);
    }
  }

  const dateDialogRef = useRef<HTMLDialogElement>(null);
  const timeDialogRef = useRef<HTMLDialogElement>(null);
  const dateTitleId = useId();
  const timeTitleId = useId();

  useDialogBackdropDismiss(dateDialogRef, dateDialogOpen, () => setDateDialogOpen(false));
  useDialogBackdropDismiss(timeDialogRef, timeDialogOpen, () => setTimeDialogOpen(false));

  const [selectedHour = "18", selectedMinute = "30"] = time.split(":");

  return (
    <div className="mt-3 space-y-3">
      {/* 雙欄主要選擇觸發卡片 */}
      <div className="grid grid-cols-2 gap-2.5">
        <button
          id="date"
          type="button"
          data-testid="date-picker-trigger"
          aria-label={`聚餐日期，目前選擇 ${friendlyDate.main} ${friendlyDate.badge}`}
          onClick={openDateDialog}
          className="group flex min-h-[72px] flex-col justify-between rounded-2xl border-2 border-line bg-bg px-3.5 py-2.5 text-left transition cursor-pointer hover:border-brand/60 active:scale-[0.98]"
        >
          <div className="flex w-full items-center justify-between text-[0.72rem] font-extrabold text-muted">
            <span>聚餐日期</span>
            <Calendar className="h-3.5 w-3.5 text-brand transition-transform group-hover:scale-110" aria-hidden="true" />
          </div>
          <div className="mt-1 flex flex-wrap items-center justify-between gap-1">
            <span className="whitespace-nowrap text-[0.98rem] font-black tracking-tight text-ink sm:text-base">
              {friendlyDate.main}
            </span>
            {friendlyDate.badge && (
              <span
                className={cn(
                  "shrink-0 whitespace-nowrap rounded-full px-1.5 py-0.5 text-[0.66rem] font-extrabold",
                  friendlyDate.weekend ? "bg-crit-soft text-crit" : "bg-brand-soft text-brand"
                )}
              >
                {friendlyDate.badge}
              </span>
            )}
          </div>
        </button>

        <button
          id="time"
          type="button"
          data-testid="time-picker-trigger"
          aria-label={`集合時間，目前選擇 ${time} ${timeCtx.period}`}
          onClick={openTimeDialog}
          className="group flex min-h-[72px] flex-col justify-between rounded-2xl border-2 border-line bg-bg px-3 py-2.5 text-left transition cursor-pointer hover:border-brand/60 active:scale-[0.98] sm:px-3.5"
        >
          <div className="flex w-full items-center justify-between text-[0.72rem] font-extrabold text-muted">
            <span>集合時間</span>
            <Clock className="h-3.5 w-3.5 text-brand transition-transform group-hover:scale-110" aria-hidden="true" />
          </div>
          <div className="mt-1 flex flex-wrap items-center justify-between gap-1">
            <span className="whitespace-nowrap text-[0.98rem] font-black tabular-nums tracking-tight text-ink sm:text-base">
              {time || "請選擇"}
            </span>
            <span className="shrink-0 whitespace-nowrap rounded-full bg-chip px-2 py-0.5 text-[0.66rem] font-extrabold text-ink">
              {timeCtx.emoji} {timeCtx.period}
            </span>
          </div>
        </button>
      </div>

      {/* 日期快速選擇膠囊 */}
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-xs font-bold text-muted">快速選日期</span>
          <button
            type="button"
            onClick={openDateDialog}
            className="text-xs font-bold text-brand underline-offset-2 hover:underline cursor-pointer"
          >
            開啟完整月曆
          </button>
        </div>
        <div className="grid grid-cols-4 gap-1.5">
          {quickDates.map((item) => {
            const active = date === item.iso;
            return (
              <button
                key={item.iso}
                type="button"
                aria-pressed={active}
                onClick={() => onDateChange(item.iso)}
                className={cn(
                  "flex min-h-[46px] flex-col items-center justify-center rounded-xl border-2 px-1.5 py-1.5 transition cursor-pointer active:scale-95",
                  active
                    ? "border-brand bg-brand-soft text-brand shadow-sm"
                    : "border-line bg-bg text-ink hover:border-brand/40"
                )}
              >
                <span className="text-xs font-extrabold leading-tight">{item.label}</span>
                <span
                  className={cn(
                    "text-[0.68rem] font-semibold",
                    active ? "text-brand" : item.weekend ? "text-crit" : "text-muted"
                  )}
                >
                  {item.sub}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 時間快速選擇膠囊 */}
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-xs font-bold text-muted">快速選時段</span>
          <button
            type="button"
            onClick={openTimeDialog}
            className="text-xs font-bold text-brand underline-offset-2 hover:underline cursor-pointer"
          >
            自訂時間
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {QUICK_TIMES.map((t) => {
            const active = time === t.value;
            return (
              <button
                key={t.value}
                type="button"
                aria-pressed={active}
                onClick={() => onTimeChange(t.value)}
                className={cn(
                  "inline-flex min-h-[38px] items-center gap-1 rounded-full border-2 px-3 py-1 text-xs font-bold transition cursor-pointer active:scale-95",
                  active
                    ? "border-brand bg-brand-soft text-brand shadow-sm"
                    : "border-line bg-bg text-ink hover:border-brand/40"
                )}
              >
                <span aria-hidden="true">{t.emoji}</span>
                <span>{t.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 原生 <dialog> 月曆選擇彈窗（手機端為底部抽屜） */}
      <dialog
        ref={dateDialogRef}
        {...({ closedby: "any" } as Record<string, string>)}
        aria-labelledby={dateTitleId}
        onClose={() => setDateDialogOpen(false)}
        className="joeat-dialog joeat-sheet"
      >
        <div className="rounded-t-3xl border-2 border-b-0 border-line bg-surface p-4 pb-[calc(18px+env(safe-area-inset-bottom))] shadow-2xl sm:rounded-3xl sm:border-b-2 sm:pb-4">
          <div className="mx-auto mb-3 h-1.5 w-10 rounded-full bg-line sm:hidden" aria-hidden="true" />
          <div className="mb-3 flex items-center justify-between">
            <h2 id={dateTitleId} className="m-0 flex items-center gap-2 text-base font-black text-ink">
              <Calendar className="h-4 w-4 text-brand" aria-hidden="true" />
              選擇聚餐日期
            </h2>
            <button
              type="button"
              aria-label="關閉日期選擇器"
              onClick={() => setDateDialogOpen(false)}
              className="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-bg text-muted transition hover:border-brand hover:text-ink cursor-pointer"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* 月份切換列 */}
          <div className="mb-3 flex items-center justify-between rounded-2xl bg-chip px-2 py-1.5">
            <button
              type="button"
              aria-label="上個月"
              disabled={!canGoPrevMonth}
              onClick={goPrevMonth}
              className="flex h-9 w-9 items-center justify-center rounded-xl bg-surface text-ink shadow-sm transition hover:text-brand disabled:opacity-35 disabled:cursor-not-allowed cursor-pointer"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-sm font-black text-ink">
              {viewYear} 年 {viewMonth} 月
            </span>
            <button
              type="button"
              aria-label="下個月"
              onClick={goNextMonth}
              className="flex h-9 w-9 items-center justify-center rounded-xl bg-surface text-ink shadow-sm transition hover:text-brand cursor-pointer"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>

          {/* 星期標題 */}
          <div className="mb-1 grid grid-cols-7 text-center">
            {WEEKDAYS.map((wd, idx) => (
              <span
                key={wd}
                className={cn(
                  "py-1 text-xs font-extrabold",
                  idx === 0 || idx === 6 ? "text-crit" : "text-muted"
                )}
              >
                {wd}
              </span>
            ))}
          </div>

          {/* 日期格線 */}
          <div className="grid grid-cols-7 gap-1">
            {calendarCells.map((cell, idx) => {
              if (!cell) {
                return <div key={`empty-${idx}`} className="h-10" aria-hidden="true" />;
              }
              const isSelected = cell.iso === date;
              const isToday = cell.iso === today.iso;
              const isWeekend = cell.weekday === 0 || cell.weekday === 6;

              return (
                <button
                  key={cell.iso}
                  type="button"
                  disabled={cell.disabled}
                  aria-label={`${viewYear}年${viewMonth}月${cell.day}日 週${WEEKDAYS[cell.weekday]}${isToday ? " 今天" : ""}`}
                  aria-pressed={isSelected}
                  onClick={() => {
                    onDateChange(cell.iso);
                    setDateDialogOpen(false);
                  }}
                  className={cn(
                    "relative flex h-10 items-center justify-center rounded-xl text-sm font-bold transition cursor-pointer active:scale-95",
                    "disabled:cursor-not-allowed disabled:opacity-30",
                    isSelected
                      ? "bg-brand text-white shadow-sm"
                      : isToday
                        ? "border-2 border-brand bg-brand-soft text-brand"
                        : isWeekend
                          ? "bg-bg text-crit hover:bg-brand-soft/60"
                          : "bg-bg text-ink hover:bg-brand-soft/60"
                  )}
                >
                  {cell.day}
                </button>
              );
            })}
          </div>

          {/* 彈窗底部快捷操作 */}
          <div className="mt-4 flex items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => {
                onDateChange(today.iso);
                setDateDialogOpen(false);
              }}
              className="min-h-[46px] rounded-2xl border-2 border-line bg-bg px-4 text-xs font-extrabold text-ink transition hover:border-brand cursor-pointer"
            >
              選今天
            </button>
            <button
              type="button"
              onClick={() => setDateDialogOpen(false)}
              className="min-h-[46px] flex-1 rounded-2xl bg-brand px-4 text-sm font-extrabold text-white shadow-game-brand transition active:translate-y-[2px] active:shadow-game-brand-press cursor-pointer"
            >
              完成
            </button>
          </div>
        </div>
      </dialog>

      {/* 原生 <dialog> 時間選擇彈窗（手機端為底部抽屜） */}
      <dialog
        ref={timeDialogRef}
        {...({ closedby: "any" } as Record<string, string>)}
        aria-labelledby={timeTitleId}
        onClose={() => setTimeDialogOpen(false)}
        className="joeat-dialog joeat-sheet"
      >
        <div className="rounded-t-3xl border-2 border-b-0 border-line bg-surface p-4 pb-[calc(18px+env(safe-area-inset-bottom))] shadow-2xl sm:rounded-3xl sm:border-b-2 sm:pb-4">
          <div className="mx-auto mb-3 h-1.5 w-10 rounded-full bg-line sm:hidden" aria-hidden="true" />
          <div className="mb-3 flex items-center justify-between">
            <h2 id={timeTitleId} className="m-0 flex items-center gap-2 text-base font-black text-ink">
              <Clock className="h-4 w-4 text-brand" aria-hidden="true" />
              選擇集合時間
            </h2>
            <button
              type="button"
              aria-label="關閉時間選擇器"
              onClick={() => setTimeDialogOpen(false)}
              className="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-bg text-muted transition hover:border-brand hover:text-ink cursor-pointer"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* 目前選擇的時間預覽 */}
          <div className="mb-3 flex items-center justify-between rounded-2xl bg-brand-soft px-4 py-2.5">
            <span className="text-xs font-bold text-brand">目前選擇</span>
            <span className="text-lg font-black tabular-nums text-brand">
              {timeCtx.emoji} {time}（{timeCtx.period}）
            </span>
          </div>

          {/* 小時快速點選 */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-extrabold text-muted">1. 先選小時</span>
              <button
                type="button"
                onClick={() => setShowEarlyHours((v) => !v)}
                className="text-xs font-bold text-brand hover:underline cursor-pointer"
              >
                {showEarlyHours ? "收合凌晨／早上" : "顯示凌晨／早上 (00–10)"}
              </button>
            </div>

            {showEarlyHours && (
              <div className="grid grid-cols-6 gap-1.5 rounded-2xl bg-chip p-2">
                {EXTRA_HOURS.map((h) => {
                  const active = selectedHour === h;
                  return (
                    <button
                      key={h}
                      type="button"
                      aria-pressed={active}
                      onClick={() => onTimeChange(`${h}:${selectedMinute}`)}
                      className={cn(
                        "h-9 rounded-xl text-xs font-extrabold tabular-nums transition cursor-pointer active:scale-95",
                        active
                          ? "bg-brand text-white shadow-sm"
                          : "bg-surface text-ink hover:border-brand"
                      )}
                    >
                      {h}
                    </button>
                  );
                })}
              </div>
            )}

            <div className="space-y-2">
              {MEAL_HOURS.map((grp) => (
                <div key={grp.group} className="flex items-center gap-2">
                  <span className="w-9 shrink-0 text-xs font-bold text-muted">{grp.group}</span>
                  <div className="grid flex-1 grid-cols-4 gap-1.5">
                    {grp.hours.map((h) => {
                      const active = selectedHour === h;
                      return (
                        <button
                          key={h}
                          type="button"
                          aria-pressed={active}
                          onClick={() => onTimeChange(`${h}:${selectedMinute}`)}
                          className={cn(
                            "h-10 rounded-xl border-2 text-sm font-extrabold tabular-nums transition cursor-pointer active:scale-95",
                            active
                              ? "border-brand bg-brand text-white shadow-sm"
                              : "border-line bg-bg text-ink hover:border-brand/50"
                          )}
                        >
                          {h}:00
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            {/* 分鐘快速點選 */}
            <div className="pt-1">
              <div className="mb-1.5 text-xs font-extrabold text-muted">2. 調整分鐘</div>
              <div className="grid grid-cols-4 gap-1.5">
                {MINUTE_STEPS.map((m) => {
                  const active = selectedMinute === m;
                  return (
                    <button
                      key={m}
                      type="button"
                      aria-pressed={active}
                      onClick={() => onTimeChange(`${selectedHour}:${m}`)}
                      className={cn(
                        "h-10 rounded-xl border-2 text-sm font-extrabold tabular-nums transition cursor-pointer active:scale-95",
                        active
                          ? "border-brand bg-brand-soft text-brand shadow-sm"
                          : "border-line bg-bg text-ink hover:border-brand/50"
                      )}
                    >
                      :{m}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* 保留原生時間輸入框供精確分鐘微調 */}
            <div className="flex items-center justify-between gap-3 rounded-2xl border border-line bg-chip px-3 py-2">
              <label htmlFor="exact-time-input" className="text-xs font-bold text-muted">
                或輸入精確時間
              </label>
              <input
                id="exact-time-input"
                type="time"
                value={time}
                onChange={(e) => {
                  if (e.target.value) onTimeChange(e.target.value);
                }}
                className="h-9 rounded-xl border-2 border-line bg-surface px-2.5 text-sm font-bold tabular-nums text-ink focus:border-brand focus:outline-none"
              />
            </div>
          </div>

          <button
            type="button"
            onClick={() => setTimeDialogOpen(false)}
            className="mt-4 min-h-[48px] w-full rounded-2xl bg-brand px-4 text-sm font-extrabold text-white shadow-game-brand transition active:translate-y-[2px] active:shadow-game-brand-press cursor-pointer"
          >
            確定時間
          </button>
        </div>
      </dialog>
    </div>
  );
}
