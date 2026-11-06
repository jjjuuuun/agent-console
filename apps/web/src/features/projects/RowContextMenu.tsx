import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Menu, type MenuItemDef } from "@agent-console/ui";

export interface RowContextMenuProps {
  /** 화면 좌표(우클릭 지점, 키보드면 항목의 왼쪽 아래) */
  x: number;
  y: number;
  label: string;
  items: readonly MenuItemDef[];
  /** 닫을 때. 포커스 복귀는 호출자가 한다 */
  onClose: () => void;
}

/**
 * 우클릭·`Shift+F10`·`ContextMenu` 키로 여는 작은 메뉴(`role="menu"`). 바깥 클릭·`Esc`·스크롤로 닫힌다.
 * 항목은 `Menu`(↑↓ Home End, Enter)가 그리고, 열리면 첫 항목에 포커스가 간다.
 */
export function RowContextMenu({ x, y, label, items, onClose }: RowContextMenuProps) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  });
  // 열릴 때 한 번만 첫 항목에 포커스를 준다(부모가 다시 그려져도 포커스를 빼앗지 않는다)
  useEffect(() => {
    ref.current?.querySelector<HTMLElement>('[role="menuitem"]:not(:disabled)')?.focus();
  }, []);
  useEffect(() => {
    const close = () => closeRef.current();
    const away = (e: Event) => {
      if (!ref.current?.contains(e.target as Node)) close();
    };
    document.addEventListener("mousedown", away, true);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", away, true);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, []);
  const left = Math.max(4, Math.min(x, window.innerWidth - 248));
  const top = Math.max(4, Math.min(y, window.innerHeight - 8 - items.length * 34));
  return createPortal(
    <div
      ref={ref}
      role="menu"
      aria-label={label}
      className="prj-ctx"
      style={{ left, top }}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onClose();
        } else if (e.key === "Tab") {
          e.preventDefault();
          onClose();
        }
      }}
    >
      <Menu items={items} onClose={onClose} />
    </div>,
    document.body,
  );
}
