import { Fragment, useEffect, useImperativeHandle, useMemo, useRef, useState, type KeyboardEvent, type ReactNode, type Ref } from "react";
import { fullTimeTitle, mergeFormatters, shortId, shortPath } from "./format";
import { fmt, mergeMessages, type DeepPartial, type LogViewMessages } from "./messages";
import { groupByMessage } from "./group";
import { CategoryChip, ErrorIcon, listStateBlock, NeutralChip } from "./parts";
import { colorFor } from "./taxonomy";
import type { ColumnSpec, Formatters, ListSlots, LogEventRow, LogTaxonomyView, SlotFor } from "./types";
import { useVirtualRows } from "./virtual";

export interface RowMenuAnchor {
  x: number;
  y: number;
  element?: HTMLElement | undefined;
}

/** 표의 명령형 API(`ref`로 받는다). 앱이 DOM을 건드리지 않고 표를 움직이게 한다. */
export interface LogEventTableHandle {
  /**
   * 그 행이 보이게 스크롤한다. 접힌 응답 묶음 안의 행이면 묶음을 펼친다.
   * @returns 현재 `rows`에 없는 uid면 false
   */
  scrollToUid(uid: string, options?: { align?: "auto" | "start" | "center" | "end" }): boolean;
  /** 표(`role="grid"`)에 포커스를 둔다. */
  focus(): void;
}

export interface LogEventTableProps extends ListSlots {
  /** 표의 명령형 API. */
  ref?: Ref<LogEventTableHandle>;
  rows: readonly LogEventRow[];
  columns: readonly ColumnSpec<LogEventRow>[];
  selectedUid?: string | null | undefined;
  onSelect?: (uid: string) => void;
  /** `Enter`로 행을 열려 했을 때(이미 선택된 행이어도 호출). 앱이 상세 패널 첫 탭으로 포커스를 옮길 때 쓴다. */
  onActivate?: (uid: string) => void;
  onRowMenu?: (uid: string, anchor: RowMenuAnchor) => void;
  taxonomy: LogTaxonomyView;
  /** 오류 행 판정(앱이 `isErrorEvent(row, taxonomy)`를 주입. 판정은 한 곳). */
  isError: (row: LogEventRow) => boolean;
  slotFor: SlotFor;
  timeMode?: "relative" | "absolute";
  /** 상대 시각의 기준(epoch 초). */
  originTime?: number | null | undefined;
  /** 같은 응답(thread + message_id) 묶기. */
  groupByMessage?: boolean;
  /** 마지막 행 따라가기. 값을 주면 [현재 위치] 칩과 `onFollowChange`가 켜진다. */
  followLast?: boolean | undefined;
  onFollowChange?: (follow: boolean) => void;
  density?: "dense" | "compact";
  /** 끝에서 `nearEndThreshold`행 이내가 되면 다음 페이지 요청 신호. */
  onNearEnd?: () => void;
  nearEndThreshold?: number;
  loadingMore?: boolean;
  hasMore?: boolean;
  /** 재생 중 현재 위치 행(왼쪽 2px 막대). */
  currentUid?: string | null | undefined;
  highlight?: (row: LogEventRow) => boolean;
  /** 열 id별 셀 덮어쓰기. undefined를 돌려주면 기본 셀. */
  renderCell?: (columnId: string, row: LogEventRow) => ReactNode | undefined;
  /** 레인(thread) 표시 이름. 없으면 id 원문. */
  laneLabelFor?: (thread: string) => string | undefined;
  /** 표 영역 높이(px). 레이아웃을 읽을 수 없을 때의 가상 스크롤 기본 높이도 겸한다. */
  height?: number;
  formatters?: Partial<Formatters>;
  messages?: DeepPartial<LogViewMessages>;
  ariaLabel?: string;
}

interface Item {
  row: LogEventRow;
  depth: number;
  group?: { key: string; size: number; expanded: boolean };
}

const ROW_H: Record<"dense" | "compact", number> = { dense: 32, compact: 40 };

function colWidth(w: number | string): string {
  return typeof w === "number" ? `${w}px` : w;
}

/**
 * 이벤트 표(가상 스크롤, `role="grid"`). 행은 `LogEvent` 그대로이고 범주·단계·상태는 분류 체계·messages로 그린다.
 * 모르는 범주·열은 원문으로 보이며 깨지지 않는다. 키보드: `↑↓ Home End PageUp PageDown` 행 이동, `Enter` 선택,
 * `→/←` 응답 묶음 펼침/접기, `Shift+F10` 행 메뉴.
 */
