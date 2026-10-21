import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import type { Run } from "@agent-console/contracts";
import { StatusChip } from "@agent-console/ui";
import { delegationMessages as dm } from "../delegation";

export interface ChildRunRow {
  run: Run;
  /** 팀 구성 이름(못 읽었으면 id) */
  teamName: string;
  /** 부모 노드 label(+ 같은 노드에서 여럿이면 " · N회차") */
  nodeText: string;
  statusLabel: string;
  startedText: string;
  durationText: string;
}

export interface ChildRunsMenuProps {
  rows: readonly ChildRunRow[];
  onOpen(runId: string): void;
  /** 열린 상태를 바깥에서 알고 싶을 때(테스트 등) */
  defaultOpen?: boolean;
}

/**
 * "자식 실행 n개 ▾" 팝오버. 행(상태·팀 구성·부모 노드·시작·소요)에서 `Enter`로 연다. 자식이 0개면 컨트롤 자체가 없다.
 * `↑↓`로 행을 옮기고 `Esc`로 닫아 단추로 돌아간다.
 */
export function ChildRunsMenu({ rows, onOpen, defaultOpen = false }: ChildRunsMenuProps) {
  const [open, setOpen] = useState(defaultOpen);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    root.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);
  if (rows.length === 0) return null;
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!open) return;
    const items = Array.from(root.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    const at = items.indexOf(document.activeElement as HTMLElement);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      items[(at + 1) % items.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      items[(at - 1 + items.length) % items.length]?.focus();
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      setOpen(false);
      button.current?.focus();
    }
  };
  return (
    <div ref={root} className="dlg-childmenu" onKeyDown={onKeyDown}>
      <button ref={button} type="button" className="app-link-btn" aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined} onClick={() => setOpen((v) => !v)}>
        {dm.run.child.menu(rows.length)} <span aria-hidden="true">▾</span>
      </button>
      {open ? (
        <div id={id} role="menu" aria-label={dm.run.child.menuLabel} className="dlg-childmenu-pop">
          <ul>
            {rows.map((r) => (
              <li key={r.run.id} role="none">
                <button
                  type="button"
                  role="menuitem"
                  className="dlg-childmenu-row"
                  onClick={() => {
                    setOpen(false);
                    onOpen(r.run.id);
                  }}
                >
                  <StatusChip status={r.run.status} kind="run" label={r.statusLabel} />
                  <span className="ac-ellipsis" title={`${r.teamName} · ${r.nodeText}`}>{dm.run.child.row(r.teamName, r.nodeText)}</span>
                  <span className="app-muted">{r.startedText} · {r.durationText}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
