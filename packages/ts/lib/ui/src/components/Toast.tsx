import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Banner, type Tone } from "./Display";
import { Button } from "./Button";

export interface ToastInput {
  tone?: Tone;
  text: string;
  /** 표시 시간(ms). 기본 5000(danger는 8000) */
  durationMs?: number;
  /** 액션 버튼 1개(예: 되돌리기). 누르면 알림을 닫는다. */
  action?: { label: string; onClick: () => void };
}

interface ToastItem extends ToastInput {
  id: number;
}

const ToastContext = createContext<(toast: ToastInput) => void>(() => {});

/** 알림 한 줄 띄우기. `ToastProvider` 밖이면 아무 일도 하지 않는다. */
export function useToast(): (toast: ToastInput) => void {
  return useContext(ToastContext);
}

function ToastView({ item, onDone }: { item: ToastItem; onDone: (id: number) => void }) {
  useEffect(() => {
    const ms = item.durationMs ?? (item.tone === "danger" ? 8000 : 5000);
    const handle = setTimeout(() => onDone(item.id), ms);
    return () => clearTimeout(handle);
  }, [item, onDone]);
  return (
    <Banner
      tone={item.tone ?? "info"}
      className="ac-toast"
      role={item.tone === "danger" ? "alert" : "status"}
      aria-live={item.tone === "danger" ? "assertive" : "polite"}
      actions={
        item.action === undefined ? undefined : (
          <Button
            size="sm"
            onClick={() => {
              item.action?.onClick();
              onDone(item.id);
            }}
          >
            {item.action.label}
          </Button>
        )
      }
    >
      {item.text}
    </Banner>
  );
}

export interface ToastProviderProps {
  children: ReactNode;
  /** 알림 영역의 접근성 이름(문구는 호출자가). */
  regionLabel?: string;
}

export function ToastProvider({ children, regionLabel }: ToastProviderProps) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const counter = useRef(0);
  const push = useCallback((toast: ToastInput) => {
    counter.current += 1;
    const id = counter.current;
    setItems((prev) => [...prev.slice(-4), { ...toast, id }]);
  }, []);
  const remove = useCallback((id: number) => setItems((prev) => prev.filter((t) => t.id !== id)), []);
  const value = useMemo(() => push, [push]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="ac-toasts" aria-label={regionLabel} role="region">
        {items.map((item) => (
          <ToastView key={item.id} item={item} onDone={remove} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}
