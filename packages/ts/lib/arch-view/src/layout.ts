/**
 * 좌표·꺾은선·칩·겹침 검사 순수 함수(docs/design/screen-architecture.md §9).
 * 칸 좌표는 중심, 영역 좌표는 왼쪽 위, `points`는 이미 경계 6px 바깥 값이다.
 * 이 파일은 DOM·React를 모른다.
 */
import type { ArchitectureCellView, ArchitectureEdgeView, ArchitectureView } from "@agent-console/contracts/architecture";
import { METRIC_COUNT, METRIC_ERRORS } from "./defaults";
import type { ArchFitMode, Pt, Rect } from "./types";

/** 연결이 칸 경계에서 떨어지는 거리(points가 없는 연결에만 적용한다). */
export const EDGE_GAP = 6;
/** 칩 높이·좌우 안쪽 여백(`--ac-arch-chip-h`와 같은 값, 겹침 계산용). */
export const CHIP_H = 20;
export const CHIP_PAD_X = 8;
export const CHIP_MAX_W = 120;
const DEFAULT_CELL_W = 180;
const DEFAULT_CELL_H = 68;

// ---------------------------------------------------------------- 칸 위치

export interface GridOptions {
  /** 한 줄에 놓을 칸 수. 생략하면 캔버스 폭에서 계산(캔버스가 없으면 4). */
  cols?: number;
  gapX?: number;
  gapY?: number;
  margin?: number;
}

/** 칸 사각형(왼쪽 위 기준). 좌표가 없으면 null. */
export function cellRectOf(cell: Pick<ArchitectureCellView, "x" | "y" | "w" | "h">): Rect | null {
  if (cell.x === null || cell.x === undefined || cell.y === null || cell.y === undefined) return null;
  const w = cell.w > 0 ? cell.w : DEFAULT_CELL_W;
  const h = cell.h > 0 ? cell.h : DEFAULT_CELL_H;
  return { x: cell.x - w / 2, y: cell.y - h / 2, w, h };
}

/**
 * 모든 칸의 사각형을 돌려준다. 좌표가 있는 칸은 그대로(중심 → 왼쪽 위), 없는 칸은 선언 순서대로 격자에 놓는다.
 * 격자는 좌표가 있는 칸 아래에서 시작해 겹치지 않는다.
 */
export function gridLayout(view: Pick<ArchitectureView, "cells" | "canvas">, options: GridOptions = {}): Record<string, Rect> {
  const cells = view.cells ?? [];
  const gapX = options.gapX ?? 40;
  const gapY = options.gapY ?? 32;
  const margin = options.margin ?? 40;
  const out: Record<string, Rect> = {};
  const missing: ArchitectureCellView[] = [];
  let bottom = -Infinity;
  for (const c of cells) {
    const r = cellRectOf(c);
    if (r) {
      out[c.id] = r;
      bottom = Math.max(bottom, r.y + r.h);
    } else missing.push(c);
  }
  if (missing.length === 0) return out;
  const colW = Math.max(...missing.map((c) => (c.w > 0 ? c.w : DEFAULT_CELL_W))) + gapX;
  const rowH = Math.max(...missing.map((c) => (c.h > 0 ? c.h : DEFAULT_CELL_H))) + gapY;
  const cw = view.canvas?.width;
  const cols = Math.max(1, options.cols ?? (cw ? Math.floor((cw - 2 * margin + gapX) / colW) : 4));
  const top = Number.isFinite(bottom) ? bottom + gapY : margin;
  missing.forEach((c, i) => {
    const w = c.w > 0 ? c.w : DEFAULT_CELL_W;
    const h = c.h > 0 ? c.h : DEFAULT_CELL_H;
    out[c.id] = { x: margin + (i % cols) * colW, y: top + Math.floor(i / cols) * rowH, w, h };
  });
  return out;
}

