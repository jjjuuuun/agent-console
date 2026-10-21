import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

export interface LogMenuItem {
  id: string;
  label: string;
  onSelect: () => void;
  disabled?: boolean;
  /** 항목 위에 구분선 */
  separator?: boolean;
}

export interface LogMenuProps {
  /** 접근성 이름 */
  label: string;
  /** 화면 좌표. `element`가 있으면 그 요소 아래에 붙이고, 닫을 때 포커스를 돌려준다. */
  anchor: { x: number; y: number; element?: HTMLElement | undefined };
  items: readonly LogMenuItem[];
  /** 항목 아래 12px muted 안내 */
  footnote?: ReactNode;
  onClose: () => void;
}

/**
 * 행·버튼 메뉴(`role="menu"`): `↑↓ Home End`로 이동, `Enter`/`Space` 선택, `Esc`/바깥 클릭/`Tab`으로 닫는다.
 * 닫으면 열기 전에 포커스가 있던 요소로 돌아간다. 항목은 호출자 데이터다.
 */
export function LogMenu({ label, anchor, items, footnote, onClose }: LogMenuProps) {
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(null);
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  });

  useEffect(() => {
    opener.current = document.activeElement;
    ref.current?.querySelector<HTMLElement>('[role="menuitem"]:not([disabled])')?.focus();
    const down = (e: MouseEvent) => {
      if (ref.current !== null && !ref.current.contains(e.target as Node)) closeRef.current();
    };
    document.addEventListener("mousedown", down);
    return () => {
      document.removeEventListener("mousedown", down);
      const back = anchor.element ?? opener.current;
      if (back instanceof HTMLElement && back.isConnected) back.focus();
    };
    // 열릴 때 한 번만
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const move = (delta: number | "first" | "last") => {
    const list = Array.from(ref.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])') ?? []);
    if (list.length === 0) return;
    const cur = list.indexOf(document.activeElement as HTMLElement);
    const next = delta === "first" ? 0 : delta === "last" ? list.length - 1 : (cur + delta + list.length) % list.length;
    list[next]?.focus();
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      move(1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      move(-1);
    } else if (e.key === "Home") {
      e.preventDefault();
      move("first");
    } else if (e.key === "End") {
      e.preventDefault();
      move("last");
    } else if (e.key === "Tab") {
      onClose();
    }
  };

  const el = anchor.element;
  const rect = el?.getBoundingClientRect();
  const left = anchor.x > 0 || anchor.y > 0 ? anchor.x : (rect?.left ?? 24);
  const top = anchor.x > 0 || anchor.y > 0 ? anchor.y : (rect?.bottom ?? 24);
  return createPortal(
    <div ref={ref} className="logs-menu" role="menu" aria-label={label} id={id} style={{ left: Math.min(left, window.innerWidth - 240), top: Math.min(top, window.innerHeight - 40) }} onKeyDown={onKey}>
      {items.map((it) => (
        <div key={it.id} role="none">
          {it.separator ? <div className="logs-menu-sep" role="separator" /> : null}
          <button
            type="button"
            role="menuitem"
            className="logs-menu-item"
            disabled={it.disabled}
            onClick={() => {
              onClose();
              it.onSelect();
            }}
          >
            {it.label}
          </button>
        </div>
      ))}
      {footnote === undefined ? null : <p className="logs-menu-note app-muted">{footnote}</p>}
    </div>,
    document.body,
  );
}
