import type { EdgeSpec, EdgeTypeDescriptor, Graph, NodeSpec, NodeTypeDescriptor } from "@agent-console/contracts";
import { closesFlowLoop } from "./loops";

/** 편집 연산: 모두 입력 그래프를 바꾸지 않고 새 그래프를 돌려주는 순수 함수. 모르는 필드는 그대로 통과한다. */

export type IdFactory = (prefix: string, existing: Set<string>) => string;

/** 기본 id 생성: prefix + 안 쓰는 가장 작은 양의 정수(n1, n2 …). 시간·난수 미사용. */
export const defaultIdFactory: IdFactory = (prefix, existing) => {
  let i = 1;
  while (existing.has(`${prefix}${i}`)) i += 1;
  return `${prefix}${i}`;
};

export const nodesOf = (g: Graph): NodeSpec[] => g.nodes ?? [];
export const edgesOf = (g: Graph): EdgeSpec[] => g.edges ?? [];

/** 같은 label이 있으면 " 2", " 3" 접미를 붙여 유일하게 만든다. */
export function uniqueLabel(base: string, existing: readonly (string | null | undefined)[]): string {
  const used = new Set(existing);
  if (!used.has(base)) return base;
  let i = 2;
  while (used.has(`${base} ${i}`)) i += 1;
  return `${base} ${i}`;
}

/** JSON Schema의 `default`로 객체를 채운다(중첩 object 재귀). 해석 못 하면 {}. */
export function defaultsFromSchema(schema: unknown): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  if (schema === null || typeof schema !== "object") return out;
  const props = (schema as { properties?: unknown }).properties;
  if (props === null || typeof props !== "object") return out;
  for (const [key, sub] of Object.entries(props as Record<string, unknown>)) {
    if (sub === null || typeof sub !== "object") continue;
    const s = sub as { default?: unknown; type?: unknown; properties?: unknown };
    if ("default" in s) out[key] = structuredClone(s.default);
    else if (s.type === "object" && s.properties !== undefined) {
      const nested = defaultsFromSchema(s);
      if (Object.keys(nested).length > 0) out[key] = nested;
    }
  }
  return out;
}

export interface Point {
  x: number;
  y: number;
}

export const snap = (p: Point, grid: number | false): Point =>
  grid === false || grid <= 0 ? p : { x: Math.round(p.x / grid) * grid, y: Math.round(p.y / grid) * grid };

/** 새 노드 기본 배치에서 가로 간격(노드 폭 + 여백)과 겹침 판정 크기. */
const X_STEP = 300;
const Y_STEP = 120;
/** 카드 실제 크기에 가까운 겹침 판정 크기(중앙 배치용) */
const CARD_W = 260;
const CARD_H = 170;

/**
 * 위치를 안 줬을 때의 기본 배치: 기준 노드(`anchorId`, 없으면 가장 오른쪽 노드)의 오른쪽,
 * 다른 노드와 겹치면 아래로 밀어 빈 자리를 찾는다. 노드가 없으면 (0, 0). 왼쪽 -> 오른쪽 흐름.
 */
export function nextFreePosition(g: Graph, grid: number | false = 8, anchorId?: string): Point {
  const nodes = nodesOf(g);
  if (nodes.length === 0) return { x: 0, y: 0 };
  const at = (n: (typeof nodes)[number]) => ({ x: n.position?.x ?? 0, y: n.position?.y ?? 0 });
  let anchor = nodes.find((n) => n.id === anchorId);
  if (anchor === undefined) anchor = nodes.reduce((a, b) => (at(b).x >= at(a).x ? b : a));
  const base = at(anchor);
  let y = base.y;
  const x = base.x + X_STEP;
  const overlaps = (cy: number) => nodes.some((n) => Math.abs(at(n).x - x) < X_STEP - 40 && Math.abs(at(n).y - cy) < Y_STEP);
  while (overlaps(y)) y += Y_STEP;
  return snap({ x, y }, grid);
}

