/** 좌표에 뜨는 메뉴(표 행의 `Shift+F10`·우클릭). 바깥 클릭·Esc로 닫고 열리면 첫 항목에 포커스한다. 항목과 라벨은 props. */
import { useEffect, useRef } from "react";
import { Menu, type MenuItemDef } from "@agent-console/ui";

export interface AnchoredMenuProps {
  x: number;
  y: number;
  items: readonly MenuItemDef[];
  label: string;
  onClose: () => void;
}

export function AnchoredMenu({ x, y, items, label, onClose }: AnchoredMenuProps) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent && e.key !== "Escape") return;
      if (e instanceof MouseEvent && ref.current?.contains(e.target as Node)) return;
      onClose();
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    const id = requestAnimationFrame(() => ref.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus());
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
      cancelAnimationFrame(id);
    };
  }, [onClose]);
  return (
    <div ref={ref} className="ac-popover wiki-ctx" role="presentation" style={{ position: "fixed", left: x, top: y }} aria-label={label}>
      <Menu items={items} onClose={onClose} />
    </div>
  );
}
