"use client";
// 揪呷 JOEAT 共用遊戲化 UI 元件庫
import {
  AlertCircle,
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronRight,
  Info,
  Lock,
  ShieldCheck,
  Sparkles,
  Utensils,
  Users,
  Vote,
} from "lucide-react";
import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

/** 錯誤提示橫幅 */
export function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="my-3 flex items-start gap-2.5 rounded-2xl border-2 border-crit/30 bg-crit-soft px-3.5 py-3 text-sm font-semibold text-crit animate-pop-in"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}

/** 隱私保護膠囊（簡短一行） */
export function PrivacyNote({ text }: { text: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-chip px-3 py-1 text-xs font-semibold text-muted">
      <Lock className="h-3 w-3 text-brand" aria-hidden="true" />
      {text}
    </span>
  );
}

/** 底部固定行動列（含安全區域防遮擋） */
export function BottomBar({ children }: { children: ReactNode }) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-20 border-t-2 border-line/80 bg-surface/90 px-4 pt-3 pb-[calc(12px+env(safe-area-inset-bottom))] backdrop-blur-md">
      <div className="mx-auto flex max-w-[500px] items-center gap-2.5">
        {children}
      </div>
    </div>
  );
}

type GameButtonVariant = "primary" | "secondary" | "line" | "ghost" | "danger";

interface GameButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: GameButtonVariant;
  size?: "md" | "sm";
}

/** 具立體按壓手感的遊戲化按鈕 */
export function GameButton({
  variant = "secondary",
  size = "md",
  className,
  children,
  ...props
}: GameButtonProps) {
  return (
    <button
      {...props}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-2xl font-bold transition-all select-none cursor-pointer disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none disabled:translate-y-0",
        size === "md" ? "min-h-[48px] px-4 text-[0.96rem]" : "min-h-[38px] px-3 text-sm rounded-xl",
        variant === "primary" &&
          "bg-gradient-to-b from-brand-2 to-brand text-brand-ink border-0 shadow-game-brand active:translate-y-[2px] active:shadow-game-brand-press",
        variant === "line" &&
          "bg-line-green text-white border-0 shadow-game-line active:translate-y-[2px] active:shadow-none",
        variant === "secondary" &&
          "bg-surface text-ink border-2 border-line shadow-game-neutral active:translate-y-[1.5px] active:shadow-none",
        variant === "danger" &&
          "bg-crit text-white border-0 shadow-[0_3px_0_0_#991b1b] active:translate-y-[2px] active:shadow-none",
        variant === "ghost" &&
          "bg-transparent text-muted border-0 hover:bg-chip active:scale-[0.98]",
        className
      )}
    >
      {children}
    </button>
  );
}

/** 可選取膠囊（過敏原 risk="critical" 採珊瑚紅強化） */
export function Chip({
  on,
  onClick,
  children,
  risk,
  className,
}: {
  on: boolean;
  onClick: () => void;
  children: ReactNode;
  risk?: string;
  className?: string;
}) {
  const isCritical = risk === "critical";
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={cn(
        "inline-flex min-h-[38px] items-center gap-1.5 rounded-full border-2 px-3.5 py-1 text-sm font-semibold transition-all select-none cursor-pointer active:scale-95",
        !on && "border-line bg-surface text-muted hover:border-brand/40 hover:text-ink",
        on && !isCritical && "border-brand bg-brand-soft text-brand font-bold shadow-sm",
        on && isCritical && "border-crit bg-crit-soft text-crit font-bold shadow-sm",
        className
      )}
    >
      {on && (
        <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-current/15 animate-badge-bounce" aria-hidden="true">
          <Check className="h-3 w-3 stroke-[3]" />
        </span>
      )}
      {children}
    </button>
  );
}