/**
 * 보이는 영역 중앙(`center`, 노드 왼쪽 위 기준 좌표)에 놓되, 다른 노드와 겹치면 (격자, 격자)씩 대각선으로 밀어 빈 자리를 찾는다.
 * 격자가 없으면(false) 8px. 겹침 판정은 `nextFreePosition`과 같은 크기. 최대 200번 밀면 마지막 후보를 쓴다.
 */
export function centerFreePosition(g: Graph, center: Point, grid: number | false = 8): Point {
  const step = grid === false || grid <= 0 ? 8 : grid;
  const nodes = nodesOf(g);
  const at = (n: (typeof nodes)[number]) => ({ x: n.position?.x ?? 0, y: n.position?.y ?? 0 });
  const base = snap(center, grid);
  let pos = base;
  for (let i = 0; i < 200; i++) {
    const hit = nodes.some((n) => Math.abs(at(n).x - pos.x) < CARD_W && Math.abs(at(n).y - pos.y) < CARD_H);
    if (!hit) return pos;
    pos = { x: base.x + step * (i + 1), y: base.y + step * (i + 1) };
  }
  return pos;
}

export interface AddNodeInput {
  descriptor: NodeTypeDescriptor;
  position?: Point;
  idFactory?: IdFactory;
  grid?: number | false;
  /** 위치를 안 줬을 때 이 노드의 오른쪽에 둔다(보통 선택된 노드) */
  anchorId?: string;
  /** 정의에서 만드는 노드(`binds`): label = 정의 이름, `config[binds.field]` = 정의 id */
  definition?: { id: string; name: string };
}

/**
 * 팔레트에서 노드 추가. label=디스크립터 title(중복 시 접미).
 * config는 비워 둔다: 스키마 기본값을 저장 문서에 채우지 않는다(생략 = 기본/상속, 사용자가 정한 값만 저장).
 */
export function addNode(g: Graph, input: AddNodeInput): { graph: Graph; nodeId: string } {
  const nodes = nodesOf(g);
  const id = (input.idFactory ?? defaultIdFactory)("n", new Set(nodes.map((n) => n.id)));
  const d = input.descriptor;
  const node: NodeSpec = {
    id,
    type: d.id,
    label: uniqueLabel(input.definition?.name ?? d.title, nodes.map((n) => n.label)),
    position: input.position ?? nextFreePosition(g, input.grid ?? 8, input.anchorId),
  };
  if (d.version !== undefined) node.type_version = d.version;
  if (input.definition !== undefined && d.binds !== null && d.binds !== undefined) {
    node.config = { ...(node.config ?? {}), [d.binds.field]: input.definition.id };
  }
  return { graph: { ...g, nodes: [...nodes, node] }, nodeId: id };
}

/** 선택 노드·엣지 삭제. 노드에 붙은 엣지도 함께 지운다. */
export function removeSelection(g: Graph, sel: { nodeIds: readonly string[]; edgeIds: readonly string[] }): Graph {
  const nodeIds = new Set(sel.nodeIds);
  const edgeIds = new Set(sel.edgeIds);
  return {
    ...g,
    nodes: nodesOf(g).filter((n) => !nodeIds.has(n.id)),
    edges: edgesOf(g).filter((e) => !edgeIds.has(e.id) && !nodeIds.has(e.source.node) && !nodeIds.has(e.target.node)),
  };
}

/** 노드 위치 갱신(드롭 시점 1회). */
export function moveNodes(g: Graph, positions: ReadonlyMap<string, Point>): Graph {
  return {
    ...g,
    nodes: nodesOf(g).map((n) => {
      const p = positions.get(n.id);
      return p === undefined ? n : { ...n, position: { ...(n.position ?? {}), x: p.x, y: p.y } };
    }),
  };
}

