import type { LogDashboard, LogWidget } from "@agent-console/contracts/logs";

export const GRID_COLUMNS = 12;
export const MIN_WIDGET_W = 3;
export const MAX_WIDGET_W = 12;
export const MIN_WIDGET_H = 2;
export const MAX_WIDGET_H = 8;
export const DEFAULT_WIDGET_SIZE = { w: 6, h: 4 } as const;
/** 격자가 예약한 `options` 키. 위젯 `optionsSchema`가 쓰지 않는다. */
export const RESERVED_OPTION_KEYS: readonly string[] = ["w", "h"];

export interface WidgetPlacement {
  id: string;
  col: number;
  row: number;
  w: number;
  h: number;
}

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));
const asInt = (v: unknown): number | undefined => (typeof v === "number" && Number.isFinite(v) ? Math.round(v) : undefined);

/** 위젯 크기(12열 기준, 클램프). 옵션에 없으면 `fallback`(종류 기본 크기), 그것도 없으면 6×4. */
export function widgetSize(widget: Pick<LogWidget, "options">, fallback?: { w: number; h: number }): { w: number; h: number } {
  const o = widget.options ?? {};
  const base = fallback ?? DEFAULT_WIDGET_SIZE;
  return { w: clamp(asInt(o["w"]) ?? base.w, MIN_WIDGET_W, MAX_WIDGET_W), h: clamp(asInt(o["h"]) ?? base.h, MIN_WIDGET_H, MAX_WIDGET_H) };
}

/**
 * 순서 + 크기로 흐름 배치(왼쪽에서 오른쪽, 한 줄이 차면 다음 줄). 좌표는 저장하지 않는다.
 * 6열이면 너비를 `ceil(w/2)`(최소 3)로 줄인다. 줄 높이는 그 줄에서 가장 높은 위젯이다.
 */
export function layoutFlow(widgets: readonly LogWidget[], columns: number = GRID_COLUMNS, sizeOf: (w: LogWidget) => { w: number; h: number } = (w) => widgetSize(w)): WidgetPlacement[] {
  const out: WidgetPlacement[] = [];
  let col = 0;
  let row = 0;
  let lineH = 0;
  for (const widget of widgets) {
    const size = sizeOf(widget);
    const w = clamp(columns === GRID_COLUMNS ? size.w : Math.max(MIN_WIDGET_W, Math.ceil(size.w / 2)), 1, columns);
    if (col + w > columns) {
      row += lineH;
      col = 0;
      lineH = 0;
    }
    out.push({ id: widget.id, col, row, w, h: size.h });
    col += w;
    lineH = Math.max(lineH, size.h);
  }
  return out;
}

/** 위젯을 `toIndex`로 옮긴다(범위 밖은 끝으로 클램프). id가 없으면 같은 배열을 돌려준다. */
export function moveWidget(widgets: readonly LogWidget[], id: string, toIndex: number): LogWidget[] {
  const from = widgets.findIndex((w) => w.id === id);
  if (from < 0) return widgets as LogWidget[];
  const to = clamp(toIndex, 0, widgets.length - 1);
  if (to === from) return widgets as LogWidget[];
  const next = [...widgets];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item as LogWidget);
  return next;
}

/** 크기 변경(클램프). 다른 `options` 키와 다른 위젯은 그대로(같은 객체). */
export function resizeWidget(widgets: readonly LogWidget[], id: string, size: { w?: number; h?: number }, fallback?: { w: number; h: number }): LogWidget[] {
  return widgets.map((widget) => {
    if (widget.id !== id) return widget;
    const cur = widgetSize(widget, fallback);
    return { ...widget, options: { ...(widget.options ?? {}), w: clamp(size.w ?? cur.w, MIN_WIDGET_W, MAX_WIDGET_W), h: clamp(size.h ?? cur.h, MIN_WIDGET_H, MAX_WIDGET_H) } };
  });
}

/** 위젯 하나만 바꾼다. 나머지는 같은 객체. */
export function updateWidget(widgets: readonly LogWidget[], id: string, patch: Partial<LogWidget> | ((w: LogWidget) => LogWidget)): LogWidget[] {
  return widgets.map((w) => (w.id !== id ? w : typeof patch === "function" ? patch(w) : { ...w, ...patch }));
}

export function removeWidget(widgets: readonly LogWidget[], id: string): LogWidget[] {
  return widgets.filter((w) => w.id !== id);
}

/** 복제본을 원본 바로 뒤에 넣는다. 깊은 복사(알 수 없는 키 포함). */
export function duplicateWidget(widgets: readonly LogWidget[], id: string, newId: string): LogWidget[] {
  const i = widgets.findIndex((w) => w.id === id);
  if (i < 0) return widgets as LogWidget[];
  const copy = { ...(structuredClone(widgets[i]) as LogWidget), id: newId };
  return [...widgets.slice(0, i + 1), copy, ...widgets.slice(i + 1)];
}

export interface PreserveOptions {
  /** 편집기가 소유한(지울 수 있는) 옵션 키. 종류별. 나머지 옵션 키는 `prev`에서 이어받는다. `w`·`h`는 항상 소유. */
  ownedOptionKeys?: (kind: string) => readonly string[];
}

const KNOWN_WIDGET_KEYS = new Set(["id", "kind", "title", "query", "options"]);
const KNOWN_QUERY_KEYS = new Set(["group_by", "metric", "filter"]);

/**
 * 저장 직전 안전망: `next`의 위젯에 없는 키 중 `prev`(서버에서 읽은 것)에 있던 알 수 없는 키를 이어받는다.
 * 위젯/질의 수준의 모르는 키, 편집기가 소유하지 않은 옵션 키가 대상이다. 위젯 목록(추가/삭제)은 `next`를 따른다.
 */
export function preserveUnknown(prev: readonly LogWidget[], next: readonly LogWidget[], opts: PreserveOptions = {}): LogWidget[] {
  const before = new Map(prev.map((w) => [w.id, w] as const));
  return next.map((n) => {
    const p = before.get(n.id);
    if (!p) return n;
    const out: Record<string, unknown> = { ...n };
    for (const [k, v] of Object.entries(p)) if (!KNOWN_WIDGET_KEYS.has(k) && !(k in out)) out[k] = v;
    const query: Record<string, unknown> = { ...n.query };
    for (const [k, v] of Object.entries(p.query)) if (!KNOWN_QUERY_KEYS.has(k) && !(k in query)) query[k] = v;
    out["query"] = query;
    const owned = new Set([...RESERVED_OPTION_KEYS, ...(opts.ownedOptionKeys?.(n.kind) ?? [])]);
    const options: Record<string, unknown> = { ...(n.options ?? {}) };
    for (const [k, v] of Object.entries(p.options ?? {})) if (!owned.has(k) && !(k in options)) options[k] = v;
    out["options"] = options;
    return out as unknown as LogWidget;
  });
}

/** 대시보드 수준의 모르는 키 보존(`id`·`title`·`widgets` 외). */
export function preserveUnknownDashboards(prev: readonly LogDashboard[], next: readonly LogDashboard[], opts: PreserveOptions = {}): LogDashboard[] {
  const before = new Map(prev.map((d) => [d.id, d] as const));
  return next.map((n) => {
    const p = before.get(n.id);
    if (!p) return n;
    const out: Record<string, unknown> = { ...n };
    for (const [k, v] of Object.entries(p)) if (!["id", "title", "widgets"].includes(k) && !(k in out)) out[k] = v;
    out["widgets"] = preserveUnknown(p.widgets ?? [], n.widgets ?? [], opts);
    return out as unknown as LogDashboard;
  });
}
