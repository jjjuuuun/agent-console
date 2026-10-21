/**
 * 연결선 `layout`을 고치는 순수 함수(graph-edges §2, §5.4). React·React Flow에 의존하지 않는다.
 * 입력은 건드리지 않고 새 값을 돌려준다.
 */
import type { EdgeLayout, EdgeSpec, Graph } from "@agent-console/contracts";
import { MAX_WAYPOINTS } from "./edgePath";
import { edgesOf, snap } from "./ops";
import type { Point } from "./ops";
import type { EdgeSegment, PathPointAt } from "../shapes/types";

/** 저장 때 `layout` 키가 놓이는 순서(diff 안정, §5.4). 모르는 키는 그 뒤에 원래 순서로 붙는다. */
export const EDGE_LAYOUT_KEY_ORDER = ["shape", "radius", "bend", "waypoints", "label_t", "label_offset"] as const;

/** 경로 초기화가 지우는 키(모양·모서리는 유지, §2.4). */
export const PATH_KEYS = ["waypoints", "bend", "label_t", "label_offset"] as const;

/** 라벨 위치 범위와 단위(§2.3). */
export const LABEL_T_MIN = 0.1;
export const LABEL_T_MAX = 0.9;
export const LABEL_T_STEP = 0.05;

/** 값이 `null`/`undefined`인 키는 지운다. */
export type EdgeLayoutPatch = Partial<EdgeLayout>;

const round1 = (v: number): number => Math.round(v * 10) / 10;
const round2 = (v: number): number => Math.round(v * 100) / 100;
const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v));
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const isPoint = (p: unknown): p is Point => typeof p === "object" && p !== null && finite((p as Point).x) && finite((p as Point).y);

/** 경로 초기화 패치(`waypoints`·`bend`·`label_t`·`label_offset` 삭제). */
export const RESET_PATH_PATCH: EdgeLayoutPatch = { waypoints: null, bend: null, label_t: null, label_offset: null };
/** 라벨 위치만 초기화하는 패치. */
export const RESET_LABEL_PATCH: EdgeLayoutPatch = { label_t: null, label_offset: null };

/**
 * `layout`을 저장 형식으로 정리한다(§5.4).
 * 빈 값(`null`·`undefined`·빈 경유점)은 키째 삭제, 숫자는 반올림(좌표·반경·꺾임 소수 1자리, 라벨 위치 소수 2자리),
 * 키 순서는 `EDGE_LAYOUT_KEY_ORDER`, 모르는 키는 그대로 통과. 모두 비면 `null`.
 */
export function normalizeEdgeLayout(layout: EdgeLayout | null | undefined): EdgeLayout | null {
  if (layout === null || layout === undefined) return null;
  const out: EdgeLayout = {};
  const put = (k: keyof EdgeLayout, v: unknown): void => {
    (out as Record<string, unknown>)[k] = v;
  };
  if (typeof layout.shape === "string" && layout.shape !== "") put("shape", layout.shape);
  if (finite(layout.radius)) put("radius", round1(layout.radius));
  if (finite(layout.bend)) put("bend", round1(layout.bend));
  if (Array.isArray(layout.waypoints)) {
    const wps = layout.waypoints.filter(isPoint).slice(0, MAX_WAYPOINTS).map((p) => ({ x: round1(p.x), y: round1(p.y) }));
    if (wps.length > 0) put("waypoints", wps);
  }
  if (finite(layout.label_t)) put("label_t", round2(layout.label_t));
  if (isPoint(layout.label_offset)) put("label_offset", { x: round1(layout.label_offset.x), y: round1(layout.label_offset.y) });
  for (const [k, v] of Object.entries(layout)) {
    if ((EDGE_LAYOUT_KEY_ORDER as readonly string[]).includes(k)) continue;
    if (v !== null && v !== undefined) (out as Record<string, unknown>)[k] = v;
  }
  return Object.keys(out).length === 0 ? null : out;
}

/** `patch`를 합쳐 정리한다. 패치의 `null`/`undefined`는 그 키를 지운다. */
export function applyEdgeLayoutPatch(layout: EdgeLayout | null | undefined, patch: EdgeLayoutPatch): EdgeLayout | null {
  const merged: Record<string, unknown> = { ...(layout ?? {}) };
  for (const [k, v] of Object.entries(patch)) {
    if (v === null || v === undefined) delete merged[k];
    else merged[k] = v;
  }
  return normalizeEdgeLayout(merged as EdgeLayout);
}

/** 엣지 하나의 `layout`을 통째로 바꾼다(`null`이면 `layout` 키를 지운다). 다른 키는 그대로. */
export function setEdgeLayout(g: Graph, edgeId: string, layout: EdgeLayout | null): Graph {
  const next = normalizeEdgeLayout(layout);
  return {
    ...g,
    edges: edgesOf(g).map((e) => {
      if (e.id !== edgeId) return e;
      const { layout: _old, ...rest } = e;
      void _old;
      return (next === null ? rest : { ...rest, layout: next }) as EdgeSpec;
    }),
  };
}

