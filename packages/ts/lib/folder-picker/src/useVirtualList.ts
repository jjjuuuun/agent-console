import { observeElementRect, useVirtualizer, type Virtualizer } from "@tanstack/react-virtual";
import { useCallback, type RefObject } from "react";

export interface UseVirtualListOptions {
  count: number;
  rowHeight: number;
  scrollRef: RefObject<HTMLElement | null>;
  overscan?: number;
  /** 레이아웃을 읽을 수 없을 때(DOM 에뮬레이터·숨김) 쓸 뷰포트 높이. */
  fallbackHeight?: number;
  /** 항상 그려야 하는 행(활성 행). */
  keepIndex?: number | null;
}

/** @tanstack/react-virtual 어댑터. 뷰포트 높이가 0으로 읽히면 `fallbackHeight`로 첫 화면 분량은 그린다. */
export function useVirtualList(opts: UseVirtualListOptions): Virtualizer<HTMLElement, Element> {
  const { count, rowHeight, scrollRef, overscan = 6, fallbackHeight = 280, keepIndex = null } = opts;
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
  // eslint-disable-next-line react-hooks/incompatible-library -- 가상화 결과는 이 컴포넌트 안에서만 쓴다
  return useVirtualizer({
    count,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowHeight,
    overscan,
    observeElementRect: observe,
    rangeExtractor,
  });
}
