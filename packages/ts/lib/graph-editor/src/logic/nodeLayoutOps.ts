/**
 * 노드 `layout`(방향·포트별 면)을 고치는 순수 함수(graph-edges §3, §5.4)와, 노드를 옮길 때 엣지 경유점을 함께 옮기는 연산(§2.2).
 * React·React Flow에 의존하지 않는다. 입력은 건드리지 않고 새 값을 돌려준다.
 */
import type { EdgeSpec, Graph, GraphUiLayout, NodeLayout, NodeSpec } from "@agent-console/contracts";
import { MAX_WAYPOINTS } from "./edgePath";
import { normalizeEdgeLayout } from "./edgeLayoutOps";
import { edgesOf, moveNodes, nodesOf } from "./ops";
import type { Point } from "./ops";
import type { Side } from "../shapes/types";

/** 저장 때 `layout` 키가 놓이는 순서(diff 안정). 모르는 키는 그 뒤에 원래 순서로 붙는다. */
export const NODE_LAYOUT_KEY_ORDER = ["direction", "ports"] as const;

/** 값이 `null`/`undefined`인 키는 지운다. */
export type NodeLayoutPatch = Partial<NodeLayout>;

/**
 * `layout`을 저장 형식으로 정리한다(§5.4). 빈 `ports`·빈 문자열·`null`은 키째 삭제, 키 순서는 `NODE_LAYOUT_KEY_ORDER`,
 * 모르는 키는 그대로 통과. 모두 비면 `null`.
 */
export function normalizeNodeLayout(layout: NodeLayout | null | undefined): NodeLayout | null {
  if (layout === null || layout === undefined) return null;
  const out: NodeLayout = {};
  if (typeof layout.direction === "string" && layout.direction !== "") out.direction = layout.direction;
  if (layout.ports !== null && layout.ports !== undefined && typeof layout.ports === "object") {
    const ports = Object.fromEntries(Object.entries(layout.ports).filter(([, v]) => typeof v === "string" && v !== ""));
    if (Object.keys(ports).length > 0) out.ports = ports;
  }
  for (const [k, v] of Object.entries(layout)) {
    if ((NODE_LAYOUT_KEY_ORDER as readonly string[]).includes(k)) continue;
    if (v !== null && v !== undefined) (out as Record<string, unknown>)[k] = v;
  }
  return Object.keys(out).length === 0 ? null : out;
}

/** `patch`를 합쳐 정리한다. 패치의 `null`/`undefined`는 그 키를 지운다. */
export function applyNodeLayoutPatch(layout: NodeLayout | null | undefined, patch: NodeLayoutPatch): NodeLayout | null {
  const merged: Record<string, unknown> = { ...(layout ?? {}) };
  for (const [k, v] of Object.entries(patch)) {
    if (v === null || v === undefined) delete merged[k];
    else merged[k] = v;
  }
  return normalizeNodeLayout(merged as NodeLayout);
}

const replaceNode = (g: Graph, nodeId: string, fn: (n: NodeSpec) => NodeSpec): Graph => ({
  ...g,
  nodes: nodesOf(g).map((n) => (n.id === nodeId ? fn(n) : n)),
});

/** 노드 하나의 `layout`을 통째로 바꾼다(`null`이면 `layout` 키를 지운다). 다른 키는 그대로. */
export function setNodeLayout(g: Graph, nodeId: string, layout: NodeLayout | null): Graph {
  const next = normalizeNodeLayout(layout);
  return replaceNode(g, nodeId, (n) => {
    const { layout: _old, ...rest } = n;
    void _old;
    return (next === null ? rest : { ...rest, layout: next }) as NodeSpec;
  });
}

/** 노드 하나의 `layout`에 패치를 합친다. */
export function patchNodeLayout(g: Graph, nodeId: string, patch: NodeLayoutPatch): Graph {
  const node = nodesOf(g).find((n) => n.id === nodeId);
  if (node === undefined) return g;
  return setNodeLayout(g, nodeId, applyNodeLayoutPatch(node.layout, patch));
}

/** 여러 노드의 `layout`에 같은 패치를 합친다(다중 선택 [방향 ▾]). 바뀔 것이 없으면 같은 그래프를 돌려준다. */
export function patchNodesLayout(g: Graph, nodeIds: readonly string[], patch: NodeLayoutPatch): Graph {
  const ids = new Set(nodeIds);
  let changed = false;
  const nodes = nodesOf(g).map((n) => {
    if (!ids.has(n.id)) return n;
    const next = applyNodeLayoutPatch(n.layout, patch);
    if (JSON.stringify(next) === JSON.stringify(normalizeNodeLayout(n.layout))) return n;
    changed = true;
    const { layout: _old, ...rest } = n;
    void _old;
    return (next === null ? rest : { ...rest, layout: next }) as NodeSpec;
  });
  return changed ? { ...g, nodes } : g;
}

/** 포트 한 개의 면을 정한다(`side`가 `null`이면 그 포트 키를 지워 상속으로). 빈 `ports`는 키째 삭제된다. */
export function withPortSide(layout: NodeLayout | null | undefined, key: string, side: string | null): NodeLayout | null {
  const ports: Record<string, string> = { ...(layout?.ports ?? {}) };
  if (side === null || side === "") delete ports[key];
  else ports[key] = side;
  return applyNodeLayoutPatch(layout, { ports: Object.keys(ports).length > 0 ? ports : null });
}

