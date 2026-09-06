"use client";
import { createContext, ReactNode, useCallback, useContext, useMemo, useState } from "react";

type Tone = "success" | "error" | "info";
interface Toast { id: number; message: string; tone: Tone }
interface ToastContextValue { toast: (message: string, tone?: Tone) => void; success: (m: string) => void; error: (m: string) => void }

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toast = useCallback((message: string, tone: Tone = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, message, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === "error" ? 7000 : 4000);
  }, []);
  const value = useMemo(() => ({ toast, success: (m: string) => toast(m, "success"), error: (m: string) => toast(m, "error") }), [toast]);
  const tones: Record<Tone, string> = { success: "border-emerald-300 bg-emerald-50 text-emerald-900", error: "border-red-300 bg-red-50 text-red-900", info: "border-blue-300 bg-blue-50 text-blue-900" };
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-80 flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} role="status" className={`pointer-events-auto rounded-md border px-3 py-2 text-sm shadow ${tones[t.tone]}`}>
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
