import { useCallback, useEffect, useId, useRef, useState } from "react";

export { useVirtualRows } from "@agent-console/virtual-rows";
export type { UseVirtualRowsOptions } from "@agent-console/virtual-rows";

/** 안정적인 DOM id 접두(여러 인스턴스가 같은 화면에 있어도 겹치지 않는다). 콜론 등 선택자에 위험한 글자는 뺀다. */
export function useDomId(): string {
  return `wk${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
}

/** 제어/비제어 겸용 상태. */
export function useControllable<T>(value: T | undefined, initial: T, onChange?: (next: T) => void): [T, (next: T) => void] {
  const [inner, setInner] = useState<T>(initial);
  const cb = useRef(onChange);
  useEffect(() => {
    cb.current = onChange;
  });
  const set = useCallback((next: T) => {
    setInner(next);
    cb.current?.(next);
  }, []);
  return [value === undefined ? inner : value, set];
}

/** 시각 한 번 읽기(마운트 시점, Unix epoch 초). `now`를 주면 그 값. */
export function useNowSeconds(now?: number): number {
  const [initial] = useState(() => Math.floor(Date.now() / 1000));
  return now ?? initial;
}

/** 키 입력 중 IME 조합인지(Enter 등 가로채기 방지). */
export function isComposingEvent(e: { nativeEvent?: { isComposing?: boolean; keyCode?: number }; keyCode?: number }): boolean {
  return e.nativeEvent?.isComposing === true || e.keyCode === 229 || e.nativeEvent?.keyCode === 229;
}