/** 선택 노드 복제(+ 선택 노드 사이 엣지). 새 노드는 (+24,+24) 오프셋. */
export function duplicateNodes(
  g: Graph,
  nodeIds: readonly string[],
  idFactory: IdFactory = defaultIdFactory,
  offset = 24,
): { graph: Graph; newNodeIds: string[] } {
  const nodes = nodesOf(g);
  const edges = edgesOf(g);
  const selected = new Set(nodeIds);
  const usedNode = new Set(nodes.map((n) => n.id));
  const usedEdge = new Set(edges.map((e) => e.id));
  const labels: (string | null | undefined)[] = nodes.map((n) => n.label);
  const map = new Map<string, string>();
  const copies: NodeSpec[] = [];
  for (const n of nodes) {
    if (!selected.has(n.id)) continue;
    const id = idFactory("n", usedNode);
    usedNode.add(id);
    map.set(n.id, id);
    const label = n.label === null || n.label === undefined ? n.label : uniqueLabel(n.label, labels);
    labels.push(label);
    const copy = structuredClone(n);
    copy.id = id;
    if (label !== undefined) copy.label = label;
    copy.position = { ...(n.position ?? {}), x: (n.position?.x ?? 0) + offset, y: (n.position?.y ?? 0) + offset };
    copies.push(copy);
  }
  const edgeCopies: EdgeSpec[] = [];
  for (const e of edges) {
    const s = map.get(e.source.node);
    const t = map.get(e.target.node);
    if (s === undefined || t === undefined) continue;
    const id = idFactory("e", usedEdge);
    usedEdge.add(id);
    const copy = structuredClone(e);
    copy.id = id;
    copy.source = { ...e.source, node: s };
    copy.target = { ...e.target, node: t };
    edgeCopies.push(copy);
  }
  return {
    graph: { ...g, nodes: [...nodes, ...copies], edges: [...edges, ...edgeCopies] },
    newNodeIds: copies.map((c) => c.id),
  };
}

/** source에서 target으로 가는 경로가 있는가(엣지 방향 기준). */
export function hasPath(g: Graph, from: string, to: string, include: (e: EdgeSpec) => boolean = () => true): boolean {
  const next = new Map<string, string[]>();
  for (const e of edgesOf(g)) {
    if (!include(e)) continue;
    const list = next.get(e.source.node) ?? [];
    list.push(e.target.node);
    next.set(e.source.node, list);
  }
  const seen = new Set<string>();
  const stack = [from];
  while (stack.length > 0) {
    const cur = stack.pop() as string;
    if (cur === to) return true;
    if (seen.has(cur)) continue;
    seen.add(cur);
    for (const n of next.get(cur) ?? []) stack.push(n);
  }
  return false;
}

export interface Connection {
  source: { node: string; port: string };
  target: { node: string; port: string };
}

export type ConnectionCheck =
  | { ok: true }
  | { ok: false; reason: "self" | "cycle" | "port" }
  | { ok: false; reason: "duplicate"; existingEdgeId: string };

/** 노드 id → 알려진 포트 이름 목록(모르면 undefined). */
export type PortLookup = (nodeId: string) => { inputs: readonly string[]; outputs: readonly string[] } | undefined;

/** 엣지 종류의 스케줄링 값. 디스크립터가 없거나 생략되면 `flow`. */
export function schedulingOf(kind: EdgeTypeDescriptor | undefined): string {
  return kind?.scheduling ?? "flow";
}

/** 연결 검사에 종류를 알려 주는 선택 인자. 있으면 순환·중복을 디스크립터 `scheduling`/종류로 판단한다. */
export interface ConnectionKindContext {
  edgeTypes: readonly EdgeTypeDescriptor[];
  kind: string;
}

/**
 * 연결 가능 여부(선택 인자 portsOf로 포트 존재·방향도 검증): 자기 연결·중복·순환 거부.
 * `ctx`가 있으면 새 종류의 `scheduling`이 `flow`일 때만 순환을 검사하고(기존 엣지도 `flow`인 것만 따라간다),
 * 중복은 같은 종류끼리만 본다. 없으면 모든 엣지를 흐름으로 보는 기존 동작.
 */