/** 그림이 차지하는 크기. `canvas`가 있으면 그 값, 없으면 칸·영역·연결을 모두 덮는 크기. */
export function canvasSize(view: Pick<ArchitectureView, "canvas" | "cells" | "zones" | "edges">, rects: Record<string, Rect>): { width: number; height: number } {
  if (view.canvas && view.canvas.width > 0 && view.canvas.height > 0) return { width: view.canvas.width, height: view.canvas.height };
  let w = 0;
  let h = 0;
  for (const r of Object.values(rects)) {
    w = Math.max(w, r.x + r.w);
    h = Math.max(h, r.y + r.h);
  }
  for (const z of view.zones ?? []) {
    w = Math.max(w, z.x + z.w);
    h = Math.max(h, z.y + z.h);
  }
  for (const e of view.edges ?? []) for (const p of e.points ?? []) {
    w = Math.max(w, p[0]);
    h = Math.max(h, p[1]);
  }
  return { width: w + 40, height: h + 40 };
}

// ---------------------------------------------------------------- 연결 경로

export const rectCenter = (r: Rect): Pt => [r.x + r.w / 2, r.y + r.h / 2];

/**
 * 연결의 꺾은선. `points`가 두 점 이상이면 그대로(이미 경계 6px 바깥이므로 다시 더하지 않는다),
 * 없으면 두 칸 중심을 잇는 직선이 경계를 지나는 점에서 6px 바깥으로 시작·끝낸다.
 * 한쪽 칸의 사각형을 모르면 빈 배열.
 */
export function edgePath(points: ReadonlyArray<Pt> | null | undefined, from?: Rect | null, to?: Rect | null, gap: number = EDGE_GAP): Pt[] {
  if (points && points.length >= 2) return points.map((p) => [p[0], p[1]] as Pt);
  if (!from || !to) return [];
  const a = rectCenter(from);
  const b = rectCenter(to);
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy);
  if (len === 0) return [];
  const ux = dx / len;
  const uy = dy / len;
  const exit = (r: Rect, sx: number, sy: number): number => {
    const tx = sx !== 0 ? r.w / 2 / Math.abs(sx) : Infinity;
    const ty = sy !== 0 ? r.h / 2 / Math.abs(sy) : Infinity;
    return Math.min(tx, ty);
  };
  const t1 = exit(from, ux, uy) + gap;
  const t2 = exit(to, ux, uy) + gap;
  if (t1 + t2 >= len) return [];
  return [[a[0] + ux * t1, a[1] + uy * t1], [b[0] - ux * t2, b[1] - uy * t2]];
}

/** SVG path `d` 문자열(직각 꺾임, 모서리 반경 0). */
export function pathData(points: ReadonlyArray<Pt>): string {
  return points.map((p, i) => `${i === 0 ? "M" : "L"}${p[0]} ${p[1]}`).join(" ");
}

export function polylineLength(points: ReadonlyArray<Pt>): number {
  let s = 0;
  for (let i = 1; i < points.length; i++) s += Math.hypot((points[i] as Pt)[0] - (points[i - 1] as Pt)[0], (points[i] as Pt)[1] - (points[i - 1] as Pt)[1]);
  return s;
}

/** 꺾은선 길이의 가운데 점(`label_at`이 없을 때 칩 중심). */
export function polylineMidpoint(points: ReadonlyArray<Pt>): Pt {
  if (points.length === 0) return [0, 0];
  let remain = polylineLength(points) / 2;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1] as Pt;
    const b = points[i] as Pt;
    const l = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (remain <= l && l > 0) return [a[0] + ((b[0] - a[0]) * remain) / l, a[1] + ((b[1] - a[1]) * remain) / l];
    remain -= l;
  }
  return points[points.length - 1] as Pt;
}

/** 칩 중심: `label_at` 우선, 없으면 선 가운데. */
export function chipCenter(edge: Pick<ArchitectureEdgeView, "label_at">, points: ReadonlyArray<Pt>): Pt {
  return edge.label_at ? [edge.label_at[0], edge.label_at[1]] : polylineMidpoint(points);
}

