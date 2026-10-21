import { createContext, useContext, useEffect, useId, useMemo, useRef, type ReactNode } from "react";
import { isImeKeyEvent } from "../lib/ime";

/**
 * `Esc` 레이어 스택. 한 번의 `Esc`는 가장 위(가장 나중에 열린) 레이어 하나만 닫는다.
 * 팔레트·메뉴·다이얼로그는 자기 컴포넌트가 `Esc`를 먼저 처리하고 전파를 멈추므로 여기까지 오지 않는다.
 * 여기에는 드로어·상세 패널·선택 해제처럼 컴포넌트가 직접 처리하지 않는 레이어를 등록한다.
 */
interface Registry {
  register(id: string, handler: () => void): () => void;
}

const EscapeContext = createContext<Registry | null>(null);

export function EscapeProvider({ children, target }: { children: ReactNode; target?: Pick<Window, "addEventListener" | "removeEventListener"> }) {
  const stack = useRef<{ id: string; handler: () => void }[]>([]);
  const registry = useMemo<Registry>(
    () => ({
      register(id, handler) {
        stack.current = [...stack.current.filter((l) => l.id !== id), { id, handler }];
        return () => {
          stack.current = stack.current.filter((l) => l.id !== id);
        };
      },
    }),
    [],
  );
  useEffect(() => {
    const el = target ?? window;
    const onKeyDown = (event: Event) => {
      const e = event as KeyboardEvent;
      if (e.key !== "Escape" || e.defaultPrevented || isImeKeyEvent(e)) return;
      const top = stack.current.at(-1);
      if (top === undefined) return;
      e.preventDefault();
      top.handler();
    };
    el.addEventListener("keydown", onKeyDown);
    return () => el.removeEventListener("keydown", onKeyDown);
  }, [target]);
  return <EscapeContext.Provider value={registry}>{children}</EscapeContext.Provider>;
}

/** `active`인 동안 `onEscape`를 레이어로 등록한다. 나중에 등록한 레이어가 먼저 닫힌다. */
export function useEscapeLayer(active: boolean, onEscape: () => void): void {
  const registry = useContext(EscapeContext);
  const id = useId();
  const ref = useRef(onEscape);
  useEffect(() => {
    ref.current = onEscape;
  });
  useEffect(() => {
    if (!active || registry === null) return;
    return registry.register(id, () => ref.current());
  }, [active, registry, id]);
}
