/**
 * 자동 경로 연결 훅(graph-edges §4.2). `route`를 가진 모양의 엣지를 모아 라우터에 한 번에 넘기고 결과를 돌려 준다.
 * - 라우터는 편집기 인스턴스당 하나(`getRouter`가 같은 객체를 돌려줘야 한다). 매 렌더·프레임 생성 금지.
 * - 끝점은 React Flow가 측정한 핸들 상자에서 읽어 `AcEdge`의 `sourceX` 등과 같게 맞춘다.
 * - 노드를 끄는 동안에는 `throttleMs`(기본 50ms)마다 다시 계산하고, 멈추면 마지막 값으로 한 번 더 계산한다.
 */
import { useEffect, useRef, useState } from "react";
import { useStore, useStoreApi } from "@xyflow/react";
import { actualNodeSize, buildRouteInput } from "../logic/autoRoute";
import type { HandleBox, RouteEdgeInput, RouteNodeGeometry } from "../logic/autoRoute";
import type { EdgeRouter, RoutedEdge } from "../logic/route";
import type { FlowEdge } from "./flow";

export const ROUTE_THROTTLE_MS = 50;
const NONE: ReadonlyMap<string, RoutedEdge> = new Map();

/** 자동 경로로 그려야 하는 엣지만 추린다(모양 id가 아니라 `route` 속성으로 판단). */
export const routedEdgeInputs = (edges: readonly FlowEdge[]): RouteEdgeInput[] =>
  edges
    .filter((e) => e.data?.shape.route === "obstacle-avoiding")
    .map((e) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle ?? null, targetHandle: e.targetHandle ?? null, waypoints: e.data?.waypoints ?? null, radius: e.data?.radius ?? null }));

interface InternalLike {
  id: string;
  measured: { width?: number; height?: number };
  width?: number | undefined;
  height?: number | undefined;
  initialWidth?: number | undefined;
  initialHeight?: number | undefined;
  /** 노드 데이터. 겹친 카드(`stacked`)는 뒤 카드 두 장만큼 장애물이 커진다 */
  data?: { stacked?: unknown } | undefined;
  internals: {
    positionAbsolute: { x: number; y: number };
    handleBounds?: { source?: readonly HandleBox[] | null; target?: readonly HandleBox[] | null } | undefined;
  };
}

/** 화면에 그려진 카드의 크기(레이아웃 px, 줌과 무관). 그려지지 않았으면 `undefined` */
function renderedSize(root: ParentNode | null | undefined, id: string): { width: number; height: number } | undefined {
  const el = root?.querySelector<HTMLElement>(`.react-flow__node[data-id="${CSS.escape(id)}"]`);
  return el === null || el === undefined || el.offsetWidth === 0 ? undefined : { width: el.offsetWidth, height: el.offsetHeight };
}

/** 겹친 카드가 앞 카드 밖으로 내미는 길이: 뒤 카드 두 장 × 어긋남(4px). 토큰 `--ac-stack-offset`의 두 배 */
export const STACK_EXTRA = 8;

function sizeOf(n: InternalLike, root: ParentNode | null | undefined): { width: number; height: number } {
  const size = actualNodeSize({
    rendered: renderedSize(root, n.id),
    measured: n.measured,
    declared: { width: n.width ?? n.initialWidth, height: n.height ?? n.initialHeight },
  });
  return n.data?.stacked === true && size.width > 0 ? { width: size.width + STACK_EXTRA, height: size.height + STACK_EXTRA } : size;
}

function geometryOf(lookup: ReadonlyMap<string, InternalLike>, root: ParentNode | null | undefined): Map<string, RouteNodeGeometry> {
  const out = new Map<string, RouteNodeGeometry>();
  for (const n of lookup.values()) {
    const hb = n.internals.handleBounds;
    const size = sizeOf(n, root);
    out.set(n.id, {
      id: n.id,
      x: n.internals.positionAbsolute.x,
      y: n.internals.positionAbsolute.y,
      width: size.width,
      height: size.height,
      source: (hb?.source ?? []).map((h) => ({ id: h.id ?? null, x: h.x, y: h.y, width: h.width, height: h.height, position: h.position })),
      target: (hb?.target ?? []).map((h) => ({ id: h.id ?? null, x: h.x, y: h.y, width: h.width, height: h.height, position: h.position })),
    });
  }
  return out;
}

/** 노드 위치·크기·핸들 상자가 바뀌었는지 알아보는 서명 */
function signatureOf(lookup: ReadonlyMap<string, InternalLike>, root: ParentNode | null | undefined): string {
  let k = "";
  for (const n of lookup.values()) {
    const hb = n.internals.handleBounds;
    const size = sizeOf(n, root);
    k += `${n.id}:${n.internals.positionAbsolute.x},${n.internals.positionAbsolute.y},${size.width},${size.height}`;
    for (const h of hb?.source ?? []) k += `;${h.id}:${h.x},${h.y},${h.position}`;
    for (const h of hb?.target ?? []) k += `;${h.id}:${h.x},${h.y},${h.position}`;
    k += "|";
  }
  return k;
}

export interface UseAutoRoutesArgs {
  edges: readonly FlowEdge[];
  /** 같은 인스턴스를 돌려줘야 한다(첫 호출 때 만들어도 된다). 자동 경로 엣지가 없으면 호출하지 않는다 */
  getRouter: () => EdgeRouter;
  throttleMs?: number;
  /** 시계(테스트용). 기본 `Date.now` */
  now?: () => number;
}

/** 엣지 id → 라우터 결과. 자동 경로 엣지가 없으면 빈 Map(라우터를 만들지 않는다). */
export function useAutoRoutes({ edges, getRouter, throttleMs = ROUTE_THROTTLE_MS, now = Date.now }: UseAutoRoutesArgs): ReadonlyMap<string, RoutedEdge> {
  const store = useStoreApi();
  const inputs = routedEdgeInputs(edges);
  const inputKey = JSON.stringify(inputs);
  const enabled = inputs.length > 0;
  const geometryKey = useStore((s) => (enabled ? signatureOf(s.nodeLookup as unknown as ReadonlyMap<string, InternalLike>, s.domNode) : ""));
  const [routes, setRoutes] = useState<ReadonlyMap<string, RoutedEdge>>(NONE);
  const lastRun = useRef(Number.NEGATIVE_INFINITY);
  const latest = useRef({ inputs, getRouter });
  useEffect(() => {
    latest.current = { inputs, getRouter };
  });

  useEffect(() => {
    if (!enabled) return;
    const run = (): void => {
      lastRun.current = now();
      const { inputs: ins, getRouter: get } = latest.current;
      const geometry = geometryOf(store.getState().nodeLookup as unknown as ReadonlyMap<string, InternalLike>, store.getState().domNode);
      const { requests, obstacles } = buildRouteInput(ins, geometry);
      setRoutes(requests.length === 0 ? NONE : get().route(requests, obstacles));
    };
    const wait = lastRun.current + throttleMs - now();
    if (wait <= 0) {
      run();
      return;
    }
    const h = setTimeout(run, wait);
    return () => clearTimeout(h);
  }, [enabled, inputKey, geometryKey, throttleMs, now, store]);

  return enabled ? routes : NONE;
}
