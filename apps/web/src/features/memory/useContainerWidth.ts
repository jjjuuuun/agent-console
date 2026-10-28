import { useEffect, useState, type RefObject } from "react";

/**
 * 요소 폭(px)을 관찰한다. 칸 전환은 뷰포트가 아니라 이 컨테이너 폭으로 판단한다(사이드바 펼침·접힘으로 같은 뷰포트에서도 달라진다).
 * 레이아웃을 읽을 수 없는 환경(폭 0)에서는 `fallback`을 돌려준다.
 */
export function useContainerWidth(ref: RefObject<HTMLElement | null>, fallback: number): number {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (el === null) return;
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