/** 점에 가장 가까운 선분(직선 구간)의 길이와 방향. */
export function segmentAt(points: ReadonlyArray<Pt>, at: Pt): { length: number; horizontal: boolean } {
  let best = { length: 0, horizontal: true };
  let bestD = Infinity;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1] as Pt;
    const b = points[i] as Pt;
    const d = distPointSegment(at, a, b);
    if (d < bestD) {
      bestD = d;
      best = { length: Math.hypot(b[0] - a[0], b[1] - a[1]), horizontal: Math.abs(b[0] - a[0]) >= Math.abs(b[1] - a[1]) };
    }
  }
  return best;
}

// ---------------------------------------------------------------- 칩 폭

/** 글자 폭 추정(px). 한글·전각은 1em, 그 밖은 0.6em. DOM 없이 계산하려는 근사다. */
export function estimateTextWidth(text: string, fontPx = 12): number {
  let w = 0;
  for (const ch of text) w += ch.codePointAt(0)! >= 0x1100 ? fontPx : ch === " " ? fontPx * 0.3 : fontPx * 0.6;
  return w;
}

/**
 * 칩 폭 상한. 가로 선분 위의 칩은 `선분 길이 − 28`도 넘지 못한다(화살촉 여유). 세로 선분 위의 칩은 선분 길이와 무관하다.
 */
export function chipWidthCap(segment: { length: number; horizontal: boolean }, labelMaxW?: number | null): number {
  const caps = [CHIP_MAX_W];
  if (segment.horizontal) caps.push(segment.length - 28);
  if (labelMaxW && labelMaxW > 0) caps.push(labelMaxW);
  return Math.max(CHIP_H, Math.min(...caps));
}

export interface ChipContent {
  label: string;
  /** 횟수(전체 표기). 없으면 칩에 횟수 자리가 없다. */
  count?: string;
  /** 횟수 약식(`12.4k`). */
  countShort?: string;
  /** 오류 수 글자(없으면 오류 조각 없음). */
  errors?: string;
}
export interface ChipFit {
  count?: string;
  /** 오류를 아이콘만 보이는가. */
  errorsIconOnly: boolean;
  errors?: string;
  /** 라벨이 말줄임 대상인가. */
  labelClipped: boolean;
  /** 추정 폭(상한을 넘지 않는다). */
  width: number;
}

/** 오류 조각의 아이콘 폭. */
const ICON_W = 12;
const GAP = 4;

/**
 * 폭 규칙(§2.3): 상한을 넘으면 횟수 약식 → 오류 조각을 아이콘만으로 → 라벨 말줄임 순으로 줄인다.
 * @param measure 글자 폭 측정 함수(기본은 `estimateTextWidth`)
 */
export function fitChip(content: ChipContent, maxW: number, measure: (t: string) => number = (t) => estimateTextWidth(t)): ChipFit {
  const widthOf = (count: string | undefined, errors: string | undefined, iconOnly: boolean, label: string): number => {
    let w = 2 * CHIP_PAD_X + measure(label);
    if (count) w += GAP + measure(count);
    if (errors !== undefined) w += GAP + ICON_W + (iconOnly ? 0 : GAP + measure(errors));
    return w;
  };
  let count = content.count;
  let iconOnly = false;
  if (widthOf(count, content.errors, iconOnly, content.label) > maxW && content.countShort) count = content.countShort;
  if (widthOf(count, content.errors, iconOnly, content.label) > maxW && content.errors !== undefined) iconOnly = true;
  const full = widthOf(count, content.errors, iconOnly, content.label);
  return { count, errors: content.errors, errorsIconOnly: iconOnly, labelClipped: full > maxW, width: Math.min(full, maxW) };
}

// ---------------------------------------------------------------- 기하

