/**
 * 선택한 연결선의 경유점 조작 점(graph-edges §2.2, §6). React Flow에 의존하지 않는 표현 컴포넌트다.
 * 좌표 변환·줌·격자는 props로 받고, 결과는 콜백으로만 내보낸다.
 *
 * - `◇` 중점 드래그 = 경유점 생성(임계 3px) + 이동, `■` 드래그 = 이동(격자 스냅, Alt 해제, Shift 축 고정),
 *   `■` 더블클릭·Delete = 삭제, 드롭 때 앞뒤 점과 일직선(화면 6px 이내)이면 자동 삭제.
 * - 드래그 중 경로는 `onDraft`(rAF당 1회)로 미리 그리고, 손을 뗄 때 `onCommit` 1회.
 * - 키보드: 경유점 ←↑↓→ 8px(Shift 32, Alt 1), Delete 삭제, 중점 Enter/Space/W 추가, Esc 종료.
 */
import { useEffect, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent, PointerEvent as ReactPointerEvent, ReactNode } from "react";
import {
  insertWaypoint,
  isRedundantWaypoint,
  midpointHandles,
  moveWaypoint,
  placeWaypoint,
  removeWaypoint,
} from "../logic/edgeLayoutOps";
import type { Point } from "../logic/ops";
import { snap } from "../logic/ops";
import { format } from "../messages";
import type { GraphEditorMessages } from "../messages";
import type { EdgeSegment } from "../shapes/types";

/** 줌이 이보다 작으면 조작 점을 숨긴다(§2.2). */
export const MIN_EDIT_ZOOM = 0.5;
/** 이동이 이 값(화면 px)을 넘기 전에는 드래그로 보지 않는다. */
export const DRAG_THRESHOLD = 3;
/** 일직선 자동 삭제 허용 거리(화면 px). */
export const COLLINEAR_TOLERANCE = 6;
const KEY_STEP = 8;
const KEY_STEP_BIG = 32;
const KEY_STEP_FINE = 1;

export interface EdgeWaypointLayerProps {
  /** 선의 시작·끝 핸들 좌표(경유점의 이웃 점) */
  source: Point;
  target: Point;
  /** 지금 그릴 경유점(드래그 미리보기가 있으면 그 값) */
  waypoints: readonly Point[];
  /** 지금 그린 경로의 선분(중점 위치 계산) */
  segments: readonly EdgeSegment[];
  zoom: number;
  screenToFlow: (p: Point) => Point;
  snapGrid: number | false;
  /** 경로 편집 모드(조작 점이 탭 순서에 들어가고, 모드 진입 때 첫 점에 포커스) */
  keyboardMode: boolean;
  messages: GraphEditorMessages;
  /** 드래그 중 경로 미리보기. `null`이면 미리보기 해제 */
  onDraft: (next: Point[] | null) => void;
  /** 확정(드래그 1회·키 1회 = 1회 호출) */
  onCommit: (next: Point[]) => void;
  /** 16개 초과 시도 */
  onLimit: () => void;
  onAnnounce: (text: string) => void;
  onExit: () => void;
  /** 줌이 작아 조작 점이 숨겨질 때 한 번 알림 */
  onZoomHint?: () => void;
  minZoom?: number;
}

interface Drag {
  mode: "wp" | "mid";
  index: number;
  pointerId: number;
  startX: number;
  startY: number;
  startFlow: Point;
  started: boolean;
  base: Point[];
  current: Point[];
  redundant: boolean;
}

type FocusTarget = { kind: "wp" | "mid"; index: number };

const place = (p: Point, zoom: number, extra = ""): CSSProperties => ({
  transform: `translate(${p.x}px, ${p.y}px) scale(${1 / zoom}) ${extra} translate(-50%, -50%)`.replace(/\s+/g, " "),
  transformOrigin: "0 0",
});

const round = (v: number): number => Math.round(v);