/** 返回連結 */
export function Back({ href, children }: { href: string; children: ReactNode }) {
  return (
    <div className="mb-2">
      <Link
        href={href}
        className="inline-flex items-center gap-1 rounded-full py-1 pr-2 text-sm font-semibold text-muted no-underline transition hover:text-brand"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        <span>{children}</span>
      </Link>
    </div>
  );
}

/** 可收合說明（預設收合，不刪除資訊；搭配原生 details-content 平滑展開） */
export function Hint({ label = "說明", children }: { label?: string; children: ReactNode }) {
  return (
    <details className="hint my-2">
      <summary className="inline-flex min-h-[30px] cursor-pointer items-center gap-1.5 rounded-full px-1 text-xs font-semibold text-muted transition hover:text-brand">
        <Info className="h-3.5 w-3.5 shrink-0 text-brand/80" aria-hidden="true" />
        <span>{label}</span>
        <ChevronDown className="hint-chevron h-3.5 w-3.5 shrink-0 transition-transform duration-200" aria-hidden="true" />
      </summary>
      <div className="mt-1.5 rounded-2xl border border-line/80 bg-chip px-3.5 py-2.5 text-xs leading-relaxed text-ink">
        {children}
      </div>
    </details>
  );
}

/** 遊戲化集氣進度條 */
export function Meter({ value, total, className }: { value: number; total: number; className?: string }) {
  const pct = total > 0 ? Math.min(100, Math.round((value / total) * 100)) : 0;
  return (
    <div
      className={cn("my-2 h-3 overflow-hidden rounded-full border border-line bg-chip", className)}
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={total}
    >
      <div
        className="meter-stripe h-full rounded-full bg-gradient-to-r from-brand-2 to-brand transition-all duration-500 ease-out"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/** 分段切換控制 */
export function Seg<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (v: T) => void;
  options: [T, string][];
  label: string;
}) {
  return (
    <div className="flex gap-1 rounded-2xl border-2 border-line bg-chip p-1" role="radiogroup" aria-label={label}>
      {options.map(([v, l]) => {
        const active = value === v;
        return (
          <button
            key={v}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(v)}
            className={cn(
              "flex-1 min-h-[38px] rounded-xl text-sm font-bold transition-all cursor-pointer",
              active
                ? "bg-surface text-brand shadow-sm ring-1 ring-line"
                : "bg-transparent text-muted hover:text-ink"
            )}
          >
            {l}
          </button>
        );
      })}
    </div>
  );
}