function cross(o: Pt, a: Pt, b: Pt): number {
  return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
}
function onSeg(a: Pt, b: Pt, p: Pt): boolean {
  return Math.min(a[0], b[0]) <= p[0] && p[0] <= Math.max(a[0], b[0]) && Math.min(a[1], b[1]) <= p[1] && p[1] <= Math.max(a[1], b[1]);
}
/** 두 선분이 만나는가(끝점이 닿거나 겹치는 경우 포함). */
export function segmentsIntersect(a: Pt, b: Pt, c: Pt, d: Pt): boolean {
  const d1 = cross(c, d, a);
  const d2 = cross(c, d, b);
  const d3 = cross(a, b, c);
  const d4 = cross(a, b, d);
  if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) return true;
  return (d1 === 0 && onSeg(c, d, a)) || (d2 === 0 && onSeg(c, d, b)) || (d3 === 0 && onSeg(a, b, c)) || (d4 === 0 && onSeg(a, b, d));
}
function pointInRect(p: Pt, r: Rect): boolean {
  return p[0] >= r.x && p[0] <= r.x + r.w && p[1] >= r.y && p[1] <= r.y + r.h;
}
/** 선분이 사각형(경계 포함)과 만나는가. */
export function segmentHitsRect(a: Pt, b: Pt, r: Rect): boolean {
  if (pointInRect(a, r) || pointInRect(b, r)) return true;
  const tl: Pt = [r.x, r.y];
  const tr: Pt = [r.x + r.w, r.y];
  const br: Pt = [r.x + r.w, r.y + r.h];
  const bl: Pt = [r.x, r.y + r.h];
  return segmentsIntersect(a, b, tl, tr) || segmentsIntersect(a, b, tr, br) || segmentsIntersect(a, b, br, bl) || segmentsIntersect(a, b, bl, tl);
}
/** 두 사각형이 겹치는가(맞닿기만 하면 겹침이 아니다). */
export function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}
function distPointSegment(p: Pt, a: Pt, b: Pt): number {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const l2 = dx * dx + dy * dy;
  const t = l2 === 0 ? 0 : Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2));
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}
/** 점과 사각형(채워진) 사이 거리. 안쪽이면 0. */
export function distanceToRect(p: Pt, r: Rect): number {
  const dx = Math.max(r.x - p[0], 0, p[0] - (r.x + r.w));
  const dy = Math.max(r.y - p[1], 0, p[1] - (r.y + r.h));
  return Math.hypot(dx, dy);
}

// ---------------------------------------------------------------- checkLayout

export type LayoutIssueKind = "cell-cell" | "edge-cell" | "edge-edge" | "chip-chip" | "chip-cell" | "chip-edge";
export interface LayoutIssue {
  kind: LayoutIssueKind;
  /** 겹친 두 대상의 id(칸 id 또는 연결 id). */
  a: string;
  b: string;
}
export interface CheckLayoutOptions {
  measure?: (text: string) => number;
  /** 칩에 들어갈 횟수 자리의 최대 글자(값을 모를 때의 추정). 기본 "0,000". */
  countPlaceholder?: string;
}

/** 연결에 칩 글자(라벨 + 횟수 + 오류)가 들어갈지 보는 데이터. 지표 이름이 없으면 라벨만. */
function chipContentFor(edge: ArchitectureEdgeView, placeholder: string): ChipContent {
  const m = edge.metrics ?? {};
  const hasCount = METRIC_COUNT in m && edge.kind === "observed";
  const hasErrors = METRIC_ERRORS in m && edge.kind === "observed";
  return { label: edge.label ?? "", count: hasCount ? placeholder : undefined, countShort: hasCount ? "0k" : undefined, errors: hasErrors ? "오류 0" : undefined };
}

/**
 * 좌표만으로 겹침·교차를 센다(칸–칸, 연결–칸, 연결–연결, 칩–칩, 칩–칸, 칩–다른 연결). 빈 배열이면 문제 없음.
 * 칩 크기는 글자 폭 추정과 폭 규칙으로 계산한다. 설정 › 구조도의 배치 미리보기도 같은 함수를 쓴다.
 */
