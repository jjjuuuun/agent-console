import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export interface ActionMenuItem {
  id: string;
  label: string;
  onSelect: () => void;
  danger?: boolean;
  disabled?: boolean;
  /** 항목 아래 설명(비활성 사유 등) */
  hint?: string;
}

export interface ActionMenuProps {
  /** 버튼의 접근성 이름 */
  label: string;
  items: readonly ActionMenuItem[];
  /** 메뉴 맨 아래에 붙는 읽기 전용 줄(링크 등) */
  footer?: ReactNode;
  /** 제어형으로 열고 닫을 때(Shift+F10 등). 없으면 내부 상태 */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  icon?: ReactNode;
  size?: "sm" | "md";
}

/** 단순 동작 메뉴: 버튼 + `role=menu`. `↑↓ Home End`로 이동, `Enter`/`Space`로 실행, `Esc`로 닫고 버튼으로 복귀. */
export function ActionMenu({ label, items, footer, open: controlled, onOpenChange, icon = "⋯", size = "md" }: ActionMenuProps) {
  const [inner, setInner] = useState(false);
  const open = controlled ?? inner;
  const setOpen = (next: boolean) => {
    if (controlled === undefined) setInner(next);
    onOpenChange?.(next);
  };
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    root.current?.querySelector<HTMLElement>('[role="menuitem"]:not([disabled])')?.focus();
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const entries = Array.from(root.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])') ?? []);
    const i = entries.indexOf(document.activeElement as HTMLElement);
    if (e.key === "Escape") {
      e.stopPropagation();
      setOpen(false);
      button.current?.focus();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      entries[(i + 1) % entries.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      entries[(i - 1 + entries.length) % entries.length]?.focus();
    } else if (e.key === "Home") {
      e.preventDefault();
      entries[0]?.focus();
    } else if (e.key === "End") {
      e.preventDefault();
      entries[entries.length - 1]?.focus();
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  };

  return (
    <div ref={root} className="chat-menu" onKeyDown={open ? onKeyDown : undefined}>
      <button
        ref={button}
        type="button"
        className="ac-btn ac-icon-btn"
        data-variant="ghost"
        data-size={size}
        title={label}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={(e) => {
          e.stopPropagation();
          setOpen(!open);
        }}
      >
        <span aria-hidden="true">{icon}</span>
      </button>
      {open ? (
        <div id={menuId} role="menu" aria-label={label} className="chat-menu-popup">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              role="menuitem"
              className="chat-menu-item"
              data-danger={item.danger ? "true" : undefined}
              disabled={item.disabled}
              title={item.hint}
              onClick={(e) => {
                e.stopPropagation();
                setOpen(false);
                button.current?.focus();
                item.onSelect();
              }}
            >
              <span>{item.label}</span>
              {item.hint ? <span className="chat-menu-hint">{item.hint}</span> : null}
            </button>
          ))}
          {footer ? <div className="chat-menu-footer">{footer}</div> : null}
        </div>
      ) : null}
    </div>
  );
}
