import { observeElementRect, useVirtualizer, type Virtualizer } from "@tanstack/react-virtual";
import { useCallback, type RefObject } from "react";

export interface UseVirtualRowsOptions {
  count: number;
  rowHeight: number;
  scrollRef: RefObject<HTMLElement | null>;
  overscan?: number;
  /** 레이아웃을 읽을 수 없을 때(숨김·테스트 환경) 쓸 뷰포트 높이. */
  fallbackHeight?: number;
}

/**
 * 가상 스크롤 훅(@tanstack/react-virtual 어댑터). 뷰포트 높이가 0으로 읽히면(숨겨진 탭·DOM 에뮬레이터)
 * `fallbackHeight`를 써서 첫 화면 분량은 항상 그린다.
 */
export function useVirtualRows(opts: UseVirtualRowsOptions): Virtualizer<HTMLElement, Element> {
  const { count, rowHeight, scrollRef, overscan = 8, fallbackHeight = 480 } = opts;
  const observe = useCallback(
    (instance: Virtualizer<HTMLElement, Element>, cb: (rect: { width: number; height: number }) => void) =>
      observeElementRect(instance, (rect) => cb(rect.height > 0 ? rect : { width: rect.width, height: fallbackHeight })),
    [fallbackHeight],
  );
  // eslint-disable-next-line react-hooks/incompatible-library -- 가상 스크롤 결과는 이 컴포넌트 안에서만 쓰고 메모이즈된 자식에 넘기지 않는다
  return useVirtualizer<HTMLElement, Element>({
    count,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowHeight,
    overscan,
    initialRect: { width: 0, height: fallbackHeight },
    observeElementRect: observe,
  });
}