/** 任務列表列（聚餐主頁使用） */
export function StepRow({
  href,
  icon,
  title,
  sub,
  done,
  badgeText,
  testid,
}: {
  href: string;
  icon: string;
  title: string;
  sub?: string;
  done?: boolean;
  badgeText?: string;
  testid?: string;
}) {
  return (
    <Link
      href={href}
      data-testid={testid}
      className={cn(
        "group my-2.5 flex items-center gap-3 rounded-2xl border-2 p-3.5 no-underline transition-all active:scale-[0.985]",
        done
          ? "border-ok/35 bg-surface shadow-card hover:border-ok/60"
          : "border-line bg-surface shadow-card hover:border-brand/50 hover:shadow-card-pop"
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl text-xl transition-transform group-hover:scale-105",
          done ? "bg-ok-soft text-ok" : "bg-brand-soft text-brand"
        )}
      >
        {done ? <Check className="h-6 w-6 stroke-[3]" /> : icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <b className="truncate text-[0.98rem] font-extrabold text-ink">{title}</b>
          {done && (
            <span className="shrink-0 rounded-full bg-ok-soft px-2 py-0.5 text-[0.7rem] font-extrabold text-ok">
              已完成
            </span>
          )}
          {!done && badgeText && (
            <span className="shrink-0 rounded-full bg-brand-soft px-2 py-0.5 text-[0.7rem] font-extrabold text-brand">
              {badgeText}
            </span>
          )}
        </span>
        {sub && <span className="mt-0.5 block truncate text-xs text-muted">{sub}</span>}
      </span>
      <ChevronRight className="h-5 w-5 shrink-0 text-muted/70 transition-transform group-hover:translate-x-0.5 group-hover:text-brand" aria-hidden="true" />
    </Link>
  );
}

/** 遊戲化關卡進度條（讓使用者知道目前在哪一關） */
const STAGES = [
  { key: "constraints", label: "底線", Icon: ShieldCheck },
  { key: "preferences", label: "料理", Icon: Utensils },
  { key: "hub", label: "集氣", Icon: Users },
  { key: "results", label: "推薦", Icon: Sparkles },
  { key: "vote", label: "投票", Icon: Vote },
] as const;

export function JourneyHeader({ current }: { current: (typeof STAGES)[number]["key"] }) {
  const activeIdx = STAGES.findIndex((s) => s.key === current);
  return (
    <nav aria-label="聚餐流程進度" className="mb-3 rounded-2xl border border-line bg-surface/80 px-2.5 py-2 shadow-sm">
      <ol className="m-0 flex list-none items-center justify-between gap-1 p-0">
        {STAGES.map((stage, idx) => {
          const Icon = stage.Icon;
          const isPast = idx < activeIdx;
          const isNow = idx === activeIdx;
          return (
            <li key={stage.key} className="flex flex-1 flex-col items-center gap-1">
              <div className="flex w-full items-center">
                <div className={cn("h-0.5 flex-1 rounded-full", idx === 0 ? "opacity-0" : isPast || isNow ? "bg-brand" : "bg-line")} />
                <div
                  aria-current={isNow ? "step" : undefined}
                  className={cn(
                    "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 transition-all",
                    isNow && "border-brand bg-brand text-white shadow-sm scale-105",
                    isPast && "border-ok bg-ok-soft text-ok",
                    !isNow && !isPast && "border-line bg-chip text-muted"
                  )}
                >
                  {isPast ? <Check className="h-3.5 w-3.5 stroke-[3]" /> : <Icon className="h-3.5 w-3.5" />}
                </div>
                <div className={cn("h-0.5 flex-1 rounded-full", idx === STAGES.length - 1 ? "opacity-0" : isPast ? "bg-brand" : "bg-line")} />
              </div>
              <span className={cn("text-[0.68rem] font-bold", isNow ? "text-brand" : isPast ? "text-ok" : "text-muted")}>
                {stage.label}
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/** 載入中骨架屏 */
export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="my-3 animate-pulse rounded-3xl border-2 border-line bg-surface p-4 shadow-card" aria-busy="true" aria-label="資料載入中">
      <div className="mb-3 h-5 w-1/3 rounded-full bg-chip" />
      <div className="space-y-2.5">
        {Array.from({ length: lines }).map((_, i) => (
          <div key={i} className={cn("h-3.5 rounded-full bg-chip", i === lines - 1 ? "w-2/3" : "w-full")} />
        ))}
      </div>
    </div>
  );
}

/** 揪呷品牌 Logo */
export function Logo({ size = 44 }: { size?: number }) {
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} role="img" aria-label="揪呷" className="shrink-0 drop-shadow-sm">
      <defs>
        <linearGradient id="joeat-logo-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#FF944D" />
          <stop offset="100%" stopColor="#FF6B35" />
        </linearGradient>
      </defs>
      <rect width="100" height="100" rx="26" fill="url(#joeat-logo-bg)" />
      <circle cx="50" cy="50" r="34" fill="#fff" />
      <path d="M34 45 C34 57 44 65 50 65 C56 65 66 57 66 45" fill="none" stroke="#FF6B35" strokeWidth="5" strokeLinecap="round" />
      <path d="M41 36 L41 45 M59 36 L59 45" stroke="#FF6B35" strokeWidth="5" strokeLinecap="round" />
      <circle cx="37" cy="52" r="3.5" fill="#FF944D" />
      <circle cx="63" cy="52" r="3.5" fill="#FF944D" />
    </svg>
  );
}
