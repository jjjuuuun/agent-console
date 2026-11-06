import { observeElementRect, useVirtualizer, type Virtualizer } from "@tanstack/react-virtual";
import { useCallback, useEffect, type RefObject } from "react";

export interface UseVirtualRowsOptions {
  count: number;
  /** 행 높이(px). 함수면 행마다 다를 수 있다(펼친 행). */
  rowHeight: number | ((index: number) => number);
  scrollRef: RefObject<HTMLElement | null>;
  overscan?: number;
  /** 레이아웃을 읽을 수 없을 때(숨김·테스트 환경) 쓸 뷰포트 높이. */
  fallbackHeight?: number;
  /** 이 값이 바뀌면 캐시된 높이를 버린다. */
  measureKey?: unknown;
}

/**
 * 가상 스크롤 훅(@tanstack/react-virtual 어댑터). 그려지는 행은 보이는 행 + 위아래 `overscan`(기본 8).
 * 뷰포트 높이가 0으로 읽히면 `fallbackHeight`로 첫 화면 분량은 항상 그린다.
 */
export function useVirtualRows(opts: UseVirtualRowsOptions): Virtualizer<HTMLElement, Element> {
  const { count, rowHeight, scrollRef, overscan = 8, fallbackHeight = 480, measureKey } = opts;
  const observe = useCallback(
    (instance: Virtualizer<HTMLElement, Element>, cb: (rect: { width: number; height: number }) => void) =>
      observeElementRect(instance, (rect) => cb(rect.height > 0 ? rect : { width: rect.width, height: fallbackHeight })),
    [fallbackHeight],
  );
  // eslint-disable-next-line react-hooks/incompatible-library -- 가상 스크롤 결과는 이 컴포넌트 안에서만 쓰고 메모이즈된 자식에 넘기지 않는다
  const virtualizer = useVirtualizer<HTMLElement, Element>({
    count,
    getScrollElement: () => scrollRef.current,
    estimateSize: typeof rowHeight === "function" ? rowHeight : () => rowHeight,
    overscan,
    initialRect: { width: 0, height: fallbackHeight },
    observeElementRect: observe,
  });
  useEffect(() => {
    virtualizer.measure();
  }, [virtualizer, measureKey, count]);
  return virtualizer;
}