export function checkLayout(view: Pick<ArchitectureView, "cells" | "edges" | "canvas">, options: CheckLayoutOptions = {}): LayoutIssue[] {
  const issues: LayoutIssue[] = [];
  const cells = view.cells ?? [];
  const edges = view.edges ?? [];
  const rects = gridLayout(view);
  const placeholder = options.countPlaceholder ?? "0,000";

  for (let i = 0; i < cells.length; i++) for (let j = i + 1; j < cells.length; j++) {
    const a = cells[i] as ArchitectureCellView;
    const b = cells[j] as ArchitectureCellView;
    if (rectsOverlap(rects[a.id] as Rect, rects[b.id] as Rect)) issues.push({ kind: "cell-cell", a: a.id, b: b.id });
  }

  const paths = edges.map((e) => edgePath(e.points, rects[e.from], rects[e.to]));
  const chips = edges.map((e, i) => {
    const pts = paths[i] as Pt[];
    if (pts.length < 2 || !(e.label || e.metrics)) return null;
    const center = chipCenter(e, pts);
    const cap = chipWidthCap(segmentAt(pts, center), e.label_max_w);
    const fit = fitChip(chipContentFor(e, placeholder), cap, options.measure);
    return { id: e.id, rect: { x: center[0] - fit.width / 2, y: center[1] - CHIP_H / 2, w: fit.width, h: CHIP_H } as Rect };
  });

  edges.forEach((e, i) => {
    const pts = paths[i] as Pt[];
    for (const c of cells) {
      const r = rects[c.id] as Rect;
      for (let k = 1; k < pts.length; k++) if (segmentHitsRect(pts[k - 1] as Pt, pts[k] as Pt, r)) { issues.push({ kind: "edge-cell", a: e.id, b: c.id }); break; }
    }
    for (let j = i + 1; j < edges.length; j++) {
      const other = paths[j] as Pt[];
      let hit = false;
      for (let k = 1; k < pts.length && !hit; k++) for (let l = 1; l < other.length; l++) if (segmentsIntersect(pts[k - 1] as Pt, pts[k] as Pt, other[l - 1] as Pt, other[l] as Pt)) { hit = true; break; }
      if (hit) issues.push({ kind: "edge-edge", a: e.id, b: (edges[j] as ArchitectureEdgeView).id });
    }
  });

  chips.forEach((chip, i) => {
    if (!chip) return;
    for (let j = i + 1; j < chips.length; j++) {
      const o = chips[j];
      if (o && rectsOverlap(chip.rect, o.rect)) issues.push({ kind: "chip-chip", a: chip.id, b: o.id });
    }
    for (const c of cells) if (rectsOverlap(chip.rect, rects[c.id] as Rect)) issues.push({ kind: "chip-cell", a: chip.id, b: c.id });
    edges.forEach((e, j) => {
      if (j === i) return;
      const pts = paths[j] as Pt[];
      for (let k = 1; k < pts.length; k++) if (segmentHitsRect(pts[k - 1] as Pt, pts[k] as Pt, chip.rect)) { issues.push({ kind: "chip-edge", a: chip.id, b: e.id }); break; }
    });
  });
  return issues;
}

// ---------------------------------------------------------------- 확대·이동

export interface Viewport {
  x: number;
  y: number;
  zoom: number;
}
export interface Size {
  width: number;
  height: number;
}
export interface FitOptions {
  /** 바깥 여백(§4.2: 16). */
  margin?: number;
  minZoom?: number;
  maxZoom?: number;
  /** `width` 맞춤의 배율 하한(§4.2: 0.6). */
  widthFloor?: number;
}
export const MIN_ZOOM = 0.25;
export const MAX_ZOOM = 2;
export const VIEW_MARGIN = 16;

export const clampZoom = (z: number, min = MIN_ZOOM, max = MAX_ZOOM): number => Math.min(max, Math.max(min, z));

