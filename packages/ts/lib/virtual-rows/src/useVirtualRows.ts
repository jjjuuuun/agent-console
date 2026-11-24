import { observeElementRect, useVirtualizer, type Virtualizer } from "@tanstack/react-virtual";
import { useCallback, useEffect, type RefObject } from "react";

export interface UseVirtualRowsOptions {
  count: number;
  /** 행 높이(px). 함수면 행마다 다를 수 있다(펼친 행). 함수는 매 렌더 새로 만들어도 된다(바뀐 것은 `measureKey`로 알린다). */
  rowHeight: number | ((index: number) => number);
  scrollRef: RefObject<HTMLElement | null>;
  overscan?: number;
  /** 레이아웃을 읽을 수 없을 때(숨김·DOM 에뮬레이터) 쓸 뷰포트 높이. */
  fallbackHeight?: number;
  /** 항상 그려야 하는 행(포커스된 행). 화면 밖이어도 DOM에서 지우지 않는다. */
  keepIndex?: number | null;
  /** 이 값이 바뀌면 캐시된 행 높이를 버린다(함수 `rowHeight`의 결과가 바뀔 때). */
  measureKey?: unknown;
}

/**
 * 가상 스크롤 훅(@tanstack/react-virtual 어댑터). 그려지는 행은 보이는 행 + 위아래 `overscan`(기본 8).
 * 뷰포트 높이가 0으로 읽히면(숨겨진 탭·DOM 에뮬레이터) `fallbackHeight`로 첫 화면 분량은 항상 그린다.
 * 숫자 `rowHeight`, 행 수(`count`), `measureKey`가 바뀌면 캐시된 높이를 버린다.
 */
export function useVirtualRows(opts: UseVirtualRowsOptions): Virtualizer<HTMLElement, Element> {
  const { count, rowHeight, scrollRef, overscan = 8, fallbackHeight = 480, keepIndex = null, measureKey } = opts;
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
    estimateSize: typeof rowHeight === "function" ? rowHeight : () => rowHeight,
    overscan,
    initialRect: { width: 0, height: fallbackHeight },
    observeElementRect: observe,
    rangeExtractor,
  });
  const fixedHeight = typeof rowHeight === "number" ? rowHeight : null;
  useEffect(() => {
    virtualizer.measure();
  }, [virtualizer, fixedHeight, measureKey, count]);
  return virtualizer;
}
