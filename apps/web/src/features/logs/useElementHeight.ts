import { useEffect, useState, type RefObject } from "react";

/**
 * 요소의 내용 높이(px)를 따라간다(가상 스크롤 표에 `height`를 줄 때). `ResizeObserver`가 없는 환경(테스트)에서는 `fallback`.
 * `min`보다 작아지면 `min`.
 */
export function useElementHeight(ref: RefObject<HTMLElement | null>, fallback: number, min = 160): number {
  const [h, setH] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (el === null) return;
    const read = () => {
      const next = Math.floor(el.clientHeight);
      if (next > 0) setH(Math.max(min, next));
    };
    read();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref, min]);
  return h;
}
