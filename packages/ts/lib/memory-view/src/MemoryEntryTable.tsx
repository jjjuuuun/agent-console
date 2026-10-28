import type { MemoryEntrySummary, MemoryScopeRef } from "@agent-console/contracts/memory";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { formatBytes, formatRelativeTime, formatTimestamp, nextSort, orderText, type SortState } from "./format";
import { useElementWidth, useNowSeconds, useVirtualRows } from "./hooks";
import { formatMessage, resolveMessages } from "./messages";
import { formatAuthor, type FormatAuthorOptions } from "./scopes";

/** 표 열 id. 고정·키·쓴 주체·수정·크기·버전은 항상 있고 태그는 폭이 넉넉할 때만 더해진다. */
export type EntryColumnId = "pin" | "key" | "author" | "updated" | "size" | "version" | "tags";

/** 열 폭(px). 키 열은 나머지(최소 `KEY_COLUMN_MIN`). */
export const COLUMN_WIDTHS = { pin: 28, author: 120, updated: 72, size: 64, version: 44, tags: 140 } as const;
export const KEY_COLUMN_MIN = 160;
/** 표 폭이 이 값 이상이면 태그 열이 더해진다(열을 숨기는 쪽이 아니라 더하는 쪽). */
export const TAGS_COLUMN_MIN_WIDTH = 720;
/** 행 높이: 한 범위를 보고 검색어가 없으면 32, 아니면 52(둘째 줄). */
export const ROW_HEIGHT_COMPACT = 32;
export const ROW_HEIGHT_TALL = 52;

/** 표 폭에서 보이는 열. 앞 6열은 폭이 모자라도 사라지지 않는다. */
export function tableColumns(width: number): EntryColumnId[] {
  const base: EntryColumnId[] = ["pin", "key", "author", "updated", "size", "version"];
  return width >= TAGS_COLUMN_MIN_WIDTH ? [...base, "tags"] : base;
}

export function tableRowHeight(tall: boolean): number {
  return tall ? ROW_HEIGHT_TALL : ROW_HEIGHT_COMPACT;
}

export interface MemoryEntryTableProps {
  /** 서버 순서 그대로(클라이언트 정렬 없음). */
  entries: readonly MemoryEntrySummary[];
  /** 서버가 아는 전체 수. 모르면 null/생략. */
  total?: number | null;
  /** 다음 쪽이 있다. 끝에서 5행 앞이면 `onLoadMore`를 부른다. */
  hasMore?: boolean;
  loading?: boolean;
  onLoadMore?: () => void;
  selectedId?: string | null;
  onSelect?: (entry: MemoryEntrySummary) => void;
  /** Enter: 상세 열고 편집기로 포커스. */
  onOpen?: (entry: MemoryEntrySummary) => void;
  /** `N` 키. */
  onNew?: () => void;
  /** `Delete`(표시 삭제)·`Shift+Delete`(완전 삭제 확인). */
  onDelete?: (entry: MemoryEntrySummary) => void;
  onPurge?: (entry: MemoryEntrySummary) => void;
  /** `Shift+F10`·ContextMenu 키. */
  onContextMenu?: (entry: MemoryEntrySummary, anchor: HTMLElement) => void;
  /** 검색어가 있으면 행이 52가 되고 둘째 줄에 미리보기를 쓴다. */
  query?: string;
  /** 여러 범위가 섞여 보이는 상태(모든 범위). 둘째 줄에 범위 라벨을 쓰고 행이 52가 된다. */
  showScope?: boolean;
  /** 범위 라벨 글. */
  scopeText?: (scope: MemoryScopeRef) => string;
  /** 알 수 없는 범위 종류의 범위인지(모든 범위 보기에서 키 뒤 아이콘). */
  isUnknownKind?: (scope: MemoryScopeRef) => boolean;
  authorOptions?: FormatAuthorOptions;
  /** 지금 시각(Unix epoch 초). 테스트·SSR 고정용, 기본은 현재. */
  now?: number;
  /** 표 폭을 직접 정한다(레이아웃이 없는 환경·테스트). 생략하면 요소 폭을 관찰한다. */
  width?: number;
  /** 실시간 갱신으로 바뀐 행 id(강조 1.5초는 CSS, `prefers-reduced-motion`이면 없음). */
  changedIds?: ReadonlySet<string>;
  /** 정렬 가능한 열 → 서버 정렬 값(`MEMORY_ENTRY_SORTS`). 생략하면 머리는 글자만(누를 수 없다). */
  sortKeys?: Partial<Record<EntryColumnId, string>>;
  /** 지금 정렬. null/생략 = 서버 기본 순서. */
  sort?: SortState | null;
  /** 머리를 누르면 다음 정렬(desc → asc → 기본 null)을 알린다. 앱이 URL에 반영하고 커서를 버린다. */
  onSortChange?: (next: SortState | null) => void;
  messages?: Readonly<Record<string, string>>;
  /** 표 위쪽 오류/빈 상태 등을 대신 그린다. */
  emptyContent?: React.ReactNode;
  className?: string;
}

