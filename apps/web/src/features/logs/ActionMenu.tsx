import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Popover } from "@agent-console/ui";

/**
 * 메뉴 항목(데이터). `item` = 누르면 실행하고 닫힘, `check` = 체크 항목(`menuitemcheckbox`, 눌러도 열려 있음),
 * `radio` = 같은 `group`의 라디오 항목(`menuitemradio`, 열려 있음), `heading` = 구역 제목(뒤따르는 `radio`·`check` 항목들을 `role="group"`으로 묶는다), `separator` = 구분선.
 */
export type ActionMenuEntry =
  | { kind: "item"; id: string; label: string; onSelect: () => void; disabled?: boolean; title?: string; hint?: string }
  | { kind: "check"; id: string; label: string; checked: boolean; onChange: (next: boolean) => void; disabled?: boolean }
  | { kind: "radio"; id: string; label: string; checked: boolean; onSelect: () => void }
  | { kind: "heading"; id: string; label: string }
  | { kind: "separator"; id: string };

export interface ActionMenuProps {
  /** 메뉴 접근성 이름(트리거 `aria-label`이 아니라 패널 이름) */
  label: string;
  /** 트리거 글자(보이는 내용) */
  trigger: ReactNode;
  /** 트리거 접근성 이름. 보이는 글자가 줄임말이면 전체 문구를 준다 */
  triggerLabel?: string;
  triggerTitle?: string;
  entries: readonly ActionMenuEntry[];
  align?: "start" | "end";
  /** 제어형 열림 상태(키로 열 때). 없으면 내부 상태 */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** 트리거에 붙이는 표시(예: 속도 값) */
  triggerClassName?: string;
  triggerVariant?: "secondary" | "ghost";
  /** 패널 맨 아래 안내(12px muted) */
  footnote?: ReactNode;
}

const ITEM_SELECTOR = '[role="menuitem"]:not(:disabled), [role="menuitemcheckbox"]:not(:disabled), [role="menuitemradio"]:not(:disabled)';

/**
 * 트리거 단추 하나 + 항목 메뉴(`role="menu"`). `↑↓ Home End`로 이동하고 `Esc`로 닫으면 포커스가 트리거로 돌아온다
 * (열기·닫기·바깥 클릭은 `@agent-console/ui`의 `Popover`). 항목은 호출자가 주는 데이터이며 화면별 이름을 모른다.
 * 비어 있는 메뉴(보이는 항목이 없음)는 그리지 않는다.
 */
export function ActionMenu({ label, trigger, triggerLabel, triggerTitle, entries, align = "end", open, onOpenChange, triggerClassName, triggerVariant = "secondary", footnote }: ActionMenuProps) {
  const [inner, setInner] = useState(false);
  const controlled = open !== undefined;
  const isOpen = controlled ? open : inner;
  const setOpen = (v: boolean) => {
    if (!controlled) setInner(v);
    onOpenChange?.(v);
  };
  const ref = useRef<HTMLDivElement>(null);
  const actionable = entries.filter((e) => e.kind === "item" || e.kind === "check" || e.kind === "radio");
  if (actionable.length === 0) return null;
  const firstEnabled = actionable.find((e) => !("disabled" in e && e.disabled === true));

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const list = Array.from(ref.current?.querySelectorAll<HTMLElement>(ITEM_SELECTOR) ?? []);
    if (list.length === 0) return;
    const i = list.indexOf(document.activeElement as HTMLElement);
    let next: number | undefined;
    if (e.key === "ArrowDown") next = (i + 1) % list.length;
    else if (e.key === "ArrowUp") next = (i - 1 + list.length) % list.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = list.length - 1;
    if (next === undefined) return;
    e.preventDefault();
    list[next]?.focus();
  };

  // 라디오 그룹: heading 뒤의 연속된 radio를 `role="group"` 하나로 묶는다.
  const nodes: ReactNode[] = [];
  let group: { id: string; label: string; items: ReactNode[] } | null = null;
  const flush = () => {
    if (group !== null) {
      nodes.push(
        <div key={group.id} role="group" aria-label={group.label} className="logs-actionmenu-group">
          <div className="logs-actionmenu-heading" aria-hidden="true">{group.label}</div>
          {group.items}
        </div>,
      );
      group = null;
    }
  };
  for (const entry of entries) {
    if (entry.kind === "heading") {
      flush();
      group = { id: entry.id, label: entry.label, items: [] };
    } else if (entry.kind === "separator") {
      flush();
      nodes.push(<div key={entry.id} className="logs-menu-sep" role="separator" />);
    } else {
      const tabIndex = entry === firstEnabled ? 0 : -1;
      const node =
        entry.kind === "item" ? (
          <button key={entry.id} type="button" role="menuitem" tabIndex={tabIndex} className="logs-menu-item" disabled={entry.disabled} title={entry.title ?? entry.label} onClick={() => { setOpen(false); entry.onSelect(); }}>
            <span className="ac-ellipsis">{entry.label}</span>
            {entry.hint === undefined ? null : <kbd className="logs-menu-kbd">{entry.hint}</kbd>}
          </button>
        ) : entry.kind === "check" ? (
          <button key={entry.id} type="button" role="menuitemcheckbox" aria-checked={entry.checked} tabIndex={tabIndex} className="logs-menu-item" disabled={entry.disabled} title={entry.label} onClick={() => entry.onChange(!entry.checked)}>
            <span className="logs-menu-mark" aria-hidden="true">{entry.checked ? "✓" : ""}</span>
            <span className="ac-ellipsis">{entry.label}</span>
          </button>
        ) : (
          <button key={entry.id} type="button" role="menuitemradio" aria-checked={entry.checked} tabIndex={tabIndex} className="logs-menu-item" title={entry.label} onClick={entry.onSelect}>
            <span className="logs-menu-mark" aria-hidden="true">{entry.checked ? "●" : ""}</span>
            <span className="ac-ellipsis">{entry.label}</span>
          </button>
        );
      if (group !== null && (entry.kind === "radio" || entry.kind === "check")) group.items.push(node);
      else {
        flush();
        nodes.push(node);
      }
    }
  }
  flush();

  return (
    <Popover
      open={isOpen}
      onOpenChange={setOpen}
      panelRole="menu"
      panelLabel={label}
      align={align}
      panelClassName="logs-actionmenu"
      renderTrigger={(p) => (
        <button {...p} type="button" className={`ac-btn ${triggerClassName ?? ""}`} data-variant={triggerVariant} data-size="sm" aria-label={triggerLabel ?? label} title={triggerTitle ?? triggerLabel ?? label}>
          {trigger}
        </button>
      )}
    >
      <div ref={ref} className="logs-actionmenu-body" onKeyDown={onKeyDown}>
        {nodes}
        {footnote === undefined ? null : <p className="logs-menu-note app-muted">{footnote}</p>}
      </div>
    </Popover>
  );
}
