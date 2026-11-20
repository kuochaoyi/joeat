"use client";
// 原生 <dialog> 確認防呆彈窗（依 modern-web-guidance dialog 規範）
// 不加 role="dialog" 或 aria-modal；將 autoFocus 放在安全動作（取消）上防止誤觸。
import { AlertTriangle } from "lucide-react";
import { useEffect, useId, useRef } from "react";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "確定",
  cancelLabel = "先不要",
  destructive = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descId = useId();

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    if (open && !el.open) {
      el.showModal();
    } else if (!open && el.open) {
      el.close();
    }
  }, [open]);

  // Safari 不支援 closedby="any" 時的點擊外部關閉 fallback
  useEffect(() => {
    const el = dialogRef.current;
    if (!el || typeof HTMLDialogElement === "undefined" || "closedBy" in HTMLDialogElement.prototype) return;
    let pressedOutside = false;
    const isOutside = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
    };
    const onDown = (e: PointerEvent) => { pressedOutside = isOutside(e); };
    const onUp = (e: PointerEvent) => {
      if (pressedOutside && isOutside(e)) el.close("cancel");
    };
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointerup", onUp);
    return () => {
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointerup", onUp);
    };
  }, []);

  function handleClose() {
    const el = dialogRef.current;
    const val = el?.returnValue ?? "";
    if (el) el.returnValue = "";
    if (val === "confirm") {
      onConfirm();
    } else {
      onCancel();
    }
  }

  return (
    <dialog
      ref={dialogRef}
      {...({ closedby: "any" } as Record<string, string>)}
      aria-labelledby={titleId}
      aria-describedby={descId}
      onClose={handleClose}
      className="joeat-dialog"
    >
      <div className="rounded-3xl border-2 border-line bg-surface p-5 shadow-2xl animate-pop-in">
        <div className="mb-3 flex items-center gap-3">
          <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${destructive ? "bg-crit-soft text-crit" : "bg-brand-soft text-brand"}`}>
            <AlertTriangle className="h-5 w-5" aria-hidden="true" />
          </div>
          <h2 id={titleId} className="m-0 text-lg font-extrabold text-ink">
            {title}
          </h2>
        </div>
        <p id={descId} className="mb-5 text-sm leading-relaxed text-muted">
          {description}
        </p>
        <form method="dialog" className="flex gap-2.5">
          <button
            type="submit"
            value="cancel"
            autoFocus
            className="flex-1 min-h-[46px] rounded-2xl border-2 border-line bg-surface px-4 text-sm font-bold text-ink transition active:translate-y-[1px]"
          >
            {cancelLabel}
          </button>
          <button
            type="submit"
            value="confirm"
            className={`flex-1 min-h-[46px] rounded-2xl px-4 text-sm font-extrabold text-white transition active:translate-y-[2px] ${
              destructive
                ? "bg-crit shadow-[0_3px_0_0_#991b1b] active:shadow-none"
                : "bg-brand shadow-game-brand active:shadow-game-brand-press"
            }`}
          >
            {confirmLabel}
          </button>
        </form>
      </div>
    </dialog>
  );
}