/**
 * 항목 표(가상 목록). 열은 폭이 줄어도 숨기지 않고 키 열만 줄어든다. role="grid", 행마다 탭 정지점 하나(roving tabindex).
 * ↑↓ Home/End PageUp/PageDown 이동, Enter 열기, Space 선택만, N 새 항목, Delete 지우기, Shift+Delete 완전 삭제, Shift+F10 행 메뉴.
 */
export function MemoryEntryTable({
  entries, total = null, hasMore = false, loading = false, onLoadMore, selectedId = null, onSelect, onOpen, onNew, onDelete, onPurge, onContextMenu,
  query = "", showScope = false, scopeText, isUnknownKind, authorOptions, now, width, changedIds, sortKeys, sort, onSortChange, messages: custom, emptyContent, className,
}: MemoryEntryTableProps) {
  const m = resolveMessages(custom);
  const scrollRef = useRef<HTMLDivElement>(null);
  const measured = useElementWidth(scrollRef, 560);
  const tableWidth = width ?? measured;
  const columns = tableColumns(tableWidth);
  const hasTags = columns.includes("tags");
  const tall = query.trim() !== "" || showScope;
  const rowHeight = tableRowHeight(tall);
  const [focusIndex, setFocusIndex] = useState(0);
  const clampedFocus = Math.min(focusIndex, Math.max(0, entries.length - 1));
  const virtual = useVirtualRows({ count: entries.length, rowHeight, scrollRef, keepIndex: entries.length > 0 ? clampedFocus : null });
  const items = virtual.getVirtualItems();
  const nowSec = useNowSeconds(now);

  // 선택한 항목이 보이는 위치로(행 높이가 바뀌거나 선택이 바뀔 때).
  const selectedIndex = useMemo(() => (selectedId === null ? -1 : entries.findIndex((e) => e.id === selectedId)), [entries, selectedId]);
  useEffect(() => {
    if (selectedIndex >= 0) virtual.scrollToIndex(selectedIndex, { align: "auto" });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 행 높이가 바뀔 때만 다시 맞춘다
  }, [tall]);

  const lastIndex = items.length > 0 ? (items[items.length - 1] as { index: number }).index : -1;
  useEffect(() => {
    if (hasMore && !loading && onLoadMore && entries.length > 0 && lastIndex >= entries.length - 5) onLoadMore();
  }, [hasMore, loading, onLoadMore, entries.length, lastIndex]);

  const gridTemplate = [`${COLUMN_WIDTHS.pin}px`, `minmax(${KEY_COLUMN_MIN}px, 1fr)`, `${COLUMN_WIDTHS.author}px`, `${COLUMN_WIDTHS.updated}px`, `${COLUMN_WIDTHS.size}px`, `${COLUMN_WIDTHS.version}px`, ...(hasTags ? [`${COLUMN_WIDTHS.tags}px`] : [])].join(" ");
  const minWidth = COLUMN_WIDTHS.pin + KEY_COLUMN_MIN + COLUMN_WIDTHS.author + COLUMN_WIDTHS.updated + COLUMN_WIDTHS.size + COLUMN_WIDTHS.version + (hasTags ? COLUMN_WIDTHS.tags : 0);

  const focusRow = (index: number) => {
    const i = Math.max(0, Math.min(entries.length - 1, index));
    setFocusIndex(i);
    virtual.scrollToIndex(i, { align: "auto" });
    queueMicrotask(() => scrollRef.current?.querySelector<HTMLElement>(`[data-index="${i}"]`)?.focus());
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const row = (e.target as HTMLElement).closest<HTMLElement>("[data-index]");
    if (!row || e.target !== row) {
      return;
    }
    const idx = Number(row.dataset["index"]);
    const entry = entries[idx];
    if (!entry) return;
    const page = Math.max(1, Math.floor((scrollRef.current?.clientHeight || 480) / rowHeight) - 1);
    switch (e.key) {
      case "ArrowDown": e.preventDefault(); focusRow(idx + 1); break;
      case "ArrowUp": e.preventDefault(); focusRow(idx - 1); break;
      case "Home": e.preventDefault(); focusRow(0); break;
      case "End": e.preventDefault(); focusRow(entries.length - 1); break;
      case "PageDown": e.preventDefault(); focusRow(idx + page); break;
      case "PageUp": e.preventDefault(); focusRow(idx - page); break;
      case "Enter": e.preventDefault(); onSelect?.(entry); onOpen?.(entry); break;
      case " ": e.preventDefault(); onSelect?.(entry); break;
      case "Delete": if (e.shiftKey) onPurge?.(entry); else onDelete?.(entry); if (onDelete || onPurge) e.preventDefault(); break;
      case "ContextMenu": e.preventDefault(); onContextMenu?.(entry, row); break;
      case "F10": if (e.shiftKey) { e.preventDefault(); onContextMenu?.(entry, row); } break;
      case "n": case "N": if (!e.ctrlKey && !e.metaKey && !e.altKey && onNew) { e.preventDefault(); onNew(); } break;
      default:
    }
  };

  const rowCount = total ?? (hasMore ? -1 : entries.length);
  const summaryText = hasMore && total === null
    ? formatMessage(m["table.summaryMore"] as string, { n: entries.length })
    : formatMessage(m["table.summary"] as string, { n: total ?? entries.length });
  const order = query.trim() !== "" ? m["table.order.result"] : orderText(sort, m);

  const headerCell = (id: EntryColumnId, label: React.ReactNode, align: "left" | "right" | "center" = "left") => {
    const sortKey = sortKeys?.[id];
    const active = sortKey !== undefined && sort?.key === sortKey;
    return (
      <div role="columnheader" className="ac-mem-th" data-align={align} aria-sort={active ? (sort?.order === "asc" ? "ascending" : "descending") : undefined}>
        {sortKey !== undefined && onSortChange ? (
          <button type="button" className="ac-mem-linkbtn ac-mem-th-btn" onClick={() => onSortChange(nextSort(sort ?? null, sortKey))}>{label}{active ? <span aria-hidden="true">{sort?.order === "asc" ? " ▲" : " ▼"}</span> : null}</button>
        ) : (
          label
        )}
      </div>
    );
  };

  return (
    <div className={`ac-mem-root ac-mem-table${className ? ` ${className}` : ""}`}>
      <div ref={scrollRef} className="ac-mem-table-scroll" data-tall={tall ? "" : undefined}>
        <div role="grid" aria-label={m["a11y.table"]} aria-rowcount={rowCount < 0 ? -1 : rowCount + 1} aria-colcount={columns.length} onKeyDown={onKeyDown}
          className="ac-mem-grid" style={{ minWidth, ["--ac-mem-cols" as string]: gridTemplate }}>
          <div role="row" aria-rowindex={1} className="ac-mem-thead">
            {headerCell("pin", <><span className="ac-mem-sr">{m["table.pinned"]}</span><span className="ac-mem-icon ac-mem-icon-pin" aria-hidden="true" /></>, "center")}
            {headerCell("key", m["table.key"] as string)}
            {headerCell("author", m["table.author"] as string)}
            {headerCell("updated", m["table.updated"] as string, "right")}
            {headerCell("size", m["table.size"] as string, "right")}
            {headerCell("version", m["table.version"] as string, "right")}
            {hasTags ? headerCell("tags", m["table.tags"] as string) : null}
          </div>
          <div role="rowgroup" className="ac-mem-tbody" style={{ height: virtual.getTotalSize() }}>
            {items.map((vi) => {
              const entry = entries[vi.index];
              if (!entry) return null;
              const author = formatAuthor(entry.updated_by, authorOptions);
              const deleted = entry.deleted_at !== null && entry.deleted_at !== undefined;
              const archived = entry.archived === true;
              const pinned = entry.pinned === true;
              const selected = entry.id === selectedId;
              const parts = entry.key.split("/");
              const last = parts[parts.length - 1] ?? entry.key;
              const head = parts.slice(0, -1).join("/");
              const tags = entry.tags ?? [];
              const scopeLine = showScope && scopeText ? scopeText(entry.scope) : null;
              const unknownKind = showScope && isUnknownKind?.(entry.scope) === true;
              const updated = formatRelativeTime(entry.updated_at, nowSec, m);
              const size = formatBytes(entry.bytes, m);
              const pieces: string[] = [
                formatMessage(m["a11y.row"] as string, { key: entry.key, author: author.text, updated, size, version: `${entry.version}` }),
              ];
              if (pinned) pieces.push(m["a11y.pinned"] as string);
              if (archived) pieces.push(m["a11y.archived"] as string);
              if (deleted) pieces.push(m["a11y.deleted"] as string);
              const tip = [scopeLine, entry.key, !hasTags && tags.length > 0 ? tags.join(", ") : null].filter(Boolean).join("\n");
              return (
                <div key={entry.id} role="row" aria-rowindex={vi.index + 2} aria-selected={selected} aria-label={pieces.join(", ")} data-index={vi.index}
                  data-selected={selected ? "" : undefined} data-archived={archived ? "" : undefined} data-deleted={deleted ? "" : undefined}
                  data-changed={changedIds?.has(entry.id) ? "" : undefined} tabIndex={vi.index === clampedFocus ? 0 : -1} className="ac-mem-tr"
                  style={{ height: vi.size, transform: `translateY(${vi.start}px)` }}
                  onClick={() => { setFocusIndex(vi.index); onSelect?.(entry); }}>
                  <div role="gridcell" className="ac-mem-td ac-mem-td-pin" data-align="center">
                    {pinned ? <span className="ac-mem-icon ac-mem-icon-pin" role="img" aria-label={m["a11y.pinned"]} title={m["a11y.pinned"]} /> : null}
                  </div>
                  <div role="gridcell" className="ac-mem-td ac-mem-td-key" title={tip}>
                    <div className="ac-mem-keyline">
                      <span className="ac-mem-key ac-ellipsis" data-struck={deleted ? "" : undefined}>
                        {head ? <span className="ac-mem-key-head">{head}/</span> : null}
                        <span className="ac-mem-key-last">{last}</span>
                      </span>
                      {archived ? <span className="ac-mem-chip">{m["row.archived"]}</span> : null}
                      {deleted ? <span className="ac-mem-chip">{m["row.deleted"]}</span> : null}
                      {unknownKind ? <span className="ac-mem-icon ac-mem-icon-unknown" role="img" aria-label={m["row.unknownKind"]} title={m["row.unknownKind"]} /> : null}
                    </div>
                    {tall ? (
                      <div className="ac-mem-subline ac-ellipsis">
                        {query.trim() !== "" ? (entry.preview ?? "") : scopeLine}
                        {query.trim() !== "" && scopeLine ? <span className="ac-mem-subline-scope">{scopeLine}</span> : null}
                      </div>
                    ) : null}
                  </div>
                  <div role="gridcell" className="ac-mem-td ac-mem-td-author" title={author.tooltip}>
                    {author.avatar ? (
                      <span className="ac-mem-avatar" aria-hidden="true" style={{ background: `var(--ac-cat-${author.avatar.slot})` }}>{author.avatar.initial}</span>
                    ) : null}
                    <span className={`ac-ellipsis${author.chip ? " ac-mem-chip" : ""}${author.mono ? " ac-mem-mono" : ""}`}>{author.text}</span>
                    {author.ruleId ? <span className="ac-mem-mono ac-ellipsis">{author.ruleId}</span> : null}
                  </div>
                  <div role="gridcell" className="ac-mem-td ac-mem-num" title={formatTimestamp(entry.updated_at)} data-align="right">{updated}</div>
                  <div role="gridcell" className="ac-mem-td ac-mem-num" title={`${entry.bytes} B`} data-align="right">{size}</div>
                  <div role="gridcell" className="ac-mem-td ac-mem-num" data-align="right">v{entry.version}</div>
                  {hasTags ? (
                    <div role="gridcell" className="ac-mem-td ac-mem-td-tags" title={tags.join(", ")}>
                      {tags.slice(0, 2).map((t) => <span key={t} className="ac-mem-chip ac-ellipsis">{t}</span>)}
                      {tags.length > 2 ? <span className="ac-mem-chip">{formatMessage(m["table.moreTags"] as string, { n: tags.length - 2 })}</span> : null}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
          {entries.length === 0 && !loading ? emptyContent ?? <div className="ac-mem-empty">{m["table.empty"]}</div> : null}
        </div>
      </div>
      <div className="ac-mem-statusline" role="status">
        {loading ? <span>{m["table.loading"]}</span> : <span>{summaryText} · {order}</span>}
      </div>
    </div>
  );
}
