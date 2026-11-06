import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { statusTone, type StatusLike } from "./display";
import { formatMessage, resolveMessages } from "./messages";
import { ToneChip } from "./ToneChip";

export interface TaskStatusMenuProps {
  /** 지금 상태 id */
  status: string;
  /** 고를 수 있는 상태 목록(서버 `task_statuses`). 상태 이름은 데이터다. */
  statuses: readonly StatusLike[];
  /** 접근성 이름에 들어갈 작업 이름 */
  taskTitle: string;
  onSelect?: (statusId: string) => void;
  /** 읽기 전용이면 누를 수 없는 칩만 보인다. */
  readOnly?: boolean;
  /** 막힘 이유(관문·폴더 쓰기 불가). 주면 버튼은 보이되 눌러도 열리지 않는다(aria-disabled + 설명). */
  blockedReason?: string;
  messages?: Readonly<Record<string, string>>;
}

/** 작업 상태 칩 + 상태 바꾸기 메뉴(키보드: Enter·↑↓·Esc). 낙관적으로 바꾸지 않는다 — 고른 값은 `onSelect`로만 알린다. */
export function TaskStatusMenu({ status, statuses, taskTitle, onSelect, readOnly = false, blockedReason, messages }: TaskStatusMenuProps) {
  const text = resolveMessages(messages);
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const menuId = useId();
  const reasonId = useId();
  const shown = statusTone(status, statuses);
  const blocked = blockedReason !== undefined && blockedReason !== "";

  useEffect(() => {
    if (!open) return;
    const index = Math.max(0, statuses.findIndex((s) => s.id === status));
    items.current[index]?.focus();
  }, [open, statuses, status]);

  if (readOnly) return <ToneChip label={shown.label} tone={shown.tone} />;

  const close = (focusBack: boolean) => {
    setOpen(false);
    if (focusBack) button.current?.focus();
  };
  const onMenuKey = (e: KeyboardEvent<HTMLElement>, index: number) => {
    const last = statuses.length - 1;
    const move = (to: number) => {
      e.preventDefault();
      items.current[to]?.focus();
    };
    if (e.key === "ArrowDown") move(index >= last ? 0 : index + 1);
    else if (e.key === "ArrowUp") move(index <= 0 ? last : index - 1);
    else if (e.key === "Home") move(0);
    else if (e.key === "End") move(last);
    else if (e.key === "Escape") {
      e.preventDefault();
      close(true);
    } else if (e.key === "Tab") close(false);
  };

  return (
    <span className="ac-sdd-menu-host">
      <button
        ref={button}
        type="button"
        className="ac-sdd-chip-button"
        data-sdd-trigger="status"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={`${formatMessage(text["tasks.status.change"], { title: taskTitle })}: ${shown.label}`}
        aria-disabled={blocked || undefined}
        aria-describedby={blocked ? reasonId : undefined}
        title={blocked ? blockedReason : undefined}
        onClick={() => {
          if (!blocked) setOpen((v) => !v);
        }}
      >
        <ToneChip label={shown.label} tone={shown.tone} />
        <span className="ac-sdd-caret" aria-hidden="true" />
      </button>
      {blocked ? (
        <span id={reasonId} className="ac-sdd-sr">
          {blockedReason}
        </span>
      ) : null}
      {open ? (
        <div id={menuId} role="menu" aria-label={text["tasks.status.menu"]} className="ac-sdd-menu" onBlur={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node | null) && e.relatedTarget !== button.current) setOpen(false);
        }}>
          {statuses.map((s, i) => {
            const d = statusTone(s.id, statuses);
            return (
              <button
                key={s.id}
                ref={(el) => {
                  items.current[i] = el;
                }}
                type="button"
                role="menuitemradio"
                aria-checked={s.id === status}
                aria-label={d.label}
                className="ac-sdd-menu-item"
                onKeyDown={(e) => onMenuKey(e, i)}
                onClick={() => {
                  close(true);
                  if (s.id !== status) onSelect?.(s.id);
                }}
              >
                <ToneChip label={d.label} tone={d.tone} />
              </button>
            );
          })}
        </div>
      ) : null}
    </span>
  );
}
