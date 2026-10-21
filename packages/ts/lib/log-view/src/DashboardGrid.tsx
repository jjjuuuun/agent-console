import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type KeyboardEvent, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import type { LogAggregateRow, LogDimensionInfo, LogMetricInfo, LogWidget } from "@agent-console/contracts/logs";
import { mergeFormatters } from "./format";
import { fmt, mergeMessages, type DeepPartial, type LogViewMessages } from "./messages";
import { duplicateWidget, GRID_COLUMNS, layoutFlow, moveWidget, removeWidget, resizeWidget, widgetSize, MAX_WIDGET_H, MAX_WIDGET_W, MIN_WIDGET_H, MIN_WIDGET_W } from "./layout";
import { AggregateTable } from "./widgets/AggregateTable";
import type { WidgetDescriptor, WidgetRegistry } from "./widgets/registry";
import { UnknownWidget } from "./widgets/UnknownWidget";
import type { Formatters, SlotFor } from "./types";
import { Skeleton } from "./parts";

export interface WidgetResult {
  rows?: readonly LogAggregateRow[] | undefined;
  loading: boolean;
  error?: { message: string; code?: string; detail?: string } | null | undefined;
  /** 마지막 갱신 시각(epoch ms). */
  updatedAt?: number | undefined;
}

export type DashboardChangeReason = "move" | "resize" | "remove" | "duplicate";
export interface DashboardChangeMeta {
  reason: DashboardChangeReason;
  id: string;
}

export interface DashboardGridProps {
  widgets: readonly LogWidget[];
  registry: WidgetRegistry;
  results: Readonly<Record<string, WidgetResult | undefined>>;
  editing?: boolean;
  /** 순서·크기·삭제·복제 변경은 모두 여기로. 알 수 없는 키는 보존된다. */
  onChange?: (next: LogWidget[], meta: DashboardChangeMeta) => void;
  onEditWidget?: (id: string) => void;
  onRefreshWidget?: (id: string) => void;
  /** 위젯이 처음 화면에 보일 때 한 번(집계 요청을 미루는 용도). */
  onVisible?: (id: string) => void;
  /** 알 수 없는 위젯의 [JSON으로 편집]. */
  onEditWidgetJson?: (widget: LogWidget) => void;
  /** 열 수. 12(기본) 또는 6(좁은 화면). */
  columns?: number;
  rowHeight?: number;
  gap?: number;
  /** 서버 스키마(있으면 지표 단위·제목 표시에 쓴다). */
  metrics?: readonly LogMetricInfo[];
  dimensions?: readonly LogDimensionInfo[];
  /** 복제본 id 생성(앱이 UUID 주입). */
  newId?: () => string;
  /** 현재 시각(ms, 주입). */
  now?: () => number;
  slotFor: SlotFor;
  formatters?: Partial<Formatters>;
  /** 마지막에 놓는 [+ 위젯 추가] 카드 등. */
  addCard?: ReactNode;
  messages?: DeepPartial<LogViewMessages>;
  ariaLabel?: string;
}

