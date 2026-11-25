/**
 * 링크 그래프 순수 함수: 서버 그래프 → 흐름 노드·엣지, 배치 엔진(elkjs stress, 결정론적), 방향키 이동, 엣지 선.
 * 노드 종류(끊긴·고아·스킴·첫 페이지·중심)는 서버 필드에서만 읽는다. 링크 문법·규칙은 모른다.
 */
import type { WikiGraph, WikiGraphEdge, WikiGraphNode } from "@agent-console/contracts/wiki";

export interface GraphNodeData extends Record<string, unknown> {
  path: string;
  title: string;
  broken: boolean;
  orphan: boolean;
  scheme: string | null;
  home: boolean;
  center: boolean;
  depth: number | null;
  /** 스크린리더 이름(제목·경로·표시) — 문구는 호출자가 채운다 */
  ariaLabel: string;
}

export interface FlowNode {
  id: string;
  width: number;
  height: number;
  position: { x: number; y: number };
  data: GraphNodeData;
}

export interface GraphEdgeData extends Record<string, unknown> {
  count: number;
  /** 중심 페이지와 닿은 엣지 */
  touchesCenter: boolean;
  /** 반대 방향 엣지가 따로 있다(두 선이 겹치지 않게 휜다) */
  paired: boolean;
  /** 같은 쌍에서 이 엣지의 휨 방향(+1/-1). 쌍이 아니면 0 */
  bend: number;
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  data: GraphEdgeData;
}

export interface GraphFlowOptions {
  /** 중심 페이지 경로(없으면 전체 보기) */
  centerPath?: string | null;
  nodeWidth?: number;
  nodeHeight?: number;
  /** 접근성 이름 만들기 */
  ariaLabelOf?: (node: WikiGraphNode, center: boolean) => string;
}

export const GRAPH_DEFAULTS = { nodeWidth: 168, nodeHeight: 36, gap: 48 } as const;

/** 서버 그래프 → 흐름 노드·엣지. 엣지가 모르는 노드를 가리키면 버린다. 순서는 경로 오름차순(배치가 같은 입력에서 같은 결과). */
export function graphToFlow(graph: WikiGraph, options: GraphFlowOptions = {}): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const w = options.nodeWidth ?? GRAPH_DEFAULTS.nodeWidth;
  const h = options.nodeHeight ?? GRAPH_DEFAULTS.nodeHeight;
  const center = options.centerPath ?? null;
  const raw = [...(graph.nodes ?? [])].sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  const seen = new Set<string>();
  const nodes: FlowNode[] = [];
  for (const n of raw) {
    if (seen.has(n.path)) continue;
    seen.add(n.path);
    const isCenter = center !== null && n.path === center;
    nodes.push({
      id: n.path,
      width: w,
      height: h,
      position: { x: 0, y: 0 },
      data: {
        path: n.path,
        title: n.title && n.title !== "" ? n.title : n.path,
        broken: n.broken === true,
        orphan: n.orphan === true,
        scheme: n.scheme ?? null,
        home: n.home === true,
        center: isCenter,
        depth: n.depth ?? null,
        ariaLabel: options.ariaLabelOf ? options.ariaLabelOf(n, isCenter) : n.title && n.title !== "" ? n.title : n.path,
      },
    });
  }
  const pairKey = (a: string, b: string): string => (a < b ? `${a}\u0000${b}` : `${b}\u0000${a}`);
  const edgeList = (graph.edges ?? []).filter((e: WikiGraphEdge) => seen.has(e.from) && seen.has(e.to));
  const directed = new Set(edgeList.map((e) => `${e.from}\u0000${e.to}`));
  const edges: FlowEdge[] = edgeList
    .map((e, i) => {
      const paired = e.from !== e.to && directed.has(`${e.to}\u0000${e.from}`);
      return {
        id: `${pairKey(e.from, e.to)}\u0000${e.from}\u0000${i}`,
        source: e.from,
        target: e.to,
        data: {
          count: e.count ?? 1,
          touchesCenter: center !== null && (e.from === center || e.to === center),
          paired,
          // 법선이 진행 방향 기준이라 두 방향 모두 +1이면 서로 반대쪽으로 휘어 겹치지 않는다
          bend: paired ? 1 : 0,
        },
      };
    })
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  return { nodes, edges };
}