/**
 * 방향 id 목록 순서로 다음/이전 값을 돌려준다. 마지막 다음과 첫 값 이전은 `null`(= 상속).
 * 현재 값이 없거나 목록에 없으면(상속·알 수 없음) 앞으로는 첫 값, 뒤로는 마지막 값.
 */
export function cycleDirection(ids: readonly string[], current: string | null | undefined, step: 1 | -1 = 1): string | null {
  if (ids.length === 0) return null;
  const at = current === null || current === undefined ? -1 : ids.indexOf(current);
  if (at < 0) return (step === 1 ? ids[0] : ids[ids.length - 1]) ?? null;
  const next = at + step;
  if (next < 0 || next >= ids.length) return null;
  return ids[next] ?? null;
}

/** 현재 포트 목록에 없는 `layout.ports` 키(포트가 사라진 경우). 데이터는 보존하고 표에 "사라진 포트"로 보인다. */
export function orphanPortKeys(layout: NodeLayout | null | undefined, live: ReadonlySet<string>): string[] {
  return Object.keys(layout?.ports ?? {}).filter((k) => !live.has(k));
}

/**
 * 핸들을 끌어 옮길 때 가장 가까운 면. 노드 상자 중심 기준 정규화 좌표에서 더 큰 축이 정한다
 * (상자 밖 어디에 놓아도 결정된다). 상자 크기가 0이면 `null`.
 */
export function nearestSide(box: { left: number; top: number; width: number; height: number }, p: Point): Side | null {
  if (box.width <= 0 || box.height <= 0) return null;
  const u = (p.x - (box.left + box.width / 2)) / box.width;
  const v = (p.y - (box.top + box.height / 2)) / box.height;
  if (Math.abs(u) >= Math.abs(v)) return u < 0 ? "left" : "right";
  return v < 0 ? "top" : "bottom";
}

const shiftEdgeWaypoints = (e: EdgeSpec, dx: number, dy: number): EdgeSpec => {
  const wps = e.layout?.waypoints;
  if (wps === undefined || wps === null || wps.length === 0) return e;
  const moved = normalizeEdgeLayout({ ...e.layout, waypoints: wps.slice(0, MAX_WAYPOINTS).map((p) => ({ x: p.x + dx, y: p.y + dy })) });
  return (moved === null ? e : { ...e, layout: moved }) as EdgeSpec;
};

/**
 * 노드를 옮긴다(`moveNodes`). 양 끝 노드가 모두 옮겨지면 그 사이 엣지의 경유점도 같은 변위만큼 옮긴다(§2.2).
 * 한쪽만 옮겨지면 경유점은 제자리(절대 좌표). 변위는 출발 노드의 변위를 쓴다(격자 스냅으로 두 노드의 변위가
 * 격자 한 칸 안에서 다를 수 있다). 변위가 0인 노드는 옮겨지지 않은 것으로 본다.
 */
export function moveNodesWithWaypoints(g: Graph, positions: ReadonlyMap<string, Point>): Graph {
  const delta = new Map<string, Point>();
  for (const n of nodesOf(g)) {
    const p = positions.get(n.id);
    if (p === undefined) continue;
    const dx = p.x - (n.position?.x ?? 0);
    const dy = p.y - (n.position?.y ?? 0);
    if (dx !== 0 || dy !== 0) delta.set(n.id, { x: dx, y: dy });
  }
  const moved = moveNodes(g, positions);
  if (delta.size < 2) return moved;
  return {
    ...moved,
    edges: edgesOf(moved).map((e) => {
      const d = delta.get(e.source.node);
      return d !== undefined && delta.has(e.target.node) ? shiftEdgeWaypoints(e, d.x, d.y) : e;
    }),
  };
}

// ---------------------------------------------------------------------------------------------
// 그래프 `ui` 병합(S4: viewport 등 다른 키를 덮어쓰지 않는다)

/** `graph.ui.layout`의 값을 읽는다(없거나 객체가 아니면 `null`). */
export function graphUiLayoutOf(g: Graph): GraphUiLayout | null {
  const v = g.ui?.["layout"];
  return v !== null && typeof v === "object" && !Array.isArray(v) ? (v as GraphUiLayout) : null;
}

/**
 * `graph.ui.layout`에 패치를 병합한다. `ui`의 다른 키(viewport 등)와 `layout`의 모르는 키는 그대로 두고,
 * 패치의 `null`/`undefined`는 그 키를 지운다. `layout`이 비면 `layout` 키를, `ui`가 비면 `ui` 키를 지운다.
 */
export function patchGraphUiLayout(g: Graph, patch: Partial<GraphUiLayout>): Graph {
  const layout: Record<string, unknown> = { ...(graphUiLayoutOf(g) ?? {}) };
  for (const [k, v] of Object.entries(patch)) {
    if (v === null || v === undefined) delete layout[k];
    else layout[k] = v;
  }
  const ui: Record<string, unknown> = { ...(g.ui ?? {}) };
  if (Object.keys(layout).length > 0) ui["layout"] = layout;
  else delete ui["layout"];
  const { ui: _old, ...rest } = g;
  void _old;
  return (Object.keys(ui).length > 0 ? { ...rest, ui } : rest) as Graph;
}
