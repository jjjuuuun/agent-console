import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";

export interface IndicatorMenuItem {
  id: string;
  label: string;
  onSelect: () => void;
}

export interface IndicatorMenuProps {
  /** 메뉴 접근성 이름 */
  label: string;
  items: readonly IndicatorMenuItem[];
  /** 화면 좌표(뷰포트 기준). 우클릭은 포인터 위치, 키보드는 표시기 모서리 */
  point: { x: number; y: number };
  /** 닫는다. `restoreFocus`가 true면 호출자가 연 요소로 포커스를 돌려준다 */
  onClose: (restoreFocus: boolean) => void;
  /** 화면 가장자리와 띄울 간격(px). 기본 8 */
  viewportMargin?: number;
}

/** 메뉴 크기(실측)로 뷰포트 안에 들어오게 좌표를 고른다. 들어갈 자리가 없으면 가장자리 간격에 맞춘다. */
export function clampToViewport(
  point: { x: number; y: number },
  size: { width: number; height: number },
  viewport: { width: number; height: number },
  margin: number,
): { x: number; y: number } {
  const fit = (p: number, s: number, v: number) => Math.max(margin, Math.min(p, v - s - margin));
  return { x: fit(point.x, size.width, viewport.width), y: fit(point.y, size.height, viewport.height) };
}

/**
 * 표시기 컨텍스트 메뉴(표현 전용): `role=menu` + `menuitem` 버튼.
 * 열리면 첫 항목에 포커스, `↑↓ Home End` 이동, `Enter`/`Space` 실행, `Esc` 닫고 복귀, `Tab`·바깥 클릭은 닫기만.
 */
export function IndicatorMenu({ label, items, point, onClose, viewportMargin = 8 }: IndicatorMenuProps) {
  const root = useRef<HTMLDivElement>(null);
  // 그리기 전(layout effect)에 실제 크기를 재서 뷰포트 안으로 옮긴다. 항목 수·글꼴에 의존하는 상수가 없다.
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  useLayoutEffect(() => {
    const el = root.current;
    if (el === null) return;
    const r = el.getBoundingClientRect();
    setPos(clampToViewport(point, { width: r.width, height: r.height }, { width: window.innerWidth, height: window.innerHeight }, viewportMargin));
  }, [point.x, point.y, items.length, viewportMargin]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    root.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) onClose(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const entries = Array.from(root.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    const i = entries.indexOf(document.activeElement as HTMLElement);
    let next: number | undefined;
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      onClose(true);
      return;
    }
    if (e.key === "Tab") {
      onClose(false);
      return;
    }
    if (e.key === "ArrowDown") next = (i + 1) % entries.length;
    else if (e.key === "ArrowUp") next = (i - 1 + entries.length) % entries.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = entries.length - 1;
    if (next === undefined) return;
    e.preventDefault();
    entries[next]?.focus();
  };

  const style = {
    position: "fixed" as const,
    left: pos?.x ?? point.x,
    top: pos?.y ?? point.y,
  };
  return createPortal(
    <div ref={root} role="menu" aria-label={label} className="usage-ind-menu" style={style} onKeyDown={onKeyDown}>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="menuitem"
          className="usage-ind-menu-item"
          data-menu-item={item.id}
          onClick={() => {
            onClose(true);
            item.onSelect();
          }}
        >
          {item.label}
        </button>
      ))}
    </div>,
    document.body,
  );
}
