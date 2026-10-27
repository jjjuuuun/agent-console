import { observeElementRect, useVirtualizer, type Virtualizer } from "@tanstack/react-virtual";
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

export interface UseVirtualRowsOptions {
  count: number;
  rowHeight: number;
  scrollRef: RefObject<HTMLElement | null>;
  overscan?: number;
  /** 레이아웃을 읽을 수 없을 때(숨김·테스트 환경) 쓸 뷰포트 높이. */
  fallbackHeight?: number;
  /** 항상 그려야 하는 행(포커스된 행). 화면 밖이어도 DOM에서 지우지 않는다. */
  keepIndex?: number | null;
}

/**
 * 가상 스크롤 훅(@tanstack/react-virtual 어댑터). 뷰포트 높이가 0으로 읽히면(숨겨진 탭·DOM 에뮬레이터)
 * `fallbackHeight`로 첫 화면 분량은 항상 그린다. 그려지는 행은 보이는 행 + 위아래 `overscan`(기본 8).
 */
export function useVirtualRows(opts: UseVirtualRowsOptions): Virtualizer<HTMLElement, Element> {
  const { count, rowHeight, scrollRef, overscan = 8, fallbackHeight = 480, keepIndex = null } = opts;
  const observe = useCallback(
    (instance: Virtualizer<HTMLElement, Element>, cb: (rect: { width: number; height: number }) => void) =>
      observeElementRect(instance, (rect) => cb(rect.height > 0 ? rect : { width: rect.width, height: fallbackHeight })),
    [fallbackHeight],
  );
  const rangeExtractor = useCallback(
    (range: { startIndex: number; endIndex: number; overscan: number; count: number }) => {
      const start = Math.max(0, range.startIndex - range.overscan);
      const end = Math.min(range.count - 1, range.endIndex + range.overscan);
      const out: number[] = [];
      for (let i = start; i <= end; i += 1) out.push(i);
      if (keepIndex !== null && keepIndex >= 0 && keepIndex < range.count && !out.includes(keepIndex)) {
        out.push(keepIndex);
        out.sort((a, b) => a - b);
      }
      return out;
    },
    [keepIndex],
  );
  // eslint-disable-next-line react-hooks/incompatible-library -- 가상 스크롤 결과는 이 컴포넌트 안에서만 쓰고 메모이즈된 자식에 넘기지 않는다
  const virtualizer = useVirtualizer<HTMLElement, Element>({
    count,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowHeight,
    overscan,
    initialRect: { width: 0, height: fallbackHeight },
    observeElementRect: observe,
    rangeExtractor,
  });
  // 행 높이가 바뀌면(검색어·모든 범위 전환) 캐시된 크기를 버린다.
  useEffect(() => {
    virtualizer.measure();
  }, [virtualizer, rowHeight]);
  return virtualizer;
}

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
