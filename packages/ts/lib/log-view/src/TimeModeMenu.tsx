import { useEffect, useId, useRef, useState } from "react";
import { TIME_MODES, type TimeMode } from "./timeMode";

export interface TimeModeMenuProps {
  mode: TimeMode;
  onChange(mode: TimeMode): void;
  /** 메뉴 단추 접근 이름(예: "시각 표시 방식") */
  label: string;
  /** 방식 id -> 글자 */
  names: Readonly<Record<TimeMode, string>>;
}

/** 시각 열 머리에 놓는 표시 방식 메뉴(`menuitemradio`). `Esc`·바깥 클릭으로 닫고 단추로 포커스가 돌아온다. */
export function TimeModeMenu({ mode, onChange, label, names }: TimeModeMenuProps) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const btn = useRef<HTMLButtonElement>(null);
  const root = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", away, true);
    return () => document.removeEventListener("pointerdown", away, true);
  }, [open]);
  useEffect(() => {
    if (open) root.current?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus();
  }, [open]);
  const close = () => {
    setOpen(false);
    btn.current?.focus();
  };
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      close();
      return;
    }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const items = Array.from(root.current?.querySelectorAll<HTMLElement>('[role="menuitemradio"]') ?? []);
    const at = items.indexOf(document.activeElement as HTMLElement);
    items[(at + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length]?.focus();
  };
  return (
    <span ref={root} className="ac-lv-timemenu" onKeyDown={onKeyDown}>
      <button ref={btn} type="button" className="ac-lv-timemenu-btn" aria-label={`${label}: ${names[mode]}`} title={`${label}: ${names[mode]}`} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined} onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}>
        <span aria-hidden="true">▾</span>
      </button>
      {open ? (
        <div id={id} role="menu" aria-label={label} className="ac-lv-timemenu-list">
          {TIME_MODES.map((m) => (
            <button key={m} type="button" role="menuitemradio" aria-checked={m === mode} tabIndex={m === mode ? 0 : -1} onClick={() => { onChange(m); close(); }}>
              <span aria-hidden="true" className="ac-lv-timemenu-mark">{m === mode ? "●" : ""}</span>
              {names[m]}
            </button>
          ))}
        </div>
      ) : null}
    </span>
  );
}