export function LogEventTable({ ref, ...props }: LogEventTableProps) {
  const { rows, columns, selectedUid, onSelect, onActivate, onRowMenu, taxonomy, isError, slotFor, timeMode = "relative", originTime, followLast, onFollowChange, density = "dense", onNearEnd, nearEndThreshold = 20, loadingMore, hasMore, currentUid, highlight, renderCell, laneLabelFor, height = 480, ariaLabel, messages, formatters: formatterOverrides, groupByMessage: groupMessages, loading, error, onRetry, renderLoading, renderEmpty, renderError } = props;
  const m = useMemo(() => mergeMessages(messages), [messages]);
  const formatters = useMemo(() => mergeFormatters(formatterOverrides), [formatterOverrides]);
  const rowH = ROW_H[density];
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [activeUid, setActiveUid] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);

  const items = useMemo<Item[]>(() => {
    if (!groupMessages) return rows.map((row) => ({ row, depth: 0 }));
    const out: Item[] = [];
    for (const it of groupByMessage(rows)) {
      if (it.kind === "row") {
        out.push({ row: it.row, depth: 0 });
        continue;
      }
      const g = it.group;
      const open = expanded.has(g.key);
      out.push({ row: g.head, depth: 0, group: { key: g.key, size: g.children.length + 1, expanded: open } });
      if (open) for (const c of g.children) out.push({ row: c, depth: 1 });
    }
    return out;
  }, [rows, groupMessages, expanded]);

  const virt = useVirtualRows({ count: items.length, rowHeight: rowH, scrollRef, fallbackHeight: height });

  // 응답 묶음이 접혀 있어 아직 items에 없는 행으로 스크롤하려 할 때, 펼친 뒤 이 uid로 다시 스크롤한다.
  const pendingScroll = useRef<{ uid: string; align: "auto" | "start" | "center" | "end" } | null>(null);
  useImperativeHandle(
    ref,
    () => ({
      scrollToUid(uid, options) {
        const align = options?.align ?? "auto";
        if (!rows.some((r) => r.uid === uid)) return false;
        if (items.some((i) => i.row.uid === uid)) {
          virt.scrollToIndex(items.findIndex((i) => i.row.uid === uid), { align });
          return true;
        }
        const group = groupByMessage(rows).find((g) => g.kind === "group" && g.group.children.some((c) => c.uid === uid));
        if (group?.kind !== "group") return false;
        const key = group.group.key;
        setExpanded((prev) => new Set(prev).add(key));
        pendingScroll.current = { uid, align };
        return true;
      },
      focus() {
        gridRef.current?.focus();
      },
    }),
    [rows, items, virt],
  );
  useEffect(() => {
    const pending = pendingScroll.current;
    if (pending === null) return;
    const i = items.findIndex((it) => it.row.uid === pending.uid);
    if (i < 0) return;
    pendingScroll.current = null;
    virt.scrollToIndex(i, { align: pending.align });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);
  const vItems = virt.getVirtualItems();
  const template = columns.map((c) => colWidth(c.width)).join(" ");

  const activeIndex = Math.max(0, items.findIndex((i) => i.row.uid === (activeUid ?? selectedUid)));
  const activeItem = items[activeIndex];

  // 다음 페이지 신호
  const lastVisible = vItems.length ? (vItems[vItems.length - 1]?.index ?? 0) : -1;
  const nearEnd = items.length > 0 && lastVisible >= items.length - nearEndThreshold;
  const nearEndRef = useRef(false);
  useEffect(() => {
    if (nearEnd && hasMore && !loadingMore && !nearEndRef.current) {
      nearEndRef.current = true;
      onNearEnd?.();
    }
    if (!nearEnd || loadingMore) nearEndRef.current = false;
  }, [nearEnd, hasMore, loadingMore, onNearEnd, items.length]);

  // 따라가기: 켜져 있으면 행이 늘 때 마지막 행이 보이게 한다.
  useEffect(() => {
    if (followLast && items.length > 0) virt.scrollToIndex(items.length - 1, { align: "end" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [followLast, items.length]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el || followLast === undefined || !onFollowChange) return;
    const atEnd = el.scrollTop + el.clientHeight >= el.scrollHeight - rowH * 2;
    if (followLast && !atEnd && el.clientHeight > 0) onFollowChange(false);
  };

  const moveTo = (i: number) => {
    const target = items[Math.min(items.length - 1, Math.max(0, i))];
    if (!target) return;
    setActiveUid(target.row.uid);
    virt.scrollToIndex(Math.min(items.length - 1, Math.max(0, i)));
    if (selectedUid != null) onSelect?.(target.row.uid);
  };

  const toggleGroup = (key: string, open: boolean) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (open) next.add(key);
      else next.delete(key);
      return next;
    });

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const page = Math.max(1, Math.floor(height / rowH) - 1);
    switch (e.key) {
      case "ArrowDown": e.preventDefault(); moveTo(activeIndex + 1); break;
      case "ArrowUp": e.preventDefault(); moveTo(activeIndex - 1); break;
      case "Home": e.preventDefault(); moveTo(0); break;
      case "End": e.preventDefault(); moveTo(items.length - 1); break;
      case "PageDown": e.preventDefault(); moveTo(activeIndex + page); break;
      case "PageUp": e.preventDefault(); moveTo(activeIndex - page); break;
      case "Enter": if (activeItem) { e.preventDefault(); onSelect?.(activeItem.row.uid); onActivate?.(activeItem.row.uid); } break;
      case "ArrowRight": if (activeItem?.group && !activeItem.group.expanded) { e.preventDefault(); toggleGroup(activeItem.group.key, true); } break;
      case "ArrowLeft": if (activeItem?.group?.expanded) { e.preventDefault(); toggleGroup(activeItem.group.key, false); } break;
      case "ContextMenu":
      case "F10":
        if (e.key === "ContextMenu" || e.shiftKey) {
          e.preventDefault();
          if (activeItem) {
            const el = gridRef.current?.querySelector<HTMLElement>(`[data-uid="${CSS.escape(activeItem.row.uid)}"]`) ?? undefined;
            const r = el?.getBoundingClientRect();
            onRowMenu?.(activeItem.row.uid, { x: r?.left ?? 0, y: r?.bottom ?? 0, element: el });
          }
        }
        break;
      default:
    }
  };

  const state = listStateBlock({ loading, error, onRetry, renderLoading, renderEmpty, renderError }, rows.length, m);

  const defaultCell = (col: ColumnSpec<LogEventRow>, row: LogEventRow, item: Item): ReactNode => {
    const custom = renderCell?.(col.id, row);
    if (custom !== undefined) return custom;
    if (col.render) return col.render(row);
    return defaultEventCell(col.id, row, { m, formatters, taxonomy, slotFor, timeMode, originTime, isError, laneLabelFor, item });
  };

  return (
    <div className="ac-lv-table" data-density={density}>
      {state && rows.length === 0 ? (
        state
      ) : (
        <div
          ref={gridRef}
          role="grid"
          tabIndex={0}
          className="ac-lv-grid-table"
          aria-label={ariaLabel ?? m.eventTable}
          aria-rowcount={items.length + 1}
          aria-activedescendant={activeItem ? `lv-row-${activeItem.row.uid}` : undefined}
          onKeyDown={onKeyDown}
        >
          <div role="row" aria-rowindex={1} className="ac-lv-rowhead" style={{ gridTemplateColumns: template }}>
            {columns.map((c) => (
              <div key={c.id} role="columnheader" data-align={c.align ?? "start"} className="ac-lv-ellipsis">
                {c.header}
              </div>
            ))}
          </div>
          <div ref={scrollRef} className="ac-lv-scroll" style={{ height }} onScroll={onScroll}>
            <div style={{ height: virt.getTotalSize(), position: "relative" }}>
              {vItems.map((v) => {
                const item = items[v.index];
                if (!item) return null;
                const { row } = item;
                const err = isError(row);
                const selected = row.uid === selectedUid;
                return (
                  <div
                    key={row.uid}
                    id={`lv-row-${row.uid}`}
                    data-uid={row.uid}
                    role="row"
                    aria-rowindex={v.index + 2}
                    aria-selected={selected}
                    aria-expanded={item.group ? item.group.expanded : undefined}
                    data-error={err || undefined}
                    data-selected={selected || undefined}
                    data-active={row.uid === activeItem?.row.uid || undefined}
                    data-current={row.uid === currentUid || undefined}
                    data-highlight={highlight?.(row) || undefined}
                    data-child={item.depth > 0 || undefined}
                    className="ac-lv-row"
                    style={{ gridTemplateColumns: template, height: rowH, transform: `translateY(${v.start}px)` }}
                    onClick={() => {
                      setActiveUid(row.uid);
                      onSelect?.(row.uid);
                    }}
                    onContextMenu={(e) => {
                      if (!onRowMenu) return;
                      e.preventDefault();
                      onRowMenu(row.uid, { x: e.clientX, y: e.clientY, element: e.currentTarget });
                    }}
                  >
                    {columns.map((c, ci) => (
                      <div key={c.id} role="gridcell" data-align={c.align ?? "start"} className="ac-lv-cell">
                        {ci === 0 && err ? <span className="ac-lv-sr">{m.errorRow}</span> : null}
                        {ci === 0 && item.depth > 0 ? <span className="ac-lv-indent" aria-hidden="true" /> : null}
                        {defaultCell(c, row, item)}
                        {ci === 0 && item.group ? (
                          <button
                            type="button"
                            tabIndex={-1}
                            className="ac-lv-linkbtn"
                            aria-label={item.group.expanded ? m.collapseGroup : m.expandGroup}
                            title={fmt(m.groupBlocks, { n: item.group.size })}
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleGroup(item.group?.key ?? "", !item.group?.expanded);
                            }}
                          >
                            <span aria-hidden="true">{item.group.expanded ? "▾" : "▸"} {item.group.size}</span>
                            <span className="ac-lv-sr">{fmt(m.groupBlocks, { n: item.group.size })}</span>
                          </button>
                        ) : null}
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
          {loadingMore ? (
            <p className="ac-lv-muted" role="status">
              {m.moreLoading}
            </p>
          ) : hasMore === false && rows.length > 0 ? (
            <p className="ac-lv-muted">{m.noMore}</p>
          ) : null}
          {followLast === false && onFollowChange ? (
            <button
              type="button"
              className="ac-lv-btn ac-lv-follow-chip"
              onClick={() => {
                onFollowChange(true);
                virt.scrollToIndex(items.length - 1, { align: "end" });
              }}
            >
              ↓ {m.jumpToCurrent}
            </button>
          ) : null}
        </div>
      )}
      {state && rows.length > 0 ? state : null}
    </div>
  );
}

interface CellCtx {
  m: LogViewMessages;
  formatters: Formatters;
  taxonomy: LogTaxonomyView;
  slotFor: SlotFor;
  timeMode: "relative" | "absolute";
  originTime: number | null | undefined;
  isError: (row: LogEventRow) => boolean;
  laneLabelFor: ((thread: string) => string | undefined) | undefined;
  item: Item;
}

/** 열 id(계약 필드 이름)별 기본 셀. 모르는 열 id는 같은 이름의 필드 원문. */
function defaultEventCell(id: string, row: LogEventRow, c: CellCtx): ReactNode {
  const { m, formatters } = c;
  switch (id) {
    case "time": {
      if (row.time == null) return m.none;
      const text = c.timeMode === "absolute" || c.originTime == null ? formatters.absoluteTime(row.time) : formatters.relativeTime((row.time - c.originTime) * 1000);
      return (
        <span className="ac-lv-num" title={fullTimeTitle(row.time)}>
          {text}
        </span>
      );
    }
    case "lane": {
      const key = row.thread ?? row.actor ?? "";
      if (!key) return m.none;
      const name = c.laneLabelFor?.(key) ?? key;
      return <span className="ac-lv-ellipsis" title={name}>{name}</span>;
    }
    case "category":
      return <CategoryChip name={c.taxonomy.get(row.category).name} color={colorFor(row.category, c.taxonomy, c.slotFor)} title={row.category} />;
    case "title":
      return (
        <Fragment>
          {c.isError(row) ? (
            <>
              <ErrorIcon />
              <NeutralChip>{m.errorBadge}</NeutralChip>
            </>
          ) : null}
          {row.tool ? <span className="ac-lv-chip ac-lv-mono" title={row.call_id ?? row.tool}>{row.tool}</span> : null}
          <span className="ac-lv-ellipsis" title={row.title}>{row.title}</span>
        </Fragment>
      );
    case "duration":
      return row.duration_ms == null ? m.none : <span className="ac-lv-num">{formatters.duration(row.duration_ms)}</span>;
    case "session":
      return row.session ? <span className="ac-lv-mono" title={row.session}>{shortId(row.session)}</span> : m.none;
    case "cwd":
      return row.cwd ? <span className="ac-lv-ellipsis" title={row.cwd}>{shortPath(row.cwd)}</span> : m.none;
    default: {
      const v = (row as unknown as Record<string, unknown>)[id];
      if (v == null || v === "") return m.none;
      const text = typeof v === "object" ? JSON.stringify(v) : String(v);
      return <span className="ac-lv-ellipsis" title={text}>{text}</span>;
    }
  }
}

/** 기본 열 정의(열 id 목록 -> ColumnSpec). 머리글은 messages.columns, 모르는 id는 id 원문. 폭 표는 `widths`로 덮어쓴다. */
export function eventColumns(ids: readonly string[], messages?: DeepPartial<LogViewMessages>, widths: Readonly<Record<string, number | string>> = {}): ColumnSpec<LogEventRow>[] {
  const m = mergeMessages(messages);
  const base: Record<string, number | string> = { time: 104, lane: 120, category: 120, title: "minmax(0,2fr)", duration: 72, summary: "minmax(0,2fr)", session: 96 };
  return ids.map((id) => ({ id, header: m.columns[id] ?? id, width: widths[id] ?? base[id] ?? "minmax(0,1fr)", align: id === "duration" ? "end" : "start" }));
}