/** 배치 엔진 입력/출력. */
export interface GraphLayoutInput {
  nodes: Array<{ id: string; width: number; height: number }>;
  edges: Array<{ id: string; source: string; target: string }>;
  gap: number;
  /** 중심 노드 id(있으면 층 배치의 뿌리). 없으면 연결이 가장 많은 노드 */
  center?: string | null;
}
export type GraphLayoutEngine = (input: GraphLayoutInput) => Promise<Record<string, { x: number; y: number }>>;

/** elkjs가 하는 일만 적은 모양(테스트에서 가짜를 넣는다). */
export interface ElkLike {
  layout(graph: unknown): Promise<{ children?: Array<{ id: string; x?: number; y?: number }> }>;
}

/** 노드가 이 수를 넘으면 elkjs를 쓰지 않고 값싼 층 배치(`layeredPositions`)를 쓴다(기본). stress는 허브가 있는 그래프에서 노드 수의 3제곱에 가깝게 느려져 500개에 약 50초 걸린다. */
export const ELK_MAX_NODES_DEFAULT = 80;

export interface ElkGraphLayoutOptions {
  /** 이 수를 넘는 그래프는 elkjs 없이 층 배치로 놓는다(기본 `ELK_MAX_NODES_DEFAULT`) */
  maxNodes?: number;
}

/**
 * 값싼 층 배치(O(노드+엣지), 결정론적, 겹침 없음). 뿌리(중심 또는 연결이 가장 많은 노드)에서 너비 우선으로 층을 나누고
 * 층마다 칸 격자 한 덩어리로 세로로 채워 왼쪽→오른쪽으로 쌓는다. 한 층의 노드는 부모 순서(발견 순서)로 놓여 가까운 노드가 가까이 모인다.
 * 연결되지 않은 덩어리는 이어서 새 층부터 놓는다.
 */
export function layeredPositions(
  nodes: ReadonlyArray<{ id: string; width: number; height: number }>,
  edges: ReadonlyArray<{ source: string; target: string }>,
  gap: number,
  center: string | null = null,
): Record<string, { x: number; y: number }> {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const adj = new Map<string, string[]>(nodes.map((n) => [n.id, []]));
  for (const e of edges) {
    if (e.source === e.target || !byId.has(e.source) || !byId.has(e.target)) continue;
    adj.get(e.source)?.push(e.target);
    adj.get(e.target)?.push(e.source);
  }
  for (const list of adj.values()) list.sort();
  const degree = (id: string): number => adj.get(id)?.length ?? 0;
  const rootOrder = [...nodes.map((n) => n.id)].sort((a, b) => degree(b) - degree(a) || (a < b ? -1 : a > b ? 1 : 0));
  if (center !== null && byId.has(center)) rootOrder.unshift(center);
  const layers: string[][] = [];
  const seen = new Set<string>();
  for (const root of rootOrder) {
    if (seen.has(root)) continue;
    let level = layers.length;
    let frontier = [root];
    seen.add(root);
    while (frontier.length > 0) {
      (layers[level] ??= []).push(...frontier);
      const next: string[] = [];
      for (const id of frontier) {
        for (const nb of adj.get(id) ?? []) {
          if (seen.has(nb)) continue;
          seen.add(nb);
          next.push(nb);
        }
      }
      frontier = next;
      level += 1;
    }
  }
  const cw = Math.max(...nodes.map((n) => n.width)) + gap;
  const ch = Math.max(...nodes.map((n) => n.height)) + gap / 2;
  const maxRows = Math.max(6, Math.ceil(Math.sqrt(nodes.length) * 1.2));
  const tallest = Math.min(maxRows, Math.max(...layers.map((l) => l.length)));
  const out: Record<string, { x: number; y: number }> = {};
  let x = 0;
  for (const layer of layers) {
    const rows = Math.min(maxRows, layer.length);
    const top = ((tallest - rows) * ch) / 2;
    layer.forEach((id, i) => {
      out[id] = { x: x + Math.floor(i / rows) * cw, y: top + (i % rows) * ch };
    });
    x += Math.ceil(layer.length / rows) * cw + gap;
  }
  return out;
}