export function checkConnection(g: Graph, c: Connection, portsOf?: PortLookup, ctx?: ConnectionKindContext): ConnectionCheck {
  if (c.source.node === c.target.node) return { ok: false, reason: "self" };
  if (portsOf !== undefined) {
    // 포트 목록을 아는 노드(undefined가 아닌 경우)만 검사: 출력 포트에서 입력 포트로만 연결 가능
    const sp = portsOf(c.source.node);
    const tp = portsOf(c.target.node);
    if (sp !== undefined && !sp.outputs.includes(c.source.port)) return { ok: false, reason: "port" };
    if (tp !== undefined && !tp.inputs.includes(c.target.port)) return { ok: false, reason: "port" };
  }
  const dup = edgesOf(g).find(
    (e) =>
      (ctx === undefined || e.kind === ctx.kind) &&
      e.source.node === c.source.node &&
      e.source.port === c.source.port &&
      e.target.node === c.target.node &&
      e.target.port === c.target.port,
  );
  if (dup !== undefined) return { ok: false, reason: "duplicate", existingEdgeId: dup.id };
  if (ctx === undefined) {
    if (hasPath(g, c.target.node, c.source.node)) return { ok: false, reason: "cycle" };
  } else {
    // 사이클 연결(디스크립터 `cycle`)은 흐름 순환을 닫을 수 있다. 그 밖의 흐름 종류만 순환을 거부한다.
    const kind = ctx.edgeTypes.filter((t) => t.id === ctx.kind).reduce<EdgeTypeDescriptor | undefined>((a, b) => (a === undefined || (b.version ?? 0) >= (a.version ?? 0) ? b : a), undefined);
    const isCycleKind = kind?.cycle !== null && kind?.cycle !== undefined;
    if (!isCycleKind && closesFlowLoop(g, { kind: ctx.kind, source: c.source, target: c.target }, ctx.edgeTypes)) {
      return { ok: false, reason: "cycle" };
    }
  }
  return { ok: true };
}

/** 엣지 추가(검사는 호출자가 checkConnection으로). */
export function addEdge(
  g: Graph,
  c: Connection,
  kind: string,
  idFactory: IdFactory = defaultIdFactory,
  config?: Record<string, unknown>,
): { graph: Graph; edgeId: string } {
  const edges = edgesOf(g);
  const id = idFactory("e", new Set(edges.map((e) => e.id)));
  const edge: EdgeSpec = { id, source: { ...c.source }, target: { ...c.target }, kind };
  if (config !== undefined && Object.keys(config).length > 0) edge.config = config;
  return { graph: { ...g, edges: [...edges, edge] }, edgeId: id };
}

/**
 * 새 연결의 엣지 종류 결정. `candidateIds`는 이미 `connects`로 걸러진 후보다.
 * 하나뿐이면 자동, 없으면 none, 둘 이상이면 선택 UI(미리 선택 = `defaultKind`가 후보에 있으면 그것, 아니면 첫 항목).
 */
export function decideEdgeKind(
  candidateIds: readonly string[],
  defaultKind?: string,
): { mode: "auto"; kind: string } | { mode: "ask"; choices: string[]; preselected: string } | { mode: "none" } {
  const [first, ...rest] = candidateIds;
  if (first === undefined) return { mode: "none" };
  if (rest.length === 0) return { mode: "auto", kind: first };
  const preselected = defaultKind !== undefined && candidateIds.includes(defaultKind) ? defaultKind : first;
  return { mode: "ask", choices: [...candidateIds], preselected };
}

/** 노드 일부 필드 갱신. */
export function patchNode(g: Graph, nodeId: string, patch: Partial<NodeSpec>): Graph {
  return { ...g, nodes: nodesOf(g).map((n) => (n.id === nodeId ? { ...n, ...patch } : n)) };
}

export function patchEdge(g: Graph, edgeId: string, patch: Partial<EdgeSpec>): Graph {
  return { ...g, edges: edgesOf(g).map((e) => (e.id === edgeId ? { ...e, ...patch } : e)) };
}