/** 엣지 하나의 `layout`에 패치를 합친다. */
export function patchEdgeLayout(g: Graph, edgeId: string, patch: EdgeLayoutPatch): Graph {
  const edge = edgesOf(g).find((e) => e.id === edgeId);
  if (edge === undefined) return g;
  return setEdgeLayout(g, edgeId, applyEdgeLayoutPatch(edge.layout, patch));
}

/**
 * 여러 엣지의 `layout`에 같은 패치를 합친다(다중 선택 [모양 ▾]·[경로 초기화], graph-edges §1.4·§2.4).
 * 한 번에 새 그래프 하나를 만든다. 바뀔 것이 없으면 같은 그래프를 돌려준다.
 */
export function patchEdgesLayout(g: Graph, edgeIds: readonly string[], patch: EdgeLayoutPatch): Graph {
  const ids = new Set(edgeIds);
  let changed = false;
  const edges = edgesOf(g).map((e) => {
    if (!ids.has(e.id)) return e;
    const next = applyEdgeLayoutPatch(e.layout, patch);
    if (JSON.stringify(next) === JSON.stringify(normalizeEdgeLayout(e.layout))) return e;
    changed = true;
    const { layout: _old, ...rest } = e;
    void _old;
    return (next === null ? rest : { ...rest, layout: next }) as EdgeSpec;
  });
  return changed ? { ...g, edges } : g;
}

/** 경로 초기화로 실제 지워질 것이 있는 엣지 수(다중 선택 확인 문구용). */
export function countResettableEdges(g: Graph, edgeIds: readonly string[]): number {
  const ids = new Set(edgeIds);
  return edgesOf(g).filter((e) => ids.has(e.id) && PATH_KEYS.some((k) => normalizeEdgeLayout(e.layout)?.[k] !== undefined)).length;
}

// ---------------------------------------------------------------------------------------------
// 모양 순환(`S` 키)

/**
 * 모양 id 목록 순서로 다음/이전 값을 돌려준다. 마지막 다음과 첫 값 이전은 `null`(= 상속).
 * 현재 값이 없거나 목록에 없으면(상속·알 수 없음) 앞으로는 첫 값, 뒤로는 마지막 값.
 */
export function cycleShape(ids: readonly string[], current: string | null | undefined, direction: 1 | -1 = 1): string | null {
  if (ids.length === 0) return null;
  const at = current === null || current === undefined ? -1 : ids.indexOf(current);
  if (at < 0) return (direction === 1 ? ids[0] : ids[ids.length - 1]) ?? null;
  const next = at + direction;
  if (next < 0 || next >= ids.length) return null;
  return ids[next] ?? null;
}

// ---------------------------------------------------------------------------------------------
// 경유점

/** 경유점을 index 자리에 끼운다. 상한(16)이면 `null`. */
export function insertWaypoint(wps: readonly Point[], index: number, p: Point): Point[] | null {
  if (wps.length >= MAX_WAYPOINTS) return null;
  const at = clamp(index, 0, wps.length);
  return [...wps.slice(0, at), { x: p.x, y: p.y }, ...wps.slice(at)];
}

export function moveWaypoint(wps: readonly Point[], index: number, p: Point): Point[] {
  return wps.map((w, i) => (i === index ? { x: p.x, y: p.y } : w));
}

export function removeWaypoint(wps: readonly Point[], index: number): Point[] {
  return wps.filter((_, i) => i !== index);
}

/** `from` 자리의 경유점을 `to` 자리로 옮긴다(범위 밖이면 그대로). */
export function reorderWaypoint(wps: readonly Point[], from: number, to: number): Point[] {
  if (from < 0 || from >= wps.length || to < 0 || to >= wps.length || from === to) return [...wps];
  const next = [...wps];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item as Point);
  return next;
}

/** 소스 → 경유점들 → 타깃 순서의 점 목록. */
export const anchorsOf = (source: Point, wps: readonly Point[], target: Point): Point[] => [source, ...wps, target];

/** 점 p에서 선분 a-b까지의 거리. */
export function distanceToSegment(p: Point, a: Point, b: Point): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len2 = dx * dx + dy * dy;
  const k = len2 === 0 ? 0 : clamp(((p.x - a.x) * dx + (p.y - a.y) * dy) / len2, 0, 1);
  return Math.hypot(p.x - (a.x + dx * k), p.y - (a.y + dy * k));
}

/**
 * 경유점 index가 앞뒤 점을 잇는 선에서 `tolerance`(캔버스 px) 이내면 `true` — 일직선이라 자동 삭제할 점(§2.2).
 * 앞뒤 점은 이웃 경유점 또는 소스·타깃 핸들이다.
 */
export function isRedundantWaypoint(source: Point, wps: readonly Point[], target: Point, index: number, tolerance: number): boolean {
  const a = anchorsOf(source, wps, target);
  const prev = a[index];
  const cur = a[index + 1];
  const next = a[index + 2];
  if (prev === undefined || cur === undefined || next === undefined) return false;
  return distanceToSegment(cur, prev, next) <= tolerance;
}

