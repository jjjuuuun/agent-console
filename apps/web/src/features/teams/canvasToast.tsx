import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Banner, Button, useToast, type ToastInput } from "@agent-console/ui";

/** 편집기 알림 한 건. `mergeKey`가 같은 알림이 떠 있으면 합쳐서 한 개로 보인다. */
export interface CanvasToastInput extends ToastInput {
  /** 같은 종류 식별자. 떠 있는 알림과 같으면 새로 쌓지 않고 개수만 올린다. */
  mergeKey?: string;
  /** 합쳐진 개수(2 이상)일 때의 문구. 없으면 첫 문구 그대로. */
  mergeText?: (count: number) => string;
}

interface Shown extends CanvasToastInput {
  id: number;
  count: number;
}

interface CanvasToastValue {
  push: (toast: CanvasToastInput) => void;
  shown: Shown | null;
  dismiss: (id: number) => void;
}

const Ctx = createContext<CanvasToastValue | null>(null);

export interface CanvasToastProviderProps {
  children: ReactNode;
  /** 자동 닫힘(ms). 되돌리기 가능 창(`undoWindowMs`)과 같은 값을 넘긴다. 기본 5000 */
  durationMs?: number;
}

/**
 * 캔버스 안에 띄우는 알림 상태. 동시에 1개만 보이고(새 알림이 앞 것을 대체), 같은 `mergeKey`는 합친다.
 * 화면 위치는 `CanvasToastRegion`이 정한다(캔버스 요소 안에 놓는다).
 */
export function CanvasToastProvider({ children, durationMs = 5000 }: CanvasToastProviderProps) {
  const [shown, setShown] = useState<Shown | null>(null);
  const counter = useRef(0);
  const push = useCallback((toast: CanvasToastInput) => {
    setShown((prev) => {
      if (prev !== null && toast.mergeKey !== undefined && prev.mergeKey === toast.mergeKey) {
        const count = prev.count + 1;
        const text = (toast.mergeText ?? prev.mergeText)?.(count) ?? prev.text;
        counter.current += 1;
        // 되돌리기는 첫 변경 이전으로 돌아가야 하므로 처음 액션을 유지한다
        return { ...prev, text, count, id: counter.current };
      }
      counter.current += 1;
      return { ...toast, id: counter.current, count: 1 };
    });
  }, []);
  const dismiss = useCallback((id: number) => setShown((prev) => (prev?.id === id ? null : prev)), []);
  useEffect(() => {
    if (shown === null) return;
    const ms = shown.durationMs ?? durationMs;
    const handle = setTimeout(() => dismiss(shown.id), ms);
    return () => clearTimeout(handle);
  }, [shown, durationMs, dismiss]);
  const value = useMemo(() => ({ push, shown, dismiss }), [push, shown, dismiss]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** 알림 호출 함수. `CanvasToastProvider` 밖이면 전역 알림(`useToast`)으로 대신 띄운다. */
export function useCanvasToast(): (toast: CanvasToastInput) => void {
  const ctx = useContext(Ctx);
  const global = useToast();
  return ctx?.push ?? ((toast) => global(toast));
}

export interface CanvasToastRegionProps {
  /** 알림 영역의 접근성 이름 */
  label: string;
  className?: string;
}

/** 현재 알림 1개를 그린다. 위치는 부모(`position: relative`)의 좌하단. */
export function CanvasToastRegion({ label, className }: CanvasToastRegionProps) {
  const ctx = useContext(Ctx);
  const item = ctx?.shown ?? null;
  return (
    <div className={className ?? "team-canvas-toasts"} role="region" aria-label={label}>
      {item !== null && ctx !== null ? (
        <Banner
          key={item.id}
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
                  ctx.dismiss(item.id);
                }}
              >
                {item.action.label}
              </Button>
            )
          }
        >
          {item.text}
        </Banner>
      ) : null}
    </div>
  );
}
