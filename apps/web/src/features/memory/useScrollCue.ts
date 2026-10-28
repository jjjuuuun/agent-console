/**
 * 스크롤 단서: 영역이 넘치고 아직 끝까지 내려가지 않았을 때만 `more`가 true다.
 * 스크롤·크기 변화·내용 변화를 따라간다. 그림(그림자)은 부르는 쪽이 정한다.
 * 반환은 `[attach, more]`다. `attach`는 콜백 ref라서 영역이 나중에 그려져도(로딩 뒤) 다시 연결된다.
 */
import { useEffect, useState } from "react";

export function useScrollCue<T extends HTMLElement>(): readonly [attach: (el: T | null) => void, more: boolean] {
  const [el, setEl] = useState<T | null>(null);
  const [more, setMore] = useState(false);
  useEffect(() => {
    if (el === null) return;
    const measure = () => setMore(el.scrollHeight > el.clientHeight + 1 && el.scrollTop + el.clientHeight < el.scrollHeight - 1);
    measure();
    el.addEventListener("scroll", measure, { passive: true });
    const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    ro?.observe(el);
    for (const child of Array.from(el.children)) ro?.observe(child);
    const mo = typeof MutationObserver === "undefined" ? null : new MutationObserver(measure);
    mo?.observe(el, { childList: true, subtree: true, attributes: true });
    return () => {
      el.removeEventListener("scroll", measure);
      ro?.disconnect();
      mo?.disconnect();
    };
  }, [el]);
  return [setEl, more];
}
