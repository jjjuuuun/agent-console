/**
 * [정리] 계산의 순수 부분(graph-edges §4.1): 편집기 상태 → 배치 요청, 배치 결과 → 새 그래프.
 * 배치 라이브러리·React·DOM에 의존하지 않는다.
 */
import type { EdgeSpec, Graph } from "@agent-console/contracts";
import type { LayoutEdgeInput, LayoutNodeInput, LayoutRequest, LayoutResult, OptionValues } from "../layout/types";
import type { Side } from "../shapes/types";
import { RESET_PATH_PATCH, patchEdgeLayout } from "./edgeLayoutOps";
import { patchGraphUiLayout, patchNodeLayout } from "./nodeLayoutOps";
import { edgesOf, moveNodes, nodesOf, snap } from "./ops";
import type { Point } from "./ops";
import type { DirectionSides } from "./layout";
import type { PortView } from "./ports";

/** 배치 입력으로 쓸 화면 노드 하나(크기·포트 면은 화면이 결정한 값). */
export interface TidyNodeView {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  inputs: readonly PortView[];
  outputs: readonly PortView[];
}

export interface BuildLayoutRequestInput {
  nodes: readonly TidyNodeView[];
  edges: readonly EdgeSpec[];
  /** 배치할 노드 id. `null` = 전체 */
  scope: ReadonlySet<string> | null;
  /** 층 계산에서 뺄 엣지 종류 */
  excludedKinds: ReadonlySet<string>;
  /** 되돌아가는 연결로 다룰 엣지 종류(디스크립터 `cycle`을 가진 종류). 생략 = 없음 */
  backKinds?: ReadonlySet<string>;
  flow: Side;
  options: OptionValues;
}

/** 배치 범위의 노드·엣지만 담은 요청을 만든다. 범위 밖 노드는 고정이므로 입력에 넣지 않는다. */
export function buildLayoutRequest(i: BuildLayoutRequestInput): LayoutRequest {
  const inScope = (id: string): boolean => i.scope === null || i.scope.has(id);
  const nodes: LayoutNodeInput[] = i.nodes
    .filter((n) => inScope(n.id))
    .map((n) => ({
      id: n.id,
      x: n.x,
      y: n.y,
      width: n.width,
      height: n.height,
      ports: [
        ...n.inputs.map((p) => ({ id: p.id, io: "in" as const, side: p.side ?? "left" })),
        ...n.outputs.map((p) => ({ id: p.id, io: "out" as const, side: p.side ?? "right" })),
      ],
    }));
  const ids = new Set(nodes.map((n) => n.id));
  const edges: LayoutEdgeInput[] = i.edges
    .filter((e) => !i.excludedKinds.has(e.kind) && ids.has(e.source.node) && ids.has(e.target.node))
    .map((e) => ({
      id: e.id,
      kind: e.kind,
      source: { node: e.source.node, port: e.source.port },
      target: { node: e.target.node, port: e.target.port },
      ...(i.backKinds?.has(e.kind) === true ? { back: true } : {}),
    }));
  return { nodes, edges, flow: i.flow, options: i.options };
}

/** 방향 id → 흐름이 나아가는 면(= 그 방향의 출력 면). 모르는 방향이면 `null`. */
export const flowSideOf = (directions: DirectionSides, directionId: string): Side | null => directions[directionId]?.out ?? null;

/**
 * 엔진 결과를 화면 좌표로 옮긴다: 결과 묶음의 좌상단을 계산 전 좌상단에 맞추고(범위가 전체여도 같음) 격자에 맞춘다.
 * 결과에 없는 노드는 제외한다.
 */
