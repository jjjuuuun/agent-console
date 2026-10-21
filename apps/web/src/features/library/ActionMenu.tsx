import { useEffect, useId, useImperativeHandle, useRef, useState, type KeyboardEvent, type ReactNode, type Ref } from "react";
import { Button } from "@agent-console/ui";

export interface ActionMenuItem {
  id: string;
  label: string;
  onSelect: () => void;
  disabled?: boolean;
  /** 비활성 이유 등(툴팁) */
  title?: string;
  danger?: boolean;
}

export interface ActionMenuHandle {
  open: () => void;
}

export interface ActionMenuProps {
  /** 버튼의 접근성 이름 */
  label: string;
  items: readonly ActionMenuItem[];
  /** 버튼 안 내용(기본 `⋯`) */
  children?: ReactNode;
  size?: "sm" | "md";
  ref?: Ref<ActionMenuHandle>;
}

/** 작은 메뉴 버튼: `role=menu`, `↑↓ Home End`, `Esc`로 닫고 버튼으로 포커스 복귀, 바깥 클릭으로 닫기. */
export function ActionMenu({ label, items, children, size = "sm", ref }: ActionMenuProps) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const id = useId();
  useImperativeHandle(ref, () => ({ open: () => setOpen(true) }), []);

  useEffect(() => {
    if (!open) return;
    root.current?.querySelector<HTMLElement>('[role="menuitem"]:not([disabled])')?.focus();
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (!open) return;
    const els = Array.from(root.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])') ?? []);
    const at = els.indexOf(document.activeElement as HTMLElement);
    let next: number | undefined;
    if (e.key === "ArrowDown") next = (at + 1) % els.length;
    else if (e.key === "ArrowUp") next = (at - 1 + els.length) % els.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = els.length - 1;
    else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      setOpen(false);
      button.current?.focus();
      return;
    } else if (e.key === "Tab") {
      setOpen(false);
      return;
    }
    if (next === undefined || els.length === 0) return;
    e.preventDefault();
    els[next]?.focus();
  };

  return (
    <span className="lib-menu" ref={root} onKeyDown={onKeyDown}>
      <Button ref={button} size={size} variant="ghost" aria-label={label} title={label} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined} onClick={() => setOpen((v) => !v)}>
        {children ?? "⋯"}
      </Button>
      {open ? (
        <ul id={id} role="menu" aria-label={label} className="lib-menu-list">
          {items.map((item) => (
            <li key={item.id} role="none">
              <button
                type="button"
                role="menuitem"
                className="lib-menu-item"
                data-danger={item.danger ? "true" : undefined}
                disabled={item.disabled}
                title={item.title}
                onClick={() => {
                  setOpen(false);
                  button.current?.focus();
                  item.onSelect();
                }}
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </span>
  );
}