/** elkjs `stress` 배치 엔진(작은 그래프) + 큰 그래프는 층 배치. elkjs는 처음 배치할 때만 불러온다. 같은 입력 = 같은 배치(시드 고정). */
export function createElkGraphLayout(load?: () => Promise<ElkLike>, options: ElkGraphLayoutOptions = {}): GraphLayoutEngine {
  const maxNodes = options.maxNodes ?? ELK_MAX_NODES_DEFAULT;
  let instance: Promise<ElkLike> | undefined;
  const getElk = (): Promise<ElkLike> => {
    instance ??=
      load?.() ??
      import("elkjs/lib/elk.bundled.js").then((m) => {
        const Ctor = (m as unknown as { default: new () => ElkLike }).default;
        return new Ctor();
      });
    return instance;
  };
  return async (input) => {
    if (input.nodes.length > maxNodes) return layeredPositions(input.nodes, input.edges, input.gap, input.center ?? null);
    const elk = await getElk();
    const out = await elk.layout({
      id: "wiki-link-graph",
      layoutOptions: {
        "elk.algorithm": "stress",
        "elk.stress.desiredEdgeLength": String(GRAPH_DEFAULTS.nodeWidth + input.gap),
        "elk.spacing.nodeNode": String(input.gap),
        "elk.randomSeed": "1",
      },
      children: input.nodes.map((n) => ({ id: n.id, width: n.width, height: n.height })),
      edges: input.edges.map((e) => ({ id: e.id, sources: [e.source], targets: [e.target] })),
    });
    const positions: Record<string, { x: number; y: number }> = {};
    for (const c of out.children ?? []) positions[c.id] = { x: c.x ?? 0, y: c.y ?? 0 };
    // stress는 노드 크기를 무시해 노드가 많으면 겹친다. 겹침이 있을 때만 격자 칸으로 풀어 준다.
    return removeOverlaps(input.nodes, positions, input.gap);
  };
}

/** 두 사각형이 `margin`보다 가깝게 겹치는가. */
function overlaps(a: { x: number; y: number; w: number; h: number }, b: { x: number; y: number; w: number; h: number }, margin: number): boolean {
  return a.x < b.x + b.w + margin && b.x < a.x + a.w + margin && a.y < b.y + b.h + margin && b.y < a.y + a.h + margin;
}

/**
 * 배치에서 겹친 노드를 푼다(결정론적). 겹침이 없으면 입력을 그대로 돌려준다. 있으면 노드를 (y, x, id) 순으로 훑으며
 * 원래 위치에 가장 가까운 빈 격자 칸(칸 크기 = 가장 큰 노드 + 간격의 절반)에 놓는다. 위치 순서·대략의 모양은 유지된다.
 * 노드가 `maxNodes`(기본 5000)를 넘으면 검사 비용 때문에 손대지 않는다.
 */
export function removeOverlaps(
  nodes: ReadonlyArray<{ id: string; width: number; height: number }>,
  positions: Record<string, { x: number; y: number }>,
  gap: number,
  maxNodes = 5000,
): Record<string, { x: number; y: number }> {
  if (nodes.length < 2 || nodes.length > maxNodes) return positions;
  const margin = Math.max(0, gap / 4);
  const boxes = nodes.map((n) => ({ id: n.id, x: positions[n.id]?.x ?? 0, y: positions[n.id]?.y ?? 0, w: n.width, h: n.height }));
  let any = false;
  for (let i = 0; i < boxes.length && !any; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      if (overlaps(boxes[i] as (typeof boxes)[number], boxes[j] as (typeof boxes)[number], margin)) {
        any = true;
        break;
      }
    }
  }
  if (!any) return positions;
  const cw = Math.max(...boxes.map((b) => b.w)) + margin * 2;
  const ch = Math.max(...boxes.map((b) => b.h)) + margin * 2;
  const taken = new Set<string>();
  const out: Record<string, { x: number; y: number }> = { ...positions };
  const order = [...boxes].sort((a, b) => a.y - b.y || a.x - b.x || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  for (const b of order) {
    const cx = Math.round(b.x / cw);
    const cy = Math.round(b.y / ch);
    let best: { col: number; row: number } | null = null;
    // 가까운 고리부터 찾고, 같은 고리 안에서는 원래 위치와의 거리가 가장 짧은 칸(같으면 위·왼쪽)
    for (let r = 0; best === null; r += 1) {
      let bestD = Infinity;
      for (let dy = -r; dy <= r; dy += 1) {
        for (let dx = -r; dx <= r; dx += 1) {
          if (Math.max(Math.abs(dx), Math.abs(dy)) !== r || taken.has(`${cx + dx},${cy + dy}`)) continue;
          const d = Math.hypot((cx + dx) * cw - b.x, (cy + dy) * ch - b.y);
          if (d < bestD) {
            bestD = d;
            best = { col: cx + dx, row: cy + dy };
          }
        }
      }
    }
    taken.add(`${best.col},${best.row}`);
    out[b.id] = { x: best.col * cw, y: best.row * ch };
  }
  return out;
}

