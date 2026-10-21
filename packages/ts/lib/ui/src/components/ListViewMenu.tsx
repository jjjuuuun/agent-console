import { useId, useState, type KeyboardEvent } from "react";
import { IconButton } from "./Button";
import { Icon } from "./Icon";
import { Popover } from "./Popover";
import { joinClass } from "./Status";

/** 보기 메뉴의 선택지 하나(묶는 기준 또는 정렬). 문구는 호출자가 이미 해석해 넘긴다. */
export interface ListViewOption {
  id: string;
  label: string;
  /** true면 `aria-disabled`로 두고 고를 수 없다. 사유를 `reason`으로 보인다. */
  disabled?: boolean;
  reason?: string;
  /** 선택됐을 때 아래에 보이는 입력(예: 속성 키). */
  input?: ListViewOptionInput;
}

export interface ListViewOptionInput {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /** 자동완성 후보. */
  suggestions?: readonly string[];
}

export interface ListViewMenuMessages {
  /** 트리거·메뉴 접근성 이름(예: "보기"). */
  menuLabel: string;
  groupTitle: string;
  sortTitle: string;
  collapseAll: string;
  expandAll: string;
}

export interface ListViewMenuProps {
  /** 트리거 글자(예: "폴더별 · 이름순"). */
  summary: string;
  /** 묶는 기준 선택지. "묶지 않음"도 호출자가 항목(예: id `""`)으로 넣는다. */
  groupOptions: readonly ListViewOption[];
  groupBy: string;
  onGroupByChange: (id: string) => void;
  sortOptions: readonly ListViewOption[];
  sort: string;
  onSortChange: (id: string) => void;
  /** 묶음이 있을 때만 넘긴다. 둘 다 있으면 메뉴 아래쪽과 옆 단추에 "모두 접기/펼치기"가 생긴다. */
  onCollapseAll?: () => void;
  onExpandAll?: () => void;
  /** 하나라도 접혀 있으면 true: 옆 단추가 "모두 펼치기"로 바뀐다. */
  anyCollapsed?: boolean;
  /** 제어형 열림(단축키 `G` 등으로 열 때). 생략하면 내부 상태. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  messages: ListViewMenuMessages;
  className?: string;
}

const ITEM = '[role="menuitemradio"],[role="menuitem"]';

/**
 * 목록 "보기" 메뉴(묶는 기준·정렬·모두 접기/펼치기). 표현 전용: 선택은 즉시 콜백으로 알리고 메뉴는 열어 둔다.
 * `↑↓ Home End`로 이동, Space/Enter 선택, Esc·바깥 클릭으로 닫으면 트리거로 포커스가 돌아간다.
 */
export function ListViewMenu({
  summary, groupOptions, groupBy, onGroupByChange, sortOptions, sort, onSortChange,
  onCollapseAll, onExpandAll, anyCollapsed = false, open: openProp, onOpenChange, messages, className,
}: ListViewMenuProps) {
  const [innerOpen, setInnerOpen] = useState(false);
  const open = openProp ?? innerOpen;
  const setOpen = (value: boolean) => {
    if (openProp === undefined) setInnerOpen(value);
    onOpenChange?.(value);
  };
  const hasCollapse = onCollapseAll !== undefined && onExpandAll !== undefined;

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.nativeEvent.isComposing) return;
    const items = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(ITEM));
    const index = items.indexOf(document.activeElement as HTMLElement);
    const inInput = (event.target as HTMLElement).tagName === "INPUT";
    let next: number | undefined;
    if (event.key === "ArrowDown") next = index < 0 ? 0 : Math.min(items.length - 1, index + 1);
    else if (event.key === "ArrowUp") next = index < 0 ? 0 : Math.max(0, index - 1);
    else if (!inInput && event.key === "Home") next = 0;
    else if (!inInput && event.key === "End") next = items.length - 1;
    if (next === undefined || items.length === 0) return;
    event.preventDefault();
    items[next]?.focus();
  };

  return (
    <span className={joinClass("ac-listview", className)}>
      <Popover
        open={open}
        onOpenChange={setOpen}
        panelRole="menu"
        panelLabel={messages.menuLabel}
        panelClassName="ac-listview-panel"
        renderTrigger={(trigger) => (
          <button {...trigger} type="button" className="ac-listview-trigger" title={messages.menuLabel}>
            <span className="ac-listview-summary ac-ellipsis">{summary}</span>
            <Icon name="chevron-down" size={12} />
          </button>
        )}
      >
        {(
          <div className="ac-listview-body" onKeyDown={onKeyDown}>
            <OptionGroup title={messages.groupTitle} options={groupOptions} value={groupBy} onChange={onGroupByChange} entryTab />
            <OptionGroup title={messages.sortTitle} options={sortOptions} value={sort} onChange={onSortChange} />
            {hasCollapse ? (
              <div role="group" aria-label={messages.menuLabel} className="ac-listview-actions">
                <button type="button" role="menuitem" tabIndex={-1} className="ac-listview-item" onClick={() => onCollapseAll()}>{messages.collapseAll}</button>
                <button type="button" role="menuitem" tabIndex={-1} className="ac-listview-item" onClick={() => onExpandAll()}>{messages.expandAll}</button>
              </div>
            ) : null}
          </div>
        )}
      </Popover>
      {hasCollapse ? (
        <IconButton
          size="sm"
          className="ac-listview-collapse"
          data-expand={anyCollapsed ? "true" : undefined}
          label={anyCollapsed ? messages.expandAll : messages.collapseAll}
          icon={<Icon name="chevron-down" size={14} />}
          onClick={anyCollapsed ? onExpandAll : onCollapseAll}
        />
      ) : null}
    </span>
  );
}