/**
 * 맞춤 모드에 따른 뷰포트. `width`는 폭에 맞추되 하한(기본 0.6)을 지킨다(넘치면 가로 스크롤),
 * `contain`은 전체가 보이게 하고 하한이 없다. 컨테이너 크기를 모르면(0) 배율 1.
 */
export function fitViewport(mode: Exclude<ArchFitMode, "none">, canvas: Size, container: Size, options: FitOptions = {}): Viewport {
  const m = options.margin ?? VIEW_MARGIN;
  const min = options.minZoom ?? MIN_ZOOM;
  const max = options.maxZoom ?? MAX_ZOOM;
  if (container.width <= 0 || container.height <= 0 || canvas.width <= 0 || canvas.height <= 0) return { x: m, y: m, zoom: 1 };
  const zw = (container.width - 2 * m) / canvas.width;
  if (mode === "width") return { x: m, y: m, zoom: clampZoom(Math.max(options.widthFloor ?? 0.6, zw), min, max) };
  const zh = (container.height - 2 * m) / canvas.height;
  const zoom = clampZoom(Math.min(zw, zh), min, max);
  return { x: Math.max(m, (container.width - canvas.width * zoom) / 2), y: Math.max(m, (container.height - canvas.height * zoom) / 2), zoom };
}

/** `focus`(화면 좌표)를 고정한 채 배율을 바꾼다. */
export function zoomAround(v: Viewport, zoom: number, focus: { x: number; y: number }, min = MIN_ZOOM, max = MAX_ZOOM): Viewport {
  const z = clampZoom(zoom, min, max);
  const k = z / v.zoom;
  return { zoom: z, x: focus.x - (focus.x - v.x) * k, y: focus.y - (focus.y - v.y) * k };
}

/** 사각형(캔버스 좌표)이 화면에 다 보이도록 **최소한**만 옮긴다. 이미 보이면 null. */
export function ensureVisible(rect: Rect, v: Viewport, container: Size, margin = VIEW_MARGIN): Viewport | null {
  if (container.width <= 0 || container.height <= 0) return null;
  const left = rect.x * v.zoom + v.x;
  const top = rect.y * v.zoom + v.y;
  const right = left + rect.w * v.zoom;
  const bottom = top + rect.h * v.zoom;
  let dx = 0;
  let dy = 0;
  if (left < margin) dx = margin - left;
  else if (right > container.width - margin) dx = container.width - margin - right;
  if (rect.w * v.zoom > container.width - 2 * margin) dx = margin - left;
  if (top < margin) dy = margin - top;
  else if (bottom > container.height - margin) dy = container.height - margin - bottom;
  if (rect.h * v.zoom > container.height - 2 * margin) dy = margin - top;
  return dx === 0 && dy === 0 ? null : { ...v, x: v.x + dx, y: v.y + dy };
}

// ---------------------------------------------------------------- 방향키 이동

export type Direction = "left" | "right" | "up" | "down";

/**
 * 방향키로 갈 가장 가까운 칸 id. 그 방향에 칸이 없으면 null.
 * 주 방향 거리 + 직각 방향 거리 × 2가 가장 작은 칸이다.
 */
export function nearestInDirection(rects: Readonly<Record<string, Rect>>, fromId: string, dir: Direction): string | null {
  const from = rects[fromId];
  if (!from) return null;
  const [fx, fy] = rectCenter(from);
  let best: string | null = null;
  let bestScore = Infinity;
  for (const [id, r] of Object.entries(rects)) {
    if (id === fromId) continue;
    const [cx, cy] = rectCenter(r);
    const dx = cx - fx;
    const dy = cy - fy;
    const main = dir === "right" ? dx : dir === "left" ? -dx : dir === "down" ? dy : -dy;
    const side = dir === "left" || dir === "right" ? Math.abs(dy) : Math.abs(dx);
    if (main <= 0 || side > main * 1.5 + 1) continue;
    const score = main + side * 2;
    if (score < bestScore) {
      bestScore = score;
      best = id;
    }
  }
  return best;
}