/** 배치를 못 쓸 때의 격자 배치(결정론적). */
export function gridPositions(nodes: ReadonlyArray<{ id: string; width: number; height: number }>, gap: number): Record<string, { x: number; y: number }> {
  const cols = Math.max(1, Math.ceil(Math.sqrt(nodes.length)));
  const out: Record<string, { x: number; y: number }> = {};
  nodes.forEach((n, i) => {
    out[n.id] = { x: (i % cols) * (n.width + gap), y: Math.floor(i / cols) * (n.height + gap) };
  });
  return out;
}

export type ArrowDirection = "left" | "right" | "up" | "down";

/**
 * 방향키 이동: `from`에서 그 방향에 있는 가장 가까운 노드. 방향 안은 90도 부채꼴(축 쪽 거리 ≥ 다른 축 거리)이고
 * 거리는 중심 사이 유클리드 거리. 없으면 null(무시).
 */
export function nearestNode(
  centers: ReadonlyArray<{ id: string; x: number; y: number }>,
  fromId: string,
  dir: ArrowDirection,
): string | null {
  const from = centers.find((c) => c.id === fromId);
  if (!from) return null;
  let best: { id: string; d: number } | null = null;
  for (const c of centers) {
    if (c.id === fromId) continue;
    const dx = c.x - from.x;
    const dy = c.y - from.y;
    const inCone =
      dir === "right" ? dx > 0 && dx >= Math.abs(dy) : dir === "left" ? dx < 0 && -dx >= Math.abs(dy) : dir === "down" ? dy > 0 && dy >= Math.abs(dx) : dy < 0 && -dy >= Math.abs(dx);
    if (!inCone) continue;
    const d = Math.hypot(dx, dy);
    if (best === null || d < best.d || (d === best.d && c.id < best.id)) best = { id: c.id, d };
  }
  return best?.id ?? null;
}

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** 사각형 중심에서 `toward` 방향으로 나가는 선이 경계와 만나는 점(+`gap`만큼 바깥). */
export function boundaryPoint(box: Box, toward: { x: number; y: number }, gap = 4): { x: number; y: number } {
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  const dx = toward.x - cx;
  const dy = toward.y - cy;
  if (dx === 0 && dy === 0) return { x: cx, y: cy };
  const hw = box.width / 2 + gap;
  const hh = box.height / 2 + gap;
  const t = Math.min(dx === 0 ? Infinity : hw / Math.abs(dx), dy === 0 ? Infinity : hh / Math.abs(dy));
  return { x: cx + dx * t, y: cy + dy * t };
}

/** 엣지 선: 두 노드 경계(4px 바깥) 사이 2차 곡선. `bend`가 0이 아니면 수직으로 ±`offset` 휜다. 라벨 위치(`mid`)와 화살촉 방향 포함. */
export function edgeGeometry(
  a: Box,
  b: Box,
  bend: number,
  offset = 12,
  gap = 4,
): { path: string; mid: { x: number; y: number }; start: { x: number; y: number }; end: { x: number; y: number } } {
  const ca = { x: a.x + a.width / 2, y: a.y + a.height / 2 };
  const cb = { x: b.x + b.width / 2, y: b.y + b.height / 2 };
  const len = Math.hypot(cb.x - ca.x, cb.y - ca.y) || 1;
  const nx = -(cb.y - ca.y) / len;
  const ny = (cb.x - ca.x) / len;
  const ctrl = { x: (ca.x + cb.x) / 2 + nx * offset * 2 * bend, y: (ca.y + cb.y) / 2 + ny * offset * 2 * bend };
  const start = boundaryPoint(a, bend === 0 ? cb : ctrl, gap);
  const end = boundaryPoint(b, bend === 0 ? ca : ctrl, gap);
  const mid = { x: (start.x + 2 * ctrl.x + end.x) / 4, y: (start.y + 2 * ctrl.y + end.y) / 4 };
  const path = bend === 0 ? `M ${start.x} ${start.y} L ${end.x} ${end.y}` : `M ${start.x} ${start.y} Q ${ctrl.x} ${ctrl.y} ${end.x} ${end.y}`;
  return { path, mid: bend === 0 ? { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 } : mid, start, end };
}
