import { useEffect, useState, type RefObject } from "react";

import { CELL_WIDTH_PX, cellsForWidth } from "./middleEllipsis";

/**
 * 요소 폭을 ResizeObserver로 재서 쓸 수 있는 칸 수(`floor(폭/7.5)-1`)를 돌려준다.
 * 측정 전·측정 불가(ResizeObserver 없음, 폭 0)면 null — 호출한 쪽이 CSS 끝 줄임으로 폴백한다.
 */
export function useElementCells(ref: RefObject<HTMLElement | null>, cellWidthPx: number = CELL_WIDTH_PX): number | null {
  const [cells, setCells] = useState<number | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const measure = (w: number) => setCells(w > 0 ? cellsForWidth(w, cellWidthPx) : null);
    measure(el.getBoundingClientRect().width);
    const ro = new ResizeObserver((entries) => {
      const e = entries[entries.length - 1];
      if (e) measure(e.contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref, cellWidthPx]);
  return cells;
}