export function EdgeWaypointLayer(props: EdgeWaypointLayerProps): ReactNode {
  const { source, target, waypoints, segments, zoom, screenToFlow, snapGrid, keyboardMode, messages: m } = props;
  const minZoom = props.minZoom ?? MIN_EDIT_ZOOM;
  const hidden = zoom < minZoom;
  const root = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);
  const raf = useRef<number | null>(null);
  const pendingDraft = useRef<Point[] | null>(null);
  const focusNext = useRef<FocusTarget | null>(null);
  const [coord, setCoord] = useState<Point | null>(null);
  const [dim, setDim] = useState<number | null>(null);
  const { onZoomHint } = props;

  useEffect(() => {
    if (hidden) onZoomHint?.();
  }, [hidden, onZoomHint]);

  useEffect(
    () => () => {
      if (raf.current !== null && typeof cancelAnimationFrame === "function") cancelAnimationFrame(raf.current);
    },
    [],
  );

  // 경로 편집 모드에 들어오면 첫 조작 점으로 포커스를 옮긴다.
  useEffect(() => {
    if (!keyboardMode || hidden) return;
    root.current?.querySelector<HTMLElement>("[data-wp], [data-mid]")?.focus();
  }, [keyboardMode, hidden]);

  useEffect(() => {
    const f = focusNext.current;
    if (f === null) return;
    // 조작 점이 아직 그려지지 않았으면(커밋이 부모 상태를 거쳐 다음 렌더에 도착) 포커스 요청을 남겨 두고 다음 렌더에서 다시 시도한다.
    const el = root.current?.querySelector<HTMLElement>(`[data-${f.kind}="${f.index}"]`);
    if (el === null || el === undefined) return;
    focusNext.current = null;
    el.focus();
  });

  if (hidden) return null;

  const flushDraft = (): void => {
    raf.current = null;
    if (pendingDraft.current !== null) props.onDraft(pendingDraft.current);
  };
  const scheduleDraft = (next: Point[]): void => {
    pendingDraft.current = next;
    if (raf.current !== null) return;
    if (typeof requestAnimationFrame === "function") raf.current = requestAnimationFrame(flushDraft);
    else flushDraft();
  };
  const cancelDraft = (): void => {
    if (raf.current !== null && typeof cancelAnimationFrame === "function") cancelAnimationFrame(raf.current);
    raf.current = null;
    pendingDraft.current = null;
  };

  const begin = (e: ReactPointerEvent<HTMLElement>, mode: "wp" | "mid", index: number): void => {
    if (e.button !== 0) return;
    e.stopPropagation();
    e.currentTarget.setPointerCapture?.(e.pointerId);
    e.currentTarget.focus();
    const list = [...waypoints];
    drag.current = {
      mode,
      index,
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      startFlow: screenToFlow({ x: e.clientX, y: e.clientY }),
      started: false,
      base: list,
      current: list,
      redundant: false,
    };
  };

  const move = (e: ReactPointerEvent<HTMLElement>): void => {
    const d = drag.current;
    if (d === null || e.pointerId !== d.pointerId) return;
    if (!d.started) {
      if (Math.hypot(e.clientX - d.startX, e.clientY - d.startY) < DRAG_THRESHOLD) return;
      if (d.mode === "mid") {
        const mids = midpointHandles(source, d.base, target, segments);
        const inserted = insertWaypoint(d.base, d.index, mids[d.index] ?? d.startFlow);
        if (inserted === null) {
          drag.current = null;
          props.onLimit();
          return;
        }
        d.base = inserted;
        d.current = inserted;
        d.mode = "wp";
      }
      d.started = true;
    }
    const raw = screenToFlow({ x: e.clientX, y: e.clientY });
    const prev = d.index === 0 ? source : (d.current[d.index - 1] as Point);
    const p = placeWaypoint(raw, { prev, shift: e.shiftKey, alt: e.altKey, grid: snapGrid });
    d.current = moveWaypoint(d.current, d.index, p);
    const redundant = isRedundantWaypoint(source, d.current, target, d.index, COLLINEAR_TOLERANCE / zoom);
    if (redundant !== d.redundant) {
      d.redundant = redundant;
      setDim(redundant ? d.index : null);
    }
    setCoord(p);
    scheduleDraft(d.current);
  };

  const end = (e: ReactPointerEvent<HTMLElement>, cancelled: boolean): void => {
    const d = drag.current;
    if (d === null || e.pointerId !== d.pointerId) return;
    drag.current = null;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
    cancelDraft();
    setCoord(null);
    setDim(null);
    if (!d.started) return;
    if (cancelled) {
      props.onDraft(null);
      return;
    }
    const final = d.redundant ? removeWaypoint(d.current, d.index) : d.current;
    props.onCommit(final);
    props.onDraft(null);
    if (d.redundant) props.onAnnounce(format(m.waypointRemoved, { i: d.index + 1, n: final.length }));
    else {
      const at = d.current[d.index] as Point;
      props.onAnnounce(format(d.mode === "wp" && d.base.length > waypoints.length ? m.waypointAdded : m.waypointMoved, { i: d.index + 1, x: round(at.x), y: round(at.y) }));
    }
  };

  const remove = (i: number): void => {
    const next = removeWaypoint(waypoints, i);
    props.onCommit(next);
    props.onAnnounce(format(m.waypointRemoved, { i: i + 1, n: next.length }));
    focusNext.current = next.length > 0 ? { kind: "wp", index: Math.min(i, next.length - 1) } : { kind: "mid", index: 0 };
  };

  const onWaypointKey = (e: KeyboardEvent<HTMLElement>, i: number): void => {
    const arrow: Record<string, Point> = { ArrowLeft: { x: -1, y: 0 }, ArrowRight: { x: 1, y: 0 }, ArrowUp: { x: 0, y: -1 }, ArrowDown: { x: 0, y: 1 } };
    const dir = arrow[e.key];
    if (dir !== undefined) {
      e.preventDefault();
      e.stopPropagation();
      const step = e.altKey ? KEY_STEP_FINE : e.shiftKey ? KEY_STEP_BIG : KEY_STEP;
      const cur = waypoints[i] as Point;
      const p = { x: cur.x + dir.x * step, y: cur.y + dir.y * step };
      props.onCommit(moveWaypoint(waypoints, i, p));
      props.onAnnounce(format(m.waypointMoved, { i: i + 1, x: round(p.x), y: round(p.y) }));
    } else if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      e.stopPropagation();
      remove(i);
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      props.onExit();
    }
  };

  const addAt = (i: number, at: Point): void => {
    const next = insertWaypoint(waypoints, i, snap(at, snapGrid));
    if (next === null) {
      props.onLimit();
      return;
    }
    props.onCommit(next);
    const p = next[i] as Point;
    props.onAnnounce(format(m.waypointAdded, { i: i + 1, x: round(p.x), y: round(p.y) }));
    focusNext.current = { kind: "wp", index: i };
  };

  const mids = midpointHandles(source, waypoints, target, segments);
  const tab = keyboardMode ? 0 : -1;

  return (
    <div ref={root} className="ac-ge-wp-layer" data-keyboard={keyboardMode ? "true" : undefined}>
      {waypoints.map((w, i) => (
        <div
          key={`w${i}`}
          className="ac-ge-wp nodrag nopan"
          data-wp={i}
          data-dimmed={dim === i ? "true" : undefined}
          role="button"
          aria-roledescription={m.waypointRoleDescription}
          aria-label={format(m.waypointAria, { i: i + 1, n: waypoints.length, x: round(w.x), y: round(w.y) })}
          tabIndex={tab}
          style={place(w, zoom)}
          onPointerDown={(e) => begin(e, "wp", i)}
          onPointerMove={move}
          onPointerUp={(e) => end(e, false)}
          onPointerCancel={(e) => end(e, true)}
          onDoubleClick={(e) => {
            e.stopPropagation();
            remove(i);
          }}
          onKeyDown={(e) => onWaypointKey(e, i)}
        />
      ))}
      {mids.map((mp, i) => (
        <div
          key={`m${i}`}
          className="ac-ge-wp-mid nodrag nopan"
          data-mid={i}
          role="button"
          aria-label={format(m.waypointAddAria, { i: i + 1 })}
          tabIndex={tab}
          style={place(mp, zoom)}
          onPointerDown={(e) => begin(e, "mid", i)}
          onPointerMove={move}
          onPointerUp={(e) => end(e, false)}
          onPointerCancel={(e) => end(e, true)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " " || e.key === "w" || e.key === "W") {
              e.preventDefault();
              e.stopPropagation();
              addAt(i, mp);
            } else if (e.key === "Escape") {
              e.preventDefault();
              e.stopPropagation();
              props.onExit();
            }
          }}
        />
      ))}
      {coord !== null && (
        <div className="ac-ge-coord-chip" aria-hidden="true" style={place(coord, zoom, "translate(48px, -24px)")}>
          {format(m.waypointCoord, { x: round(coord.x), y: round(coord.y) })}
        </div>
      )}
    </div>
  );
}
