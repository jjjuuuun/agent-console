import { observeElementRect, useVirtualizer, type Virtualizer } from "@tanstack/react-virtual";
import { useCallback, useEffect, useId, useRef, useState, type RefObject } from "react";

export interface UseVirtualRowsOptions {
  count: number;
  /** 고정 높이 또는 행 번호 → 높이(함수는 안정적인 참조여야 한다: useMemo/useCallback) */
  rowHeight: number | ((index: number) => number);
  scrollRef: RefObject<HTMLElement | null>;
  overscan?: number;
  /** 레이아웃을 읽을 수 없을 때(숨김·DOM 에뮬레이터) 쓸 뷰포트 높이. */
  fallbackHeight?: number;
}

/**
 * 가상 스크롤 훅(@tanstack/react-virtual 어댑터). 뷰포트 높이가 0으로 읽히면 `fallbackHeight`로 첫 화면 분량은 항상 그린다.
 * 그려지는 행은 보이는 행 + 위아래 `overscan`(기본 8).
 */
export function useVirtualRows(opts: UseVirtualRowsOptions): Virtualizer<HTMLElement, Element> {
  const { count, rowHeight, scrollRef, overscan = 8, fallbackHeight = 480 } = opts;
  const observe = useCallback(
    (instance: Virtualizer<HTMLElement, Element>, cb: (rect: { width: number; height: number }) => void) =>
      observeElementRect(instance, (rect) => cb(rect.height > 0 ? rect : { width: rect.width, height: fallbackHeight })),
    [fallbackHeight],
  );
  // eslint-disable-next-line react-hooks/incompatible-library -- 가상 스크롤 결과는 이 컴포넌트 안에서만 쓴다
  const virtualizer = useVirtualizer<HTMLElement, Element>({
    count,
    getScrollElement: () => scrollRef.current,
    estimateSize: typeof rowHeight === "number" ? () => rowHeight : rowHeight,
    overscan,
    initialRect: { width: 0, height: fallbackHeight },
    observeElementRect: observe,
  });
  useEffect(() => {
    virtualizer.measure();
  }, [virtualizer, rowHeight]);
  return virtualizer;
}

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