function agoText(ms: number, m: LogViewMessages): string {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s}${m.units.s}`;
  if (s < 3600) return `${Math.floor(s / 60)}${m.units.m}`;
  return `${Math.floor(s / 3600)}${m.units.h}`;
}

/** 위젯 제목: 위젯 `title` -> 종류 제목 + 지표 이름 -> 안내 문구. */
function widgetTitle(w: LogWidget, d: WidgetDescriptor | undefined, metric: string, m: LogViewMessages): string {
  if (w.title?.trim()) return w.title;
  if (d) return `${d.title} · ${metric}`;
  return m.widgetUntitled;
}

/**
 * 대시보드 격자: 순서 + `options.w`·`h`로 흐르는 12열(좁으면 6열) 배치. 좌표를 저장하지 않는다.
 * 순서 변경은 드래그(손잡이)와 `Ctrl+↑↓`, 크기는 `Shift+방향키`와 모서리 손잡이, 삭제 `Delete`, 복제 `Ctrl+D`.
 * 모르는 종류는 `UnknownWidget`으로 그리고 설정은 그대로 둔다. 이 컴포넌트는 데이터를 가져오지 않는다.
 */
export function DashboardGrid(props: DashboardGridProps) {
  const { widgets, registry, results, editing = false, onChange, onEditWidget, onRefreshWidget, onVisible, onEditWidgetJson, columns = GRID_COLUMNS, rowHeight = 80, gap = 12, metrics, newId, slotFor, addCard, ariaLabel } = props;
  const m = useMemo(() => mergeMessages(props.messages), [props.messages]);
  const formatters = useMemo(() => mergeFormatters(props.formatters), [props.formatters]);
  const now = props.now ?? Date.now;
  const placements = useMemo(() => layoutFlow(widgets, columns, (w) => widgetSize(w, registry.get(w.kind)?.defaultSize)), [widgets, columns, registry]);
  const placementById = useMemo(() => new Map(placements.map((p) => [p.id, p])), [placements]);
  const [tableIds, setTableIds] = useState<ReadonlySet<string>>(new Set());
  const [dragId, setDragId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  const cardRefs = useRef(new Map<string, HTMLElement>());
  const gridRef = useRef<HTMLDivElement>(null);
  const [focusId, setFocusId] = useState<string | null>(null);

  const emit = useCallback((next: LogWidget[], meta: DashboardChangeMeta) => onChange?.(next, meta), [onChange]);
  const fallbackFor = useCallback((w: LogWidget) => registry.get(w.kind)?.defaultSize, [registry]);

  // 포커스 복귀: 순서 이동·삭제 뒤 대상 카드에 포커스를 유지한다.
  useEffect(() => {
    if (focusId) cardRefs.current.get(focusId)?.focus();
  }, [focusId, widgets]);

  const toggleTable = (id: string) =>
    setTableIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const neighbor = (id: string, dir: "left" | "right" | "up" | "down"): string | undefined => {
    const cur = placementById.get(id);
    if (!cur) return undefined;
    let best: { id: string; score: number } | undefined;
    for (const p of placements) {
      if (p.id === id) continue;
      const dx = p.col - cur.col;
      const dy = p.row - cur.row;
      const ok = dir === "left" ? dx < 0 && dy === 0 : dir === "right" ? dx > 0 && dy === 0 : dir === "up" ? dy < 0 : dy > 0;
      if (!ok) continue;
      const score = dir === "left" || dir === "right" ? Math.abs(dx) : Math.abs(dy) * 100 + Math.abs(dx);
      if (!best || score < best.score) best = { id: p.id, score };
    }
    return best?.id;
  };

  const onCardKey = (e: KeyboardEvent<HTMLElement>, w: LogWidget) => {
    if (e.target !== e.currentTarget) return; // 카드 안 버튼의 키는 가로채지 않는다
    const idx = widgets.findIndex((x) => x.id === w.id);
    const dirs: Record<string, "left" | "right" | "up" | "down"> = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" };
    const dir = dirs[e.key];
    if (!editing) {
      if (e.key === "Enter" && registry.get(w.kind)?.tableToggle !== false && registry.has(w.kind)) {
        e.preventDefault();
        toggleTable(w.id);
      } else if (dir) {
        const n = neighbor(w.id, dir);
        if (n) {
          e.preventDefault();
          cardRefs.current.get(n)?.focus();
        }
      }
      return;
    }
    if (e.ctrlKey && dir && (dir === "up" || dir === "down")) {
      e.preventDefault();
      setFocusId(w.id);
      emit(moveWidget(widgets, w.id, idx + (dir === "up" ? -1 : 1)), { reason: "move", id: w.id });
    } else if (e.shiftKey && dir) {
      e.preventDefault();
      const cur = widgetSize(w, fallbackFor(w));
      const patch = dir === "left" ? { w: cur.w - 1 } : dir === "right" ? { w: cur.w + 1 } : dir === "up" ? { h: cur.h - 1 } : { h: cur.h + 1 };
      emit(resizeWidget(widgets, w.id, patch, fallbackFor(w)), { reason: "resize", id: w.id });
    } else if (dir && !e.ctrlKey && !e.altKey) {
      const n = neighbor(w.id, dir);
      if (n) {
        e.preventDefault();
        cardRefs.current.get(n)?.focus();
      }
    } else if (e.key === "Enter") {
      e.preventDefault();
      onEditWidget?.(w.id);
    } else if (e.key === "Delete") {
      e.preventDefault();
      const next = widgets[idx + 1] ?? widgets[idx - 1];
      setFocusId(next?.id ?? null);
      emit(removeWidget(widgets, w.id), { reason: "remove", id: w.id });
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "d") {
      e.preventDefault();
      const id = newId?.() ?? `${w.id}-copy`;
      setFocusId(id);
      emit(duplicateWidget(widgets, w.id, id), { reason: "duplicate", id });
    }
  };

  const onDrop = (e: DragEvent, targetId: string) => {
    e.preventDefault();
    const src = dragId ?? e.dataTransfer.getData("text/plain");
    setDragId(null);
    setOverId(null);
    if (!src || src === targetId) return;
    const to = widgets.findIndex((w) => w.id === targetId);
    if (to >= 0) emit(moveWidget(widgets, src, to), { reason: "move", id: src });
  };

  // 모서리 손잡이: 포인터 이동량을 열·행 칸으로 환산해 스냅한다.
  const startResize = (e: ReactPointerEvent<HTMLElement>, w: LogWidget) => {
    e.preventDefault();
    const grid = gridRef.current;
    if (!grid) return;
    const colW = (grid.clientWidth - gap * (columns - 1)) / columns;
    const start = { x: e.clientX, y: e.clientY, size: widgetSize(w, fallbackFor(w)) };
    const target = e.currentTarget;
    target.setPointerCapture?.(e.pointerId);
    const factor = columns === GRID_COLUMNS ? 1 : 2;
    const move = (ev: PointerEvent) => {
      const dw = Math.round((ev.clientX - start.x) / (colW + gap)) * factor;
      const dh = Math.round((ev.clientY - start.y) / (rowHeight + gap));
      const next = { w: Math.min(MAX_WIDGET_W, Math.max(MIN_WIDGET_W, start.size.w + dw)), h: Math.min(MAX_WIDGET_H, Math.max(MIN_WIDGET_H, start.size.h + dh)) };
      const cur = widgetSize(w, fallbackFor(w));
      if (next.w !== cur.w || next.h !== cur.h) emit(resizeWidget(widgets, w.id, next, fallbackFor(w)), { reason: "resize", id: w.id });
    };
    const up = () => {
      target.removeEventListener("pointermove", move);
      target.removeEventListener("pointerup", up);
    };
    target.addEventListener("pointermove", move);
    target.addEventListener("pointerup", up);
  };

  return (
    <div
      ref={gridRef}
      className="ac-lv-grid"
      role="group"
      aria-label={ariaLabel ?? m.dashboard}
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`, gridAutoRows: `${rowHeight}px`, gap }}
    >
      {widgets.map((w) => {
        const place = placementById.get(w.id);
        if (!place) return null;
        const d = registry.get(w.kind);
        const res = results[w.id];
        const metricInfo = metrics?.find((x) => x.id === w.query.metric);
        const metricName = metricInfo?.title ?? metricInfo?.id ?? w.query.metric;
        const title = widgetTitle(w, d, metricName, m);
        const tableMode = tableIds.has(w.id);
        return (
          <WidgetCard
            key={w.id}
            widget={w}
            descriptor={d}
            result={res}
            title={title}
            editing={editing}
            tableMode={tableMode}
            style={{ gridColumn: `${place.col + 1} / span ${place.w}`, gridRow: `${place.row + 1} / span ${place.h}` }}
            size={widgetSize(w, d?.defaultSize)}
            metric={metricInfo}
            m={m}
            formatters={formatters}
            slotFor={slotFor}
            updatedText={res?.updatedAt != null ? fmt(m.widgetUpdated, { ago: agoText(now() - res.updatedAt, m) }) : undefined}
            dropTarget={overId === w.id && dragId !== w.id}
            registerRef={(el) => {
              if (el) cardRefs.current.set(w.id, el);
              else cardRefs.current.delete(w.id);
            }}
            onKeyDown={(e) => onCardKey(e, w)}
            onToggleTable={() => toggleTable(w.id)}
            onRefresh={onRefreshWidget ? () => onRefreshWidget(w.id) : undefined}
            onEdit={onEditWidget ? () => onEditWidget(w.id) : undefined}
            onRemove={() => emit(removeWidget(widgets, w.id), { reason: "remove", id: w.id })}
            onDuplicate={() => emit(duplicateWidget(widgets, w.id, newId?.() ?? `${w.id}-copy`), { reason: "duplicate", id: w.id })}
            onVisible={d && onVisible ? () => onVisible(w.id) : undefined}
            onEditJson={onEditWidgetJson}
            onDragStart={(e) => {
              setDragId(w.id);
              e.dataTransfer.setData("text/plain", w.id);
              e.dataTransfer.effectAllowed = "move";
            }}
            onDragEnd={() => {
              setDragId(null);
              setOverId(null);
            }}
            onDragOver={(e) => {
              if (!dragId) return;
              e.preventDefault();
              setOverId(w.id);
            }}
            onDrop={(e) => onDrop(e, w.id)}
            onResizeStart={(e) => startResize(e, w)}
          />
        );
      })}
      {addCard ? (
        <div className="ac-lv-addcard" style={{ gridColumn: "span 3", gridRow: "span 2" }}>
          {addCard}
        </div>
      ) : null}
    </div>
  );
}

