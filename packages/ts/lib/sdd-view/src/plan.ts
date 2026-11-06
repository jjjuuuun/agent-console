import type { ParsedTask, TaskPlan } from "@agent-console/contracts/sdd";
import { taskTitle } from "./display";

/** 계획 그래프 노드 크기·간격(px). 값은 앱이 바꿀 수 있게 `PlanFlowOptions`로 받는다. */
export interface PlanFlowOptions {
  nodeWidth?: number;
  nodeHeight?: number;
  layerGap?: number;
  nodeGap?: number;
  /** 그릴 노드 상한. 넘으면 앞에서부터 자르고 `truncated`를 켠다. */
  maxNodes?: number;
}

export const PLAN_DEFAULTS = { nodeWidth: 176, nodeHeight: 44, layerGap: 64, nodeGap: 12, maxNodes: 300 } as const;

/** 노드에 실리는 표시 데이터. */
export interface PlanNodeData extends Record<string, unknown> {
  key: string;
  title: string;
  status: string;
  /** 0부터. 어느 묶음에도 없으면 맨 뒤 묶음 */
  layer: number;
  critical: boolean;
  ready: boolean;
  blocked: boolean;
  cycle: boolean;
}

export interface PlanNodeModel {
  id: string;
  position: { x: number; y: number };
  width: number;
  height: number;
  data: PlanNodeData;
}

export interface PlanEdgeModel {
  id: string;
  source: string;
  target: string;
  critical: boolean;
}

export interface PlanFlow {
  nodes: PlanNodeModel[];
  edges: PlanEdgeModel[];
  truncated: boolean;
}

/**
 * 계획(층·병목)과 작업 목록 → 그래프 모델(읽기 전용 그림용). 처음 좌표는 층별 열이고,
 * ELK 배치가 끝나면 `applyPositions`로 좌표만 바꾼다. 의존이 그림 안에 없는 작업을 가리키면 그 연결은 뺀다.
 */
export function planToFlow(plan: TaskPlan, tasks: readonly ParsedTask[], options: PlanFlowOptions = {}): PlanFlow {
  const o = { ...PLAN_DEFAULTS, ...options };
  const byKey = new Map(tasks.map((t) => [t.key, t] as const));
  const layerOf = new Map<string, number>();
  (plan.layers ?? []).forEach((keys, i) => keys.forEach((k) => layerOf.set(k, i)));
  const cycleKeys = new Set((plan.cycles ?? []).flat());
  const readySet = new Set(plan.ready ?? []);
  const blockedSet = new Set(plan.blocked ?? []);
  const critical = plan.critical_path ?? [];
  const criticalSet = new Set(critical);

  const order: string[] = [];
  const seen = new Set<string>();
  const add = (k: string) => {
    if (!seen.has(k) && byKey.has(k)) {
      seen.add(k);
      order.push(k);
    }
  };
  (plan.layers ?? []).forEach((keys) => keys.forEach(add));
  [...cycleKeys, ...blockedSet, ...readySet].forEach(add);

  const truncated = order.length > o.maxNodes;
  const keys = truncated ? order.slice(0, o.maxNodes) : order;
  const extraLayer = (plan.layers ?? []).length;
  const counters = new Map<number, number>();
  const nodes: PlanNodeModel[] = keys.map((key) => {
    const task = byKey.get(key) as ParsedTask;
    const layer = layerOf.get(key) ?? extraLayer;
    const row = counters.get(layer) ?? 0;
    counters.set(layer, row + 1);
    return {
      id: key,
      position: { x: layer * (o.nodeWidth + o.layerGap), y: row * (o.nodeHeight + o.nodeGap) },
      width: o.nodeWidth,
      height: o.nodeHeight,
      data: {
        key,
        title: taskTitle(task),
        status: task.status,
        layer,
        critical: criticalSet.has(key),
        ready: readySet.has(key),
        blocked: blockedSet.has(key),
        cycle: cycleKeys.has(key),
      },
    };
  });

  const present = new Set(keys);
  const criticalEdges = new Set<string>();
  for (let i = 1; i < critical.length; i += 1) criticalEdges.add(`${critical[i - 1]}\u0000${critical[i]}`);
  const edges: PlanEdgeModel[] = [];
  const seenEdges = new Set<string>();
  for (const key of keys) {
    for (const dep of byKey.get(key)?.dependencies ?? []) {
      const id = `${dep}\u0000${key}`;
      if (!present.has(dep) || dep === key || seenEdges.has(id)) continue;
      seenEdges.add(id);
      edges.push({ id: `${dep}->${key}`, source: dep, target: key, critical: criticalEdges.has(id) });
    }
  }
  return { nodes, edges, truncated };
}

/** 배치 결과(좌표)를 노드에 반영한다. 결과에 없는 노드는 처음 좌표를 유지한다. */
export function applyPositions(flow: PlanFlow, positions: Readonly<Record<string, { x: number; y: number }>>): PlanFlow {
  return { ...flow, nodes: flow.nodes.map((n) => (positions[n.id] ? { ...n, position: positions[n.id] as { x: number; y: number } } : n)) };
}

/** 배치 엔진 입력·출력(ELK 타입이 밖으로 새지 않게 한 구조). */
export interface PlanLayoutInput {
  nodes: { id: string; width: number; height: number }[];
  edges: { id: string; source: string; target: string }[];
  layerGap: number;
  nodeGap: number;
}
export type PlanLayoutEngine = (input: PlanLayoutInput) => Promise<Record<string, { x: number; y: number }>>;

interface ElkLike {
  layout(graph: unknown): Promise<{ children?: { id: string; x?: number; y?: number }[] }>;
}

/**
 * elkjs 배치 엔진(층 배치, 왼쪽→오른쪽). elkjs는 처음 배치할 때만 동적으로 불러온다.
 * `load`로 ELK 인스턴스를 직접 줄 수 있다(테스트·다른 번들 방식).
 */
export function createElkPlanLayout(load?: () => Promise<ElkLike>): PlanLayoutEngine {
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
    const elk = await getElk();
    const graph = {
      id: "sdd-plan-graph",
      layoutOptions: {
        "elk.algorithm": "layered",
        "elk.direction": "RIGHT",
        "elk.layered.spacing.nodeNodeBetweenLayers": String(input.layerGap),
        "elk.spacing.nodeNode": String(input.nodeGap),
        "elk.layered.cycleBreaking.strategy": "GREEDY",
      },
      children: input.nodes.map((n) => ({ id: n.id, width: n.width, height: n.height })),
      edges: input.edges.map((e) => ({ id: e.id, sources: [e.source], targets: [e.target] })),
    };
    const out = await elk.layout(graph);
    const positions: Record<string, { x: number; y: number }> = {};
    for (const c of out.children ?? []) positions[c.id] = { x: c.x ?? 0, y: c.y ?? 0 };
    return positions;
  };
}

/** 묶음 글 한 줄. */
export interface PlanBundle {
  /** 1부터 */
  index: number;
  keys: string[];
  titles: string[];
}

/** 계획의 층 → 묶음 글 목록(작업 키와 사람이 읽는 이름). */
export function planBundles(plan: TaskPlan, tasks: readonly ParsedTask[]): PlanBundle[] {
  const byKey = new Map(tasks.map((t) => [t.key, t] as const));
  return (plan.layers ?? []).map((keys, i) => ({
    index: i + 1,
    keys: [...keys],
    titles: keys.map((k) => {
      const t = byKey.get(k);
      return t ? taskTitle(t) : k;
    }),
  }));
}
