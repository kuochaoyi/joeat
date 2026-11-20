"use client";
import Link from "next/link";
import type { ReactNode } from "react";

export function ErrorBox({ message }: { message: string | null }) {
  return message ? <div className="error" role="alert">{message}</div> : null;
}

/** One short line, not a paragraph. */
export function PrivacyNote({ text }: { text: string }) {
  return <span className="privacy">🔒 {text}</span>;
}

export function BottomBar({ children }: { children: ReactNode }) {
  return <div className="bar"><div className="inner">{children}</div></div>;
}

export function Chip({ on, onClick, children, risk }: { on: boolean; onClick: () => void; children: ReactNode; risk?: string }) {
  return (
    <button type="button" className={`chip${on ? " on" : ""}${risk ? ` risk-${risk}` : ""}`} aria-pressed={on} onClick={onClick}>
      {children}
    </button>
  );
}

export function Back({ href, children }: { href: string; children: ReactNode }) {
  return <p style={{ margin: "0 0 4px" }}><Link href={href} className="muted">← {children}</Link></p>;
}

/** Long explanations live in here, closed by default: the page stays short, nothing is deleted. */
export function Hint({ label = "說明", children }: { label?: string; children: ReactNode }) {
  return <details className="hint"><summary>{label}</summary><div>{children}</div></details>;
}

export function Meter({ value, total }: { value: number; total: number }) {
  const pct = total > 0 ? Math.min(100, Math.round((value / total) * 100)) : 0;
  return <div className="meter" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={total}><i style={{ width: `${pct}%` }} /></div>;
}

/** Two or three options as one capsule. */
export function Seg<T extends string>({ value, onChange, options, label }: { value: T; onChange: (v: T) => void; options: [T, string][]; label: string }) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map(([v, l]) => <button key={v} type="button" role="radio" aria-checked={value === v} className={value === v ? "on" : ""} onClick={() => onChange(v)}>{l}</button>)}
    </div>
  );
}

/** A list row: icon, one-line title, one grey line, optional chevron. */
export function StepRow({ href, icon, title, sub, done, testid }: { href: string; icon: string; title: string; sub?: string; done?: boolean; testid?: string }) {
  return (
    <Link href={href} className={`step${done ? " done" : ""}`} data-testid={testid}>
      <span className="ico" aria-hidden="true">{done ? "✅" : icon}</span>
      <span className="t"><b>{title}</b>{sub && <span>{sub}</span>}</span>
      <span className="go" aria-hidden="true">›</span>
    </Link>
  );
}

export function Logo({ size = 40 }: { size?: number }) {
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} role="img" aria-label="揪呷">
      <rect width="100" height="100" rx="24" fill="#FF6B35" /><circle cx="50" cy="50" r="34" fill="#fff" />
      <path d="M34 44 C34 56 44 64 50 64 C56 64 66 56 66 44" fill="none" stroke="#FF6B35" strokeWidth="4.5" strokeLinecap="round" />
      <path d="M42 36 L42 46 M58 36 L58 46" stroke="#FF6B35" strokeWidth="4.5" strokeLinecap="round" />
      <circle cx="38" cy="52" r="3" fill="#FF8C42" /><circle cx="62" cy="52" r="3" fill="#FF8C42" />
    </svg>
  );
}
