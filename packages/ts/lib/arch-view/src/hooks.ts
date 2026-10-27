import { useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import type { Size } from "./layout";

/**
 * 요소 크기를 관찰한다. 레이아웃이 없는 환경(크기 0)에서는 `fallback`을 쓴다. 요소가 나중에 생기거나 바뀌는 경우(보기 전환)를 위해 `remountKey`가 바뀌면 다시 붙는다.
 */
export function useElementSize(ref: RefObject<HTMLElement | null>, fallback?: Size, remountKey?: unknown): Size {
  const [size, setSize] = useState<Size>({ width: 0, height: 0 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const read = () => {
      const r = el.getBoundingClientRect();
      setSize((prev) => (prev.width === r.width && prev.height === r.height ? prev : { width: r.width, height: r.height }));
    };
    read();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref, remountKey]);
  return size.width > 0 && size.height > 0 ? size : (fallback ?? size);
}

/** 제어/비제어 겸용 상태. `value`가 있으면 그 값이 이기고, 바꾸려는 값은 `onChange`로만 낸다. */
export function useControllable<T>(value: T | undefined, initial: T, onChange?: (next: T) => void): [T, (next: T) => void] {
  const [inner, setInner] = useState<T>(initial);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const set = useCallback((next: T) => {
    setInner(next);
    onChangeRef.current?.(next);
  }, []);
  return [value === undefined ? inner : value, set];
}
