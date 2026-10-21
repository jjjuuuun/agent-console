/**
 * "엉킨 연결" 감지(graph-edges §10). 순수 함수: 이미 계산한 엣지 선분과 노드 사각형만 본다.
 * 엣지가 (a) 노드 사각형을 지나거나(다른 노드 `crosses-node`, 자기 끝점 노드 안쪽 `crosses-own-node`) (b) 소스·타깃 핸들이 서로 반대쪽을 향해 경로가 노드를 감싸면 문제로 본다.
 * 데이터를 바꾸지 않는다(힌트만).
 */
import type { EdgeSegment, Side } from "../shapes/types";
import type { Point } from "./ops";
import { sideNormal } from "./edgePath";

export interface TroubleNode {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface TroubleEdge {
  id: string;
  sourceNode: string;
  targetNode: string;
  /** 소스 핸들 위치와 그 핸들이 놓인 면 */
  source: Point & { side: Side };
  target: Point & { side: Side };
  /** 그려질 경로를 편 선분 */
  segments: readonly EdgeSegment[];
  /** 자체 회피 라우터가 그리는 엣지(노드를 피하므로 (a)·(b) 모두 검사하지 않는다) */
  selfAvoiding?: boolean;
}

export type TroubleReason = "crosses-node" | "crosses-own-node" | "wraps-node";

export interface EdgeTrouble {
  edgeId: string;
  reasons: TroubleReason[];
  /** `crosses-node`·`crosses-own-node`일 때 지나는 노드 id */
  crossedNodes: string[];
}

export interface DetectEdgeTroubleOptions {
  /** 사각형을 이만큼 줄여 검사한다(경계에 스치는 선은 제외, px). 기본 2 */
  inset?: number;
  /** 핸들이 반대쪽을 향한 것으로 보는 최소 거리(px). 기본 0 */
  wrapTolerance?: number;
}

function segmentHitsRect(a: Point, b: Point, r: { left: number; top: number; right: number; bottom: number }): boolean {
  if (r.right <= r.left || r.bottom <= r.top) return false;
  // Liang–Barsky
  let t0 = 0;
  let t1 = 1;
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const clip = (p: number, q: number): boolean => {
    if (p === 0) return q >= 0;
    const t = q / p;
    if (p < 0) {
      if (t > t1) return false;
      if (t > t0) t0 = t;
    } else {
      if (t < t0) return false;
      if (t < t1) t1 = t;
    }
    return true;
  };
  return clip(-dx, a.x - r.left) && clip(dx, r.right - a.x) && clip(-dy, a.y - r.top) && clip(dy, r.bottom - a.y);
}

/** 문제가 있는 엣지만 id 순으로 돌려준다(없으면 빈 배열). */
export function detectEdgeTrouble(nodes: readonly TroubleNode[], edges: readonly TroubleEdge[], options: DetectEdgeTroubleOptions = {}): EdgeTrouble[] {
  const inset = options.inset ?? 2;
  const tol = options.wrapTolerance ?? 0;
  const rects = nodes.map((n) => ({ id: n.id, left: n.x + inset, top: n.y + inset, right: n.x + n.width - inset, bottom: n.y + n.height - inset }));
  const out: EdgeTrouble[] = [];
  for (const e of [...edges].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))) {
    const reasons: TroubleReason[] = [];
    const crossed: string[] = [];
    if (e.selfAvoiding !== true) {
      for (const r of rects) {
        if (r.id === e.sourceNode || r.id === e.targetNode) continue;
        if (e.segments.some((s) => segmentHitsRect(s.from, s.to, r))) crossed.push(r.id);
      }
      if (crossed.length > 0) reasons.push("crosses-node");
      // 자기 끝점 노드 안쪽을 가로지르는 것도 사용자에게는 겹침이다(고리 연결은 제외)
      if (e.sourceNode !== e.targetNode) {
        const own = rects.filter((r) => (r.id === e.sourceNode || r.id === e.targetNode) && e.segments.some((s) => segmentHitsRect(s.from, s.to, r)));
        if (own.length > 0) {
          reasons.push("crosses-own-node");
          crossed.push(...own.map((r) => r.id));
        }
      }
    }
    // 소스 핸들이 타깃과 반대 방향을 보거나, 타깃 핸들이 소스와 반대 방향을 보면 경로가 노드를 감싼다
    const ns = sideNormal(e.source.side);
    const nt = sideNormal(e.target.side);
    const awaySource = (e.target.x - e.source.x) * ns.x + (e.target.y - e.source.y) * ns.y < -tol;
    const awayTarget = (e.source.x - e.target.x) * nt.x + (e.source.y - e.target.y) * nt.y < -tol;
    // 자체 회피 라우터가 그리는 엣지는 되돌아가는 연결도 노드 바깥으로 돌려 그리므로 감싸기도 문제로 보지 않는다
    if ((awaySource || awayTarget) && e.selfAvoiding !== true) reasons.push("wraps-node");
    if (reasons.length > 0) out.push({ edgeId: e.id, reasons, crossedNodes: crossed });
  }
  return out;
}
