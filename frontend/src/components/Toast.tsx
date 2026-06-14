/**
 * Transient toast notifications. A learning/feedback action (e.g. marking an
 * opportunity "too risky") records a signal but otherwise resolves the item
 * silently — which reads as a no-op. A toast that fades in, holds, and fades
 * out makes "what just happened" visible without a persistent banner.
 *
 * Usage: const toast = useToast(); toast('Recorded — trains future learning.');
 */
import { createContext, useCallback, useContext, useRef, useState } from 'react';
import type { ReactNode } from 'react';

type ToastItem = { id: number; message: string };

const ToastContext = createContext<(message: string) => void>(() => {});

export const useToast = () => useContext(ToastContext);

const LIFETIME_MS = 4200; // matches the toast-life CSS animation duration

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const seq = useRef(0);

  const push = useCallback((message: string) => {
    if (!message) return;
    const id = (seq.current += 1);
    setToasts((cur) => [...cur, { id, message }]);
    window.setTimeout(
      () => setToasts((cur) => cur.filter((t) => t.id !== id)),
      LIFETIME_MS,
    );
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toast-stack" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="toast" role="status">
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
