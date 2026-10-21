/**
 * 자동 경로를 캔버스에 연결하는 순수 계산(graph-edges §4.2). React·React Flow에 의존하지 않는다.
 * - `buildRouteInput`: 화면에 측정된 노드·핸들 좌표에서 라우터 요청을 만든다. 끝점은 React Flow가 `AcEdge`에 주는
 *   `sourceX` 등과 같은 규칙(핸들 상자의 면 중앙)으로 계산한다.
 * - `routePreview`: [정리] 미리보기용으로, 새 노드 위치 기준 연결 중심선을 라우터로 계산한다.
 */
import type { EdgeRouter, RouteEdgeRequest, RouteObstacle, RoutedEdge } from "./route";
import type { Point } from "./ops";
import type { EdgeEndpoint, Side } from "../shapes/types";

/** 측정된 핸들 상자(노드 좌상단 기준). React Flow `handleBounds` 항목과 같은 모양 */
export interface HandleBox {
  id?: string | null;
  x: number;
  y: number;
  width: number;
  height: number;
  position: Side;
}

/** 측정된 노드(캔버스 절대 좌표) */
export interface RouteNodeGeometry {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  source: readonly HandleBox[];
  target: readonly HandleBox[];
}

/** 자동 경로를 쓰는 엣지의 입력 */
export interface RouteEdgeInput {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
  waypoints?: readonly Point[] | null;
  radius?: number | null;
}

/** 노드 크기의 출처들. 위에서부터 유효한(0보다 큰 유한) 값을 쓴다. */
export interface NodeSizeSources {
  /** 실제로 그려진 카드의 레이아웃 크기(DOM `offsetWidth/Height`) */
  rendered?: { width: number; height: number } | undefined;
  /** React Flow가 측정해 둔 크기 */
  measured?: { width?: number | undefined; height?: number | undefined } | undefined;
  /** 추정·지정 크기(`width`/`height`, 없으면 `initialWidth`/`initialHeight`) */
  declared?: { width?: number | undefined; height?: number | undefined } | undefined;
}

const usable = (v: number | undefined): v is number => v !== undefined && Number.isFinite(v) && v > 0;

/**
 * 장애물로 쓸 노드 크기: 실제로 그려진 카드 크기 → 측정값 → 추정값 순(가로·세로 따로).
 * 실행 상세의 카드는 상태 줄·요약 줄 때문에 편집기의 추정값보다 커서, 추정값이나 낡은 측정값을 쓰면 경로가 카드 가장자리를 스친다(4R.20).
 * 어느 출처에도 값이 없으면 0.
 */
export function actualNodeSize(src: NodeSizeSources): { width: number; height: number } {
  const pick = (a: number | undefined, b: number | undefined, c: number | undefined): number => (usable(a) ? a : usable(b) ? b : usable(c) ? c : 0);
  return {
    width: pick(src.rendered?.width, src.measured?.width, src.declared?.width),
    height: pick(src.rendered?.height, src.measured?.height, src.declared?.height),
  };
}

/** 핸들 상자의 선 끝점(React Flow `getHandlePosition`과 같음: 면에 맞닿은 변의 중앙) */
export function handleEndpoint(node: RouteNodeGeometry, h: HandleBox): EdgeEndpoint {
  const x = node.x + h.x;
  const y = node.y + h.y;
  switch (h.position) {
    case "top":
      return { x: x + h.width / 2, y, side: "top" };
    case "right":
      return { x: x + h.width, y: y + h.height / 2, side: "right" };
    case "bottom":
      return { x: x + h.width / 2, y: y + h.height, side: "bottom" };
    case "left":
      return { x, y: y + h.height / 2, side: "left" };
  }
}

const pick = (boxes: readonly HandleBox[], id: string | null | undefined): HandleBox | undefined => (id ? boxes.find((b) => b.id === id) : boxes[0]);

export interface RouteInput {
  requests: RouteEdgeRequest[];
  obstacles: RouteObstacle[];
}

/**
 * 라우터 입력을 만든다. 핸들이 아직 측정되지 않은 엣지는 요청에서 뺀다(측정 뒤 다시 계산된다).
 * 타깃 핸들은 느슨한 연결 모드와 같이 타깃·소스 핸들 모두에서 찾는다.
 */
export function buildRouteInput(edges: readonly RouteEdgeInput[], nodes: ReadonlyMap<string, RouteNodeGeometry>): RouteInput {
  const obstacles: RouteObstacle[] = [];
  for (const n of nodes.values()) obstacles.push({ id: n.id, x: n.x, y: n.y, width: n.width, height: n.height });
  const requests: RouteEdgeRequest[] = [];
  for (const e of edges) {
    const sn = nodes.get(e.source);
    const tn = nodes.get(e.target);
    if (sn === undefined || tn === undefined) continue;
    const sh = pick(sn.source, e.sourceHandle);
    const th = pick([...tn.target, ...tn.source], e.targetHandle);
    if (sh === undefined || th === undefined) continue;
    requests.push({
      id: e.id,
      source: handleEndpoint(sn, sh),
      target: handleEndpoint(tn, th),
      waypoints: e.waypoints ?? null,
      sourceNodeId: e.source,
      targetNodeId: e.target,
      ...(e.radius !== undefined && e.radius !== null ? { radius: e.radius } : {}),
    });
  }
  return { requests, obstacles };
}

/** 노드 사각형의 면 중앙 */
export function faceAnchor(r: { x: number; y: number; width: number; height: number }, side: Side): EdgeEndpoint {
  switch (side) {
    case "left":
      return { x: r.x, y: r.y + r.height / 2, side };
    case "right":
      return { x: r.x + r.width, y: r.y + r.height / 2, side };
    case "top":
      return { x: r.x + r.width / 2, y: r.y, side };
    case "bottom":
      return { x: r.x + r.width / 2, y: r.y + r.height, side };
  }
}

export interface PreviewNode {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  /** 연결 포트 id → 면. 모르면 입력은 left, 출력은 right */
  inputSides: ReadonlyMap<string, Side>;
  outputSides: ReadonlyMap<string, Side>;
}

export interface PreviewEdge {
  id: string;
  source: { node: string; port: string };
  target: { node: string; port: string };
}

/**
 * 새 위치 기준 연결 중심선. 모든 엣지를 한 번에 라우터에 넘긴다(교차 비용이 앞선 엣지에 의존).
 * 두 끝 노드가 모두 `nodes`에 있는 엣지만 계산한다. 반환은 엣지 id → 라우터 결과.
 */
export function routePreview(router: EdgeRouter, nodes: readonly PreviewNode[], edges: readonly PreviewEdge[]): ReadonlyMap<string, RoutedEdge> {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const requests: RouteEdgeRequest[] = [];
  for (const e of edges) {
    const s = byId.get(e.source.node);
    const t = byId.get(e.target.node);
    if (s === undefined || t === undefined) continue;
    requests.push({
      id: e.id,
      source: faceAnchor(s, s.outputSides.get(e.source.port) ?? "right"),
      target: faceAnchor(t, t.inputSides.get(e.target.port) ?? "left"),
      sourceNodeId: s.id,
      targetNodeId: t.id,
    });
  }
  return router.route(
    requests,
    nodes.map((n) => ({ id: n.id, x: n.x, y: n.y, width: n.width, height: n.height })),
  );
}
