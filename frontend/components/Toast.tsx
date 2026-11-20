"use client";
// 全域輕量通知系統：採 popover="manual" + 固定 aria-live 區域（依 modern-web-guidance 規範）
import { CheckCircle2, Info, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

interface ToastMessage {
  id: number;
  text: string;
  tone?: "ok" | "info";
}

interface ToastContextValue {
  showToast: (text: string, tone?: "ok" | "info") => void;
}

const ToastContext = createContext<ToastContextValue>({ showToast: () => undefined });

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const [liveText, setLiveText] = useState("");
  const popoverRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const dismiss = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    const el = popoverRef.current;
    if (el && typeof el.hidePopover === "function") {
      try { el.hidePopover(); } catch { /* 已經關閉時忽略 */ }
    }
    setToast(null);
  }, []);

  const showToast = useCallback((text: string, tone: "ok" | "info" = "ok") => {
    if (timerRef.current) clearTimeout(timerRef.current);
    const id = Date.now();
    setToast({ id, text, tone });
    setLiveText(text);

    // 優先使用原生 ariaNotify（若瀏覽器支援）
    if (typeof document !== "undefined" && "ariaNotify" in document) {
      try {
        (document as Document & { ariaNotify?: (msg: string) => void }).ariaNotify?.(text);
      } catch { /* fallback 交給下方 aria-live */ }
    }

    timerRef.current = setTimeout(() => {
      // 若使用者正聚焦在通知的關閉按鈕上，先不自動消失
      if (popoverRef.current?.contains(document.activeElement)) return;
      dismiss();
    }, 2800);
  }, [dismiss]);

  useEffect(() => {
    const el = popoverRef.current;
    if (!toast || !el) return;
    if (typeof el.showPopover === "function") {
      try { el.showPopover(); } catch { /* 已開啟時忽略 */ }
    }
  }, [toast]);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {/* 螢幕閱讀器常駐播報區 */}
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {liveText}
      </div>
      {/* 原生 Top-Layer 通知容器 */}
      <div role="region" aria-label="系統通知">
        <div
          ref={popoverRef}
          {...({ popover: "manual" } as Record<string, string>)}
          className="joeat-toast"
        >
          {toast && (
            <div className="flex items-center gap-2.5 rounded-full bg-ink px-4 py-2.5 text-sm font-bold text-surface shadow-xl ring-2 ring-brand/30 animate-pop-in">
              {toast.tone === "ok" ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-ok" aria-hidden="true" />
              ) : (
                <Info className="h-4 w-4 shrink-0 text-brand-2" aria-hidden="true" />
              )}
              <span>{toast.text}</span>
              <button
                type="button"
                aria-label="關閉通知"
                onClick={dismiss}
                className="ml-1 inline-flex h-6 w-6 items-center justify-center rounded-full text-surface/70 hover:bg-surface/15 hover:text-surface"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </div>
          )}
        </div>
      </div>
    </ToastContext.Provider>
  );
}