interface CardProps {
  widget: LogWidget;
  descriptor: WidgetDescriptor | undefined;
  result: WidgetResult | undefined;
  title: string;
  editing: boolean;
  tableMode: boolean;
  style: React.CSSProperties;
  size: { w: number; h: number };
  metric: LogMetricInfo | undefined;
  m: LogViewMessages;
  formatters: Formatters;
  slotFor: SlotFor;
  updatedText: string | undefined;
  dropTarget: boolean;
  registerRef: (el: HTMLElement | null) => void;
  onKeyDown: (e: KeyboardEvent<HTMLElement>) => void;
  onToggleTable: () => void;
  onRefresh: (() => void) | undefined;
  onEdit: (() => void) | undefined;
  onRemove: () => void;
  onDuplicate: () => void;
  onVisible: (() => void) | undefined;
  onEditJson: ((w: LogWidget) => void) | undefined;
  onDragStart: (e: DragEvent) => void;
  onDragEnd: () => void;
  onDragOver: (e: DragEvent) => void;
  onDrop: (e: DragEvent) => void;
  onResizeStart: (e: ReactPointerEvent<HTMLElement>) => void;
}

function WidgetCard(p: CardProps) {
  const { widget: w, descriptor: d, result: res, m } = p;
  const ref = useRef<HTMLElement | null>(null);
  const seen = useRef(false);
  const { onVisible, registerRef } = p;

  useEffect(() => {
    const el = ref.current;
    registerRef(el);
    return () => registerRef(null);
  }, [registerRef]);

  // 처음 화면에 보일 때 한 번만 알린다. IntersectionObserver가 없는 환경이면 바로 알린다.
  const onVisibleRef = useRef(onVisible);
  useEffect(() => {
    onVisibleRef.current = onVisible;
  });
  const wantsVisible = onVisible !== undefined;
  useEffect(() => {
    if (!wantsVisible || seen.current) return;
    const fire = () => {
      if (seen.current) return;
      seen.current = true;
      onVisibleRef.current?.();
    };
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") {
      fire();
      return;
    }
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        fire();
        io.disconnect();
      }
    });
    io.observe(el);
    return () => io.disconnect();
  }, [wantsVisible]);

  const groupBy = w.query.group_by ?? [];
  let body: ReactNode;
  if (!d) {
    body = <UnknownWidget widget={w} editing={p.editing} onEditJson={p.onEditJson} onRemove={p.onRemove} messages={m} />;
  } else if (res?.error) {
    body = (
      <div className="ac-lv-error" role="alert">
        <span className="ac-lv-clamp2">{res.error.code === "validation_failed" ? fmt(m.widgetInvalid, { message: res.error.message }) : res.error.message}</span>
        {p.onRefresh ? (
          <button type="button" className="ac-lv-btn" onClick={p.onRefresh}>
            {m.retry}
          </button>
        ) : null}
      </div>
    );
  } else if (!res || (res.loading && !res.rows)) {
    body = <Skeleton label={m.loading} />;
  } else if (!res.rows || res.rows.length === 0) {
    body = (
      <div className="ac-lv-empty" role="status">
        <p>{m.widgetNoData}</p>
        <p className="ac-lv-muted">{m.widgetNoDataHint}</p>
      </div>
    );
  } else {
    const props = { widget: w, rows: res.rows, loading: res.loading, error: null, options: w.options ?? {}, groupBy, size: p.size, tableMode: p.tableMode, metric: p.metric, title: p.title, messages: m, formatters: p.formatters, slotFor: p.slotFor };
    body = p.tableMode ? (
      <AggregateTable
        rows={res.rows}
        groupBy={groupBy}
        metricLabel={p.metric?.title ?? p.metric?.id ?? w.query.metric}
        columns={d.tableColumns?.(res.rows, props)}
        ariaLabel={p.title}
        messages={m}
        formatters={p.formatters}
      />
    ) : (
      d.render(props)
    );
  }

  return (
    <section
      ref={(el) => {
        ref.current = el;
      }}
      className="ac-lv-card"
      data-editing={p.editing || undefined}
      data-drop-target={p.dropTarget || undefined}
      data-widget-id={w.id}
      data-kind={w.kind}
      style={p.style}
      tabIndex={0}
      aria-label={p.title}
      onKeyDown={p.onKeyDown}
      onDragOver={p.onDragOver}
      onDrop={p.onDrop}
    >
      <header className="ac-lv-cardhead">
        {p.editing ? (
          <span className="ac-lv-handle" draggable onDragStart={p.onDragStart} onDragEnd={p.onDragEnd} title={m.widgetMove} aria-label={m.widgetMove} role="img">
            ⠿
          </span>
        ) : null}
        <h3 className="ac-lv-ellipsis" title={p.title}>
          {p.title}
        </h3>
        {p.updatedText ? <span className="ac-lv-muted ac-lv-num">{p.updatedText}</span> : null}
        {res?.loading && res.rows ? <span className="ac-lv-spinner" role="status" aria-label={m.loading} /> : null}
        {d && p.onRefresh ? (
          <button type="button" className="ac-lv-iconbtn" onClick={p.onRefresh} aria-label={m.widgetRefresh} title={m.widgetRefresh}>
            ⟳
          </button>
        ) : null}
        {p.editing ? (
          <>
            {p.onEdit ? (
              <button type="button" className="ac-lv-iconbtn" onClick={p.onEdit} aria-label={m.widgetEdit} title={m.widgetEdit}>
                ⚙
              </button>
            ) : null}
            <button type="button" className="ac-lv-iconbtn" onClick={p.onDuplicate} aria-label={m.widgetDuplicate} title={m.widgetDuplicate}>
              ⧉
            </button>
            <button type="button" className="ac-lv-iconbtn" onClick={p.onRemove} aria-label={m.widgetRemove} title={m.widgetRemove}>
              ✕
            </button>
          </>
        ) : null}
      </header>
      <div className="ac-lv-cardbody">{body}</div>
      {d && d.tableToggle !== false && res?.rows && res.rows.length > 0 && !res.error ? (
        <footer className="ac-lv-cardfoot">
          <button type="button" className="ac-lv-linkbtn" aria-pressed={p.tableMode} onClick={p.onToggleTable}>
            {p.tableMode ? m.widgetShowChart : m.widgetShowTable}
          </button>
        </footer>
      ) : null}
      {p.editing ? <span className="ac-lv-resize" onPointerDown={p.onResizeStart} aria-hidden="true" /> : null}
    </section>
  );
}
