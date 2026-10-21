import { useEffect, useId, useRef, useState } from "react";
import { Button } from "@agent-console/ui";
import { useStorage } from "../../app/StorageContext";
import { logsMessages as t } from "./messages";

/** 열 구성 상태: 화면 선택이라 localStorage에 둔다(`key`). 저장된 값이 깨졌거나 목록에 없는 열 id면 기본으로 돌아간다. */
export function useColumnChoice(key: string, all: readonly string[], defaults: readonly string[]): [string[], (next: string[]) => void] {
  const storage = useStorage();
  const [ids, setIds] = useState<string[]>(() => {
    try {
      const raw = storage.get(key);
      const parsed: unknown = raw === null ? null : JSON.parse(raw);
      if (Array.isArray(parsed)) {
        const ok = parsed.filter((x): x is string => typeof x === "string" && all.includes(x));
        if (ok.length > 0) return ok;
      }
    } catch {
      /* 기본값 */
    }
    return [...defaults];
  });
  const set = (next: string[]) => {
    const ordered = all.filter((id) => next.includes(id));
    setIds(ordered);
    storage.set(key, JSON.stringify(ordered));
  };
  return [ids, set];
}

export interface ColumnsMenuProps {
  all: readonly string[];
  selected: readonly string[];
  labelOf(id: string): string;
  onChange(next: string[]): void;
}

/** [열 ▾] 메뉴: 체크박스로 표시할 열을 고른다. 최소 한 열은 남긴다. `Esc`로 닫고 버튼으로 포커스가 돌아간다. */
export function ColumnsMenu({ all, selected, labelOf, onChange }: ColumnsMenuProps) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    pop.current?.querySelector<HTMLElement>("[type=checkbox]")?.focus();
    const down = (e: MouseEvent) => {
      if (!pop.current?.contains(e.target as Node) && !btn.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", down);
    return () => document.removeEventListener("mousedown", down);
  }, [open]);
  return (
    <span className="logs-colmenu">
      <Button ref={btn} size="sm" aria-haspopup="true" aria-expanded={open} aria-controls={open ? id : undefined} onClick={() => setOpen(!open)}>
        {t.filters.columns} ▾
      </Button>
      {open ? (
        <div
          ref={pop}
          id={id}
          role="group"
          aria-label={t.filters.columnsLabel}
          className="logs-popover"
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.stopPropagation();
              setOpen(false);
              btn.current?.focus();
            }
          }}
        >
          {all.map((c) => (
            <label key={c} className="app-check">
              <input
                type="checkbox"
                checked={selected.includes(c)}
                disabled={selected.length === 1 && selected.includes(c)}
                onChange={(e) => onChange(e.target.checked ? [...selected, c] : selected.filter((x) => x !== c))}
              />
              {labelOf(c)}
            </label>
          ))}
        </div>
      ) : null}
    </span>
  );
}
