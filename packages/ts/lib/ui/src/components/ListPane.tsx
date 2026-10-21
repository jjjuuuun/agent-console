import { useId, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { GroupHeader } from "./GroupHeader";
import { joinClass } from "./Status";

export interface ListPaneMessages {
  /** 목록(listbox) 접근성 이름 */
  listLabel: string;
  /** 검색 입력 접근성 이름. `searchValue`를 쓸 때 필요 */
  searchLabel?: string;
  searchPlaceholder?: string;
}

/** 묶음 하나(머리 정의 + 접힘 상태 + 항목). 접힌 묶음의 항목은 그리지 않는다. 하위 묶음 숨김은 호출자가 한다. */
export interface ListPaneGroup<T> {
  key: string;
  label: ReactNode;
  /** 머리 툴팁(전체 경로). */
  title?: string;
  count: number;
  depth: number;
  collapsed: boolean;
  items: readonly T[];
}

export interface ListPaneProps<T> {
  /** 평면 항목. `groups`가 있으면 무시한다(빈 상태 판단도 `groups` 기준). */
  items: readonly T[];
  /** 있으면 묶음 머리와 함께 그린다. 한 항목이 여러 묶음에 있을 수 있고 선택 표시는 모든 사본에 켜진다. */
  groups?: readonly ListPaneGroup<T>[];
  /** 머리 접기·펴기. `collapsed`는 바꾼 뒤의 값. */
  onToggleGroup?: (key: string, collapsed: boolean) => void;
  /** 항목의 고유 id. 기본은 `item.id`. */
  getItemId?: (item: T) => string;
  selectedId?: string;
  onSelect: (id: string, item: T) => void;
  renderItem: (item: T, state: { selected: boolean }) => ReactNode;
  /** 행 최소 높이(px). 기본은 토큰 `--ac-row-h`. */
  rowHeight?: number;
  /** 로딩 중 슬롯(있으면 목록 대신 표시). */
  loading?: ReactNode;
  /** 오류 슬롯(로딩보다 우선). */
  error?: ReactNode;
  /** 항목이 없을 때 슬롯. */
  empty?: ReactNode;
  /** 값이 있으면(빈 문자열 포함) 검색 입력을 보인다. */
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  /** 검색 입력 오른쪽 슬롯(만들기 버튼 등). */
  toolbar?: ReactNode;
  /** 검색 줄 바로 아래에 끼울 줄(보기 메뉴 등). */
  belowTop?: ReactNode;
  /**
   * 묶음 머리에 항목을 끌어 놓을 수 있게 한다(HTML5 drag). 있으면 머리가 드롭 대상이 되고 `dataTransfer`를 그대로 넘긴다.
   * `canDropOnGroup`이 false를 돌려주면 그 머리는 대상이 아니다. 키보드·터치 대안은 호출자가 따로 준다.
   */
  onGroupDrop?: (groupKey: string, data: DataTransfer) => void;
  canDropOnGroup?: (groupKey: string) => boolean;
  messages: ListPaneMessages;
  className?: string;
}

interface NavEntry<T> {
  navKey: string;
  kind: "header" | "row";
  id?: string;
  item?: T;
  group?: ListPaneGroup<T>;
}

function defaultGetId(item: unknown): string {
  return String((item as { id: unknown }).id);
}

/**
 * 마스터 목록 패널(제어형). `role=listbox`, 한 개의 Tab 정지점(roving), `↑↓ Home End`로 포커스 이동,
 * `Enter`/`Space`/클릭으로 선택. 검색 입력에서 `↓`를 누르면 목록으로 이동한다. 크기 조절은 호출자(SplitPane 등)가 한다.
 */
export function ListPane<T>({
  items,
  groups,
  onToggleGroup,
  getItemId = defaultGetId,
  selectedId,
  onSelect,
  renderItem,
  rowHeight,
  loading,
  error,
  empty,
  searchValue,
  onSearchChange,
  toolbar,
  belowTop,
  onGroupDrop,
  canDropOnGroup,
  messages,
  className,
}: ListPaneProps<T>) {
  const base = useId();
  const [dropKey, setDropKey] = useState<string | undefined>(undefined);
  const droppable = (key: string) => onGroupDrop !== undefined && (canDropOnGroup?.(key) ?? true);
  const listRef = useRef<HTMLUListElement>(null);
  const [focusKey, setFocusKey] = useState<string | undefined>(undefined);
  // 이동 순서(머리와 보이는 항목). 평면이면 id가 곧 키다.
  const entries: NavEntry<T>[] = [];
  if (groups === undefined) {
    for (const item of items) {
      const id = getItemId(item);
      entries.push({ navKey: id, kind: "row", id, item });
    }
  } else {
    for (const g of groups) {
      entries.push({ navKey: `h\u001f${g.key}`, kind: "header", group: g });
      if (!g.collapsed) for (const item of g.items) {
        const id = getItemId(item);
        entries.push({ navKey: `r\u001f${g.key}\u001f${id}`, kind: "row", id, item });
      }
    }
  }
  const navKeys = entries.map((e) => e.navKey);
  const tabStop =
    focusKey !== undefined && navKeys.includes(focusKey)
      ? focusKey
      : (entries.find((e) => e.kind === "row" && e.id === selectedId) ?? entries[0])?.navKey;

  const focusEntry = (navKey: string | undefined) => {
    if (navKey === undefined) return;
    setFocusKey(navKey);
    listRef.current?.querySelector<HTMLElement>(`[data-nav-key="${CSS.escape(navKey)}"]`)?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLUListElement>) => {
    const active = (event.target as HTMLElement).closest<HTMLElement>("[data-nav-key]")?.dataset.navKey;
    const index = active === undefined ? -1 : navKeys.indexOf(active);
    if (index < 0) return;
    const entry = entries[index]!;
    if (entry.kind === "header") {
      const g = entry.group!;
      if (event.key === "ArrowLeft" && !g.collapsed) {
        event.preventDefault();
        onToggleGroup?.(g.key, true);
        return;
      }
      if (event.key === "ArrowRight" && g.collapsed) {
        event.preventDefault();
        onToggleGroup?.(g.key, false);
        return;
      }
    }
    let next: number | undefined;
    if (event.key === "ArrowDown") next = Math.min(entries.length - 1, index + 1);
    else if (event.key === "ArrowUp") next = Math.max(0, index - 1);
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = entries.length - 1;
    else if ((event.key === "Enter" || event.key === " ") && entry.kind === "row") {
      event.preventDefault();
      onSelect(entry.id!, entry.item!);
      return;
    }
    if (next === undefined) return;
    event.preventDefault();
    focusEntry(navKeys[next]);
  };

  const renderRow = (e: NavEntry<T>, rowIndex: number) => {
    const id = e.id!;
    const selected = id === selectedId;
    return (
      <li
        key={e.navKey}
        id={`${base}-${rowIndex}`}
        role="option"
        aria-selected={selected}
        data-row-id={id}
        data-nav-key={e.navKey}
        data-selected={selected ? "true" : undefined}
        tabIndex={e.navKey === tabStop ? 0 : -1}
        className="ac-listpane-row"
        style={rowHeight === undefined ? undefined : { minHeight: rowHeight }}
        onFocus={() => setFocusKey(e.navKey)}
        onClick={() => onSelect(id, e.item!)}
      >
        {renderItem(e.item!, { selected })}
      </li>
    );
  };

  const state = error !== undefined ? "error" : loading !== undefined ? "loading" : (groups === undefined ? items.length === 0 : groups.length === 0) ? "empty" : "list";
  const hasSearch = searchValue !== undefined;

  return (
    <div className={joinClass("ac-listpane", className)} data-state={state}>
      {hasSearch || toolbar !== undefined ? (
        <div className="ac-listpane-top">
          {hasSearch ? (
            <input
              type="search"
              className="ac-input ac-listpane-search"
              value={searchValue}
              aria-label={messages.searchLabel}
              placeholder={messages.searchPlaceholder}
              onChange={(e) => onSearchChange?.(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown" && !e.nativeEvent.isComposing && entries.length > 0) {
                  e.preventDefault();
                  focusEntry(tabStop);
                }
              }}
            />
          ) : null}
          {toolbar}
        </div>
      ) : null}
      {belowTop}
      {state === "error" ? (
        <div className="ac-listpane-slot" role="alert">{error}</div>
      ) : state === "loading" ? (
        <div className="ac-listpane-slot" role="status" aria-busy="true">{loading}</div>
      ) : state === "empty" ? (
        <div className="ac-listpane-slot">{empty}</div>
      ) : (
        <ul ref={listRef} role="listbox" aria-label={messages.listLabel} className="ac-listpane-list" onKeyDown={onKeyDown}>
          {groups === undefined
            ? entries.map((e, i) => renderRow(e, i))
            : (() => {
                let rowIndex = 0;
                return groups.map((g, gi) => {
                  const headId = `${base}-h${gi}`;
                  const bodyId = `${base}-g${gi}`;
                  const shown = !g.collapsed && g.items.length > 0;
                  return (
                    <li key={g.key} role="presentation" className="ac-listpane-section" data-collapsed={g.collapsed ? "true" : undefined}>
                      <div
                        role="presentation"
                        className="ac-listpane-grouphead"
                        onDragOver={droppable(g.key) ? (e) => { e.preventDefault(); setDropKey(g.key); } : undefined}
                        onDragLeave={droppable(g.key) ? () => setDropKey((k) => (k === g.key ? undefined : k)) : undefined}
                        onDrop={droppable(g.key) ? (e) => { e.preventDefault(); setDropKey(undefined); onGroupDrop?.(g.key, e.dataTransfer); } : undefined}
                      >
                        <GroupHeader
                          id={headId}
                          label={g.label}
                          title={g.title}
                          count={g.count}
                          depth={g.depth}
                          collapsed={g.collapsed}
                          dropTarget={dropKey === g.key}
                          controlsId={shown ? bodyId : undefined}
                          navKey={`h\u001f${g.key}`}
                          tabIndex={`h\u001f${g.key}` === tabStop ? 0 : -1}
                          onFocus={() => setFocusKey(`h\u001f${g.key}`)}
                          onToggle={() => onToggleGroup?.(g.key, !g.collapsed)}
                        />
                      </div>
                      {shown ? (
                        <ul id={bodyId} role="group" aria-labelledby={headId} className="ac-listpane-group" style={{ "--ac-group-depth": Math.min(g.depth, 3) } as CSSProperties}>
                          {g.items.map((item) => {
                            const id = getItemId(item);
                            return renderRow({ navKey: `r\u001f${g.key}\u001f${id}`, kind: "row", id, item }, rowIndex++);
                          })}
                        </ul>
                      ) : null}
                    </li>
                  );
                });
              })()}
        </ul>
      )}
    </div>
  );
}