/** `Shift` 축 고정: 이전 점 기준 가로/세로 중 큰 쪽만 남긴다. */
export function lockAxis(prev: Point, p: Point): Point {
  return Math.abs(p.x - prev.x) >= Math.abs(p.y - prev.y) ? { x: p.x, y: prev.y } : { x: prev.x, y: p.y };
}

/** 드래그 중 경유점 위치를 정한다: 축 고정(Shift) → 격자 스냅(Alt면 건너뜀). */
export function placeWaypoint(raw: Point, opts: { prev: Point; shift: boolean; alt: boolean; grid: number | false }): Point {
  const locked = opts.shift ? lockAxis(opts.prev, raw) : raw;
  const snapped = opts.alt ? locked : snap(locked, opts.grid);
  return { x: round1(snapped.x), y: round1(snapped.y) };
}

/** 점 p에 가장 가까운 선분 위의 점과 거리. 선분이 없으면 `null`. */
export function nearestOnSegments(segments: readonly EdgeSegment[], p: Point): { point: Point; distance: number; index: number } | null {
  let best: { point: Point; distance: number; index: number } | null = null;
  segments.forEach((s, index) => {
    const dx = s.to.x - s.from.x;
    const dy = s.to.y - s.from.y;
    const len2 = dx * dx + dy * dy;
    const k = len2 === 0 ? 0 : clamp(((p.x - s.from.x) * dx + (p.y - s.from.y) * dy) / len2, 0, 1);
    const point = { x: s.from.x + dx * k, y: s.from.y + dy * k };
    const distance = Math.hypot(p.x - point.x, p.y - point.y);
    if (best === null || distance < best.distance) best = { point, distance, index };
  });
  return best;
}

/**
 * 새 경유점 p를 끼울 자리: 끼웠을 때 늘어나는 길이가 가장 작은 구간(= 가장 가까운 선분).
 * 반환값은 `wps` 안의 삽입 index(0 = 첫 경유점 앞).
 */
export function insertIndexFor(source: Point, wps: readonly Point[], target: Point, p: Point): number {
  const a = anchorsOf(source, wps, target);
  let best = 0;
  let bestExtra = Number.POSITIVE_INFINITY;
  for (let i = 0; i < a.length - 1; i += 1) {
    const from = a[i] as Point;
    const to = a[i + 1] as Point;
    const extra = Math.hypot(p.x - from.x, p.y - from.y) + Math.hypot(to.x - p.x, to.y - p.y) - Math.hypot(to.x - from.x, to.y - from.y);
    if (extra < bestExtra) {
      bestExtra = extra;
      best = i;
    }
  }
  return best;
}

/**
 * 선분 중점 "+" 위치: 인접한 두 점의 가운데에서 경로 위의 가장 가까운 점.
 * 결과 길이는 경유점 수 + 1. 경로가 없으면 단순 중점.
 */
export function midpointHandles(source: Point, wps: readonly Point[], target: Point, segments: readonly EdgeSegment[]): Point[] {
  const a = anchorsOf(source, wps, target);
  const out: Point[] = [];
  for (let i = 0; i < a.length - 1; i += 1) {
    const from = a[i] as Point;
    const to = a[i + 1] as Point;
    const mid = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 };
    out.push(nearestOnSegments(segments, mid)?.point ?? mid);
  }
  return out;
}

// ---------------------------------------------------------------------------------------------
// 라벨 위치

/** 라벨 위치를 0.05 단위로 반올림하고 0.1~0.9로 자른다. */
export const snapLabelT = (t: number): number => round2(clamp(Math.round(t / LABEL_T_STEP) * LABEL_T_STEP, LABEL_T_MIN, LABEL_T_MAX));

/**
 * 점 p에 가장 가까운 라벨 위치(0.1~0.9, 0.05 단위). 경로 모양에 따라 t의 뜻이 다르므로
 * (경유점 없는 곡선은 베지어 매개변수) 선분 투영 대신 `labelAt`을 직접 훑어 찾는다.
 */
export function nearestLabelT(labelAt: (t: number) => PathPointAt, p: Point): number {
  let best = 0.5;
  let bestDist = Number.POSITIVE_INFINITY;
  const steps = Math.round((LABEL_T_MAX - LABEL_T_MIN) / LABEL_T_STEP);
  for (let i = 0; i <= steps; i += 1) {
    const t = round2(LABEL_T_MIN + i * LABEL_T_STEP);
    const at = labelAt(t);
    const d = Math.hypot(at.x - p.x, at.y - p.y);
    if (d < bestDist) {
      bestDist = d;
      best = t;
    }
  }
  return best;
}

// ---------------------------------------------------------------------------------------------
// 패널 요약

/** 기본값에서 바뀐 항목의 키 목록(패널의 "기본값에서 바뀐 항목"). 알려진 키만, 저장 키 순서대로. */
export function changedLayoutKeys(layout: EdgeLayout | null | undefined): Array<(typeof EDGE_LAYOUT_KEY_ORDER)[number]> {
  const n = normalizeEdgeLayout(layout);
  if (n === null) return [];
  return EDGE_LAYOUT_KEY_ORDER.filter((k) => n[k] !== undefined);
}
