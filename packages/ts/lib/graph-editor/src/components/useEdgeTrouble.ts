/** "엉킨 연결" 감지를 편집기 모델에 연결하는 훅(graph-edges §10). 계산 자체는 `detectEdgeTrouble`(순수). */
import { useEffect, useState } from "react";
import { buildEdgePath } from "../logic/edgePath";
import { parseHandleId } from "../logic/ports";
import { detectEdgeTrouble } from "../logic/troubleDetect";
import type { EdgeTrouble, TroubleEdge, TroubleNode } from "../logic/troubleDetect";
import { faceAnchor } from "../logic/autoRoute";
import type { RoutedEdge } from "../logic/route";
import { ROUTE_PLACEHOLDER_SHAPE } from "./flow";
import type { FlowEdge, FlowNode } from "./flow";

export const TROUBLE_SETTLE_MS = 800;

const nodeRect = (n: FlowNode, size: ReadonlyMap<string, { width: number; height: number }>): TroubleNode => {
  const dim = size.get(n.id);
  return { id: n.id, x: n.position.x, y: n.position.y, width: dim?.width ?? n.initialWidth ?? 0, height: dim?.height ?? n.initialHeight ?? 0 };
};

const anchor = (r: TroubleNode, side: Parameters<typeof faceAnchor>[1]) => faceAnchor(r, side);

/**
 * 화면 모델에서 감지 입력을 만들어 문제 엣지를 찾는다. 핸들 좌표는 면의 중앙으로 근사한다(힌트 용도).
 * `selfAvoiding(edge)`가 참이면 그 엣지는 노드를 피해 그려지므로 가로지름은 검사하지 않는다.
 */
export function troubleOfModel(
  nodes: readonly FlowNode[],
  edges: readonly FlowEdge[],
  size: ReadonlyMap<string, { width: number; height: number }>,
  selfAvoiding: (e: FlowEdge) => boolean = () => false,
): EdgeTrouble[] {
  const rects = new Map(nodes.map((n) => [n.id, nodeRect(n, size)]));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const troubleEdges: TroubleEdge[] = [];
  for (const e of edges) {
    const sr = rects.get(e.source);
    const tr = rects.get(e.target);
    const sn = byId.get(e.source);
    const tn = byId.get(e.target);
    const sp = parseHandleId(e.sourceHandle);
    const tp = parseHandleId(e.targetHandle);
    if (sr === undefined || tr === undefined || sn === undefined || tn === undefined || sp === undefined || tp === undefined || e.data === undefined) continue;
    const s = anchor(sr, sn.data.outputs.find((p) => p.id === sp.port)?.side ?? "right");
    const t = anchor(tr, tn.data.inputs.find((p) => p.id === tp.port)?.side ?? "left");
    const built = buildEdgePath({
      source: s,
      target: t,
      waypoints: e.data.waypoints ?? null,
      shape: e.data.shape.route !== undefined ? ROUTE_PLACEHOLDER_SHAPE : e.data.shape,
      radius: e.data.radius ?? null,
      bend: e.data.bend ?? null,
    });
    troubleEdges.push({ id: e.id, sourceNode: e.source, targetNode: e.target, source: s, target: t, segments: built.segments, ...(selfAvoiding(e) ? { selfAvoiding: true } : {}) });
  }
  return detectEdgeTrouble([...rects.values()], troubleEdges);
}

/**
 * 자동 경로 엣지는 라우터가 노드를 피해 그리므로 가로지름 검사에서 뺀다. 단 라우터가 대체 경로로 물러난 엣지(`fallback`)는 검사한다.
 * `routes`는 `useAutoRoutes` 결과(계산 전이면 비어 있어도 자동 경로 엣지는 뺀다).
 */
export const selfAvoidingOf =
  (routes: ReadonlyMap<string, RoutedEdge> | undefined) =>
  (e: FlowEdge): boolean =>
    e.data?.shape.route !== undefined && routes?.get(e.id)?.fallback !== true;

/**
 * 편집 모드에서 모델이 `settleMs` 동안 바뀌지 않으면 노드를 지나는 연결선 id를 알려 준다(감싸기만 하는 연결은 세지 않는다).
 * 노드 크기가 아직 측정되지 않았으면(`ready=false`) 계산하지 않는다. 같은 결과면 같은 배열을 돌려줘 불필요한 렌더를 피한다.
 */
export function useEdgeTrouble(args: { enabled: boolean; ready: boolean; nodes: readonly FlowNode[]; edges: readonly FlowEdge[]; size: ReadonlyMap<string, { width: number; height: number }>; settleMs?: number; routes?: ReadonlyMap<string, RoutedEdge> }): readonly string[] {
  const { enabled, ready, nodes, edges, size, settleMs = TROUBLE_SETTLE_MS, routes } = args;
  const [ids, setIds] = useState<readonly string[]>(NO_IDS);
  useEffect(() => {
    if (!enabled || !ready) return;
    const h = setTimeout(() => {
      const next = troubleOfModel(nodes, edges, size, selfAvoidingOf(routes))
        .filter((t) => t.reasons.includes("crosses-node") || t.reasons.includes("crosses-own-node"))
        .map((t) => t.edgeId);
      setIds((cur) => (cur.length === next.length && cur.every((v, k) => v === next[k]) ? cur : next));
    }, settleMs);
    return () => clearTimeout(h);
  }, [enabled, ready, nodes, edges, size, settleMs, routes]);
  return enabled && ready ? ids : NO_IDS;
}

const NO_IDS: readonly string[] = [];
