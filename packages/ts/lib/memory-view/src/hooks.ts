import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

export { useVirtualRows } from "@agent-console/virtual-rows";
export type { UseVirtualRowsOptions } from "@agent-console/virtual-rows";

/** 요소 폭을 관찰한다. 레이아웃이 없는 환경(폭 0)에서는 `fallback`. */
export function useElementWidth(ref: RefObject<HTMLElement | null>, fallback: number): number {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const read = () => setWidth((prev) => {
      const w = Math.round(el.getBoundingClientRect().width);
      return prev === w ? prev : w;
    });
    read();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return width > 0 ? width : fallback;
}

/** 제어/비제어 겸용 상태. `value`가 있으면 그 값이 이기고, 바꾸려는 값은 `onChange`로만 낸다. */
export function useControllable<T>(value: T | undefined, initial: T, onChange?: (next: T) => void): [T, (next: T) => void] {
  const [inner, setInner] = useState<T>(initial);
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  });
  const set = useCallback((next: T) => {
    setInner(next);
    onChangeRef.current?.(next);
  }, []);
  return [value === undefined ? inner : value, set];
}

/** 지금 시각(Unix epoch 초). `now`를 주면 그 값(테스트·고정), 아니면 마운트 시점 값. */
export function useNowSeconds(now?: number): number {
  const [initial] = useState(() => Math.floor(Date.now() / 1000));
  return now ?? initial;
}