export function anchorPositions(
  result: LayoutResult,
  before: readonly Pick<TidyNodeView, "id" | "x" | "y">[],
  grid: number | false,
): Map<string, Point> {
  const ids = Object.keys(result.positions);
  const out = new Map<string, Point>();
  const original = before.filter((n) => result.positions[n.id] !== undefined);
  if (ids.length === 0 || original.length === 0) return out;
  const minNew = { x: Math.min(...ids.map((id) => (result.positions[id] as Point).x)), y: Math.min(...ids.map((id) => (result.positions[id] as Point).y)) };
  const minOld = { x: Math.min(...original.map((n) => n.x)), y: Math.min(...original.map((n) => n.y)) };
  for (const id of ids) {
    const p = result.positions[id] as Point;
    out.set(id, snap({ x: minOld.x + (p.x - minNew.x), y: minOld.y + (p.y - minNew.y) }, grid));
  }
  return out;
}

/** 적용 옵션. 생략한 항목은 그래프를 바꾸지 않는다. */
export interface ApplyTidyInput {
  positions: ReadonlyMap<string, Point>;
  /** `graph.ui.layout.direction`에 기록할 방향 id */
  direction?: string;
  /** `graph.ui.layout.edge_shape`: 문자열 = 설정, `null` = 지움(상속) */
  edgeShape?: string | null;
  /** 종류별 모양 변경분: 문자열 = 설정, `null` = 그 종류 지움 */
  edgeShapeByKind?: Readonly<Record<string, string | null>>;
  /** 범위 안 엣지의 경유점·꺾임·라벨 위치를 지운다 */
  resetRoutes: boolean;
  /** 범위 안 노드의 개별 방향(`layout.direction`)을 지워 그래프 방향을 따르게 한다 */
  alignNodeDirection: boolean;
  /** 범위(`null` = 전체). 경로·방향 정리의 대상을 정한다 */
  scope: ReadonlySet<string> | null;
}

/** 한 번의 [적용]이 만드는 그래프. 노드 이동 + 선택한 정리 + `ui.layout` 기록을 한 번에 묶는다. */
export function applyTidy(graph: Graph, i: ApplyTidyInput): Graph {
  let g = moveNodes(graph, i.positions);
  const inScope = (id: string): boolean => i.scope === null || i.scope.has(id);
  if (i.resetRoutes) {
    for (const e of edgesOf(g)) if (inScope(e.source.node) && inScope(e.target.node)) g = patchEdgeLayout(g, e.id, RESET_PATH_PATCH);
  }
  if (i.alignNodeDirection) {
    for (const n of nodesOf(g)) if (inScope(n.id) && n.layout?.direction !== undefined && n.layout.direction !== null) g = patchNodeLayout(g, n.id, { direction: null });
  }
  const ui: Record<string, unknown> = {};
  if (i.direction !== undefined) ui["direction"] = i.direction;
  if (i.edgeShape !== undefined) ui["edge_shape"] = i.edgeShape;
  if (i.edgeShapeByKind !== undefined) {
    const current = { ...((g.ui?.["layout"] as { edge_shape_by_kind?: Record<string, string> | null } | undefined)?.edge_shape_by_kind ?? {}) };
    for (const [k, v] of Object.entries(i.edgeShapeByKind)) {
      if (v === null) delete current[k];
      else current[k] = v;
    }
    ui["edge_shape_by_kind"] = Object.keys(current).length > 0 ? current : null;
  }
  return Object.keys(ui).length > 0 ? patchGraphUiLayout(g, ui) : g;
}

/** 모든 연결선의 경유점·꺾임·라벨 위치를 지운다(모양은 유지, §2.5). 바꿀 것이 없으면 같은 그래프를 돌려준다. */
export function resetAllEdgePaths(graph: Graph): Graph {
  let g = graph;
  for (const e of edgesOf(graph)) {
    const l = e.layout;
    if (l?.waypoints != null || l?.bend != null || l?.label_t != null || l?.label_offset != null) g = patchEdgeLayout(g, e.id, RESET_PATH_PATCH);
  }
  return g;
}

/** 경로 초기화 대상 엣지 수(확인 문구용). */
export function countEdgePaths(graph: Graph): number {
  return edgesOf(graph).filter((e) => e.layout?.waypoints != null || e.layout?.bend != null || e.layout?.label_t != null || e.layout?.label_offset != null).length;
}