function OptionGroup({ title, options, value, onChange, entryTab = false }: {
  title: string;
  options: readonly ListViewOption[];
  value: string;
  onChange: (id: string) => void;
  /** 이 그룹의 선택 항목을 메뉴의 진입 tab 정지점으로 삼는다. */
  entryTab?: boolean;
}) {
  const base = useId();
  const headId = `${base}-t`;
  return (
    <div role="group" aria-labelledby={headId} className="ac-listview-section">
      <div id={headId} className="ac-listview-title">{title}</div>
      {options.map((o) => {
        const checked = o.id === value;
        const reasonId = o.reason === undefined ? undefined : `${base}-r-${o.id}`;
        return (
          <div key={o.id} className="ac-listview-option">
            <button
              type="button"
              role="menuitemradio"
              aria-checked={checked}
              aria-disabled={o.disabled ? true : undefined}
              aria-describedby={o.disabled ? reasonId : undefined}
              tabIndex={entryTab && checked ? 0 : -1}
              className="ac-listview-item"
              onClick={() => {
                if (!o.disabled) onChange(o.id);
              }}
            >
              <span className="ac-listview-radio" aria-hidden="true" data-checked={checked ? "true" : undefined} />
              <span className="ac-ellipsis">{o.label}</span>
            </button>
            {o.disabled && o.reason !== undefined ? <div id={reasonId} className="ac-listview-reason">{o.reason}</div> : null}
            {checked && o.input !== undefined ? <OptionInput input={o.input} /> : null}
          </div>
        );
      })}
    </div>
  );
}

function OptionInput({ input }: { input: ListViewOptionInput }) {
  const listId = useId();
  return (
    <div className="ac-listview-input">
      <input
        className="ac-input"
        aria-label={input.label}
        placeholder={input.placeholder}
        value={input.value}
        list={input.suggestions === undefined ? undefined : listId}
        onChange={(e) => input.onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === " ") e.stopPropagation();
        }}
      />
      {input.suggestions === undefined ? null : <datalist id={listId}>{input.suggestions.map((s) => <option key={s} value={s} />)}</datalist>}
    </div>
  );
}
