/**
 * 핸들 이동 제스처(graph-edges §3.4): 롱프레스 400ms 또는 `Alt`+드래그로 이동 모드에 들어가
 * 노드 가장자리를 따라 끌고, 놓으면 가장 가까운 면으로 확정한다. 연결 드래그와는 이동 모드 진입으로 구분한다.
 * React Flow에 의존하지 않는다(핸들 DOM에 붙일 이벤트 props만 만든다). 이동 모드 중 캔버스 라이브러리의
 * 마우스 이동 처리는 window 캡처 단계에서 막아 연결 드래그가 시작되지 않게 한다.
 */
import { useCallback, useEffect, useRef } from "react";
import type { MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent } from "react";
import { nearestSide } from "../logic/nodeLayoutOps";
import type { Side } from "../shapes/types";

/** 롱프레스 시간(ms)과, 이 거리(px) 안에서 움직이면 아직 누르고 있는 것으로 본다. */
export const PORT_MOVE_HOLD_MS = 400;
export const PORT_MOVE_SLOP = 4;

export interface UsePortMoveOptions {
  enabled: boolean;
  /** 지금 핸들이 붙은 면 */
  currentSide: Side;
  /** 놓았을 때 면이 바뀌면 호출 */
  onCommit: (side: Side) => void;
  onCancel?: () => void;
  holdMs?: number;
}

export interface PortMoveHandlers {
  onPointerDownCapture: (e: ReactPointerEvent<HTMLElement>) => void;
  onMouseDownCapture: (e: ReactMouseEvent<HTMLElement>) => void;
  onClickCapture: (e: ReactMouseEvent<HTMLElement>) => void;
}

/** 노드 상자 요소에 이동 모드 표시를 달고 뗀다(CSS 가이드의 근거 속성). */
const MODE_ATTR = "data-port-move";
const SIDE_ATTR = "data-port-move-side";

export function usePortMove(opts: UsePortMoveOptions): PortMoveHandlers {
  const optsRef = useRef(opts);
  useEffect(() => {
    optsRef.current = opts;
  });
  const teardown = useRef<(() => void) | null>(null);
  const moved = useRef(false);
  useEffect(() => () => teardown.current?.(), []);

  const onPointerDownCapture = useCallback((e: ReactPointerEvent<HTMLElement>) => {
    const o = optsRef.current;
    if (!o.enabled || e.button !== 0) return;
    teardown.current?.();
    const handleEl = e.currentTarget;
    const found = handleEl.closest<HTMLElement>(".ac-ge-node");
    if (found === null) return;
    const nodeEl: HTMLElement = found;
    const pointerId = e.pointerId;
    const startX = e.clientX;
    const startY = e.clientY;
    let moving = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let side: Side | null = null;

    const sideAt = (x: number, y: number): Side | null => {
      const r = nodeEl.getBoundingClientRect();
      return nearestSide({ left: r.left, top: r.top, width: r.width, height: r.height }, { x, y });
    };
    const blockMove = (ev: Event): void => ev.stopPropagation();
    const finish = (commit: boolean): void => {
      const wasMoving = moving;
      if (timer !== null) clearTimeout(timer);
      timer = null;
      window.removeEventListener("pointermove", onMove, true);
      window.removeEventListener("pointerup", onUp, true);
      window.removeEventListener("pointercancel", onCancel, true);
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("mousemove", blockMove, true);
      window.removeEventListener("touchmove", blockMove, true);
      nodeEl.removeAttribute(MODE_ATTR);
      nodeEl.removeAttribute(SIDE_ATTR);
      handleEl.removeAttribute("data-moving");
      teardown.current = null;
      if (!wasMoving) return;
      moved.current = true;
      setTimeout(() => {
        moved.current = false;
      }, 0);
      const cur = optsRef.current;
      if (commit && side !== null && side !== cur.currentSide) cur.onCommit(side);
      else cur.onCancel?.();
    };
    const enter = (): void => {
      moving = true;
      nodeEl.setAttribute(MODE_ATTR, "true");
      handleEl.setAttribute("data-moving", "true");
      side = optsRef.current.currentSide;
      nodeEl.setAttribute(SIDE_ATTR, side);
      window.addEventListener("mousemove", blockMove, true);
      window.addEventListener("touchmove", blockMove, true);
    };
    function onMove(ev: PointerEvent): void {
      if (ev.pointerId !== pointerId) return;
      if (!moving) {
        if (Math.hypot(ev.clientX - startX, ev.clientY - startY) > PORT_MOVE_SLOP) finish(false); // 연결 드래그로 넘긴다
        return;
      }
      const next = sideAt(ev.clientX, ev.clientY);
      if (next !== null && next !== side) {
        side = next;
        nodeEl.setAttribute(SIDE_ATTR, next);
      }
    }
    function onUp(ev: PointerEvent): void {
      if (ev.pointerId === pointerId) finish(true);
    }
    function onCancel(ev: PointerEvent): void {
      if (ev.pointerId === pointerId) finish(false);
    }
    function onKey(ev: KeyboardEvent): void {
      if (ev.key === "Escape" && moving) {
        ev.stopPropagation();
        finish(false);
      }
    }
    window.addEventListener("pointermove", onMove, true);
    window.addEventListener("pointerup", onUp, true);
    window.addEventListener("pointercancel", onCancel, true);
    window.addEventListener("keydown", onKey, true);
    teardown.current = () => finish(false);
    if (e.altKey) enter();
    else timer = setTimeout(enter, o.holdMs ?? PORT_MOVE_HOLD_MS);
  }, []);

  // 이동 모드(Alt)로 시작했다면 캔버스 라이브러리가 연결 드래그를 시작하지 못하게 mousedown을 막는다.
  const onMouseDownCapture = useCallback((e: ReactMouseEvent<HTMLElement>) => {
    if (optsRef.current.enabled && e.altKey && e.button === 0) e.stopPropagation();
  }, []);
  // 이동을 마친 직후의 click이 클릭 연결로 번지지 않게 한다.
  const onClickCapture = useCallback((e: ReactMouseEvent<HTMLElement>) => {
    if (moved.current) {
      e.stopPropagation();
      e.preventDefault();
    }
  }, []);
  return { onPointerDownCapture, onMouseDownCapture, onClickCapture };
}
