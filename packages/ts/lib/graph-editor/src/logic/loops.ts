import type { EdgeSpec, EdgeTypeDescriptor, Graph } from "@agent-console/contracts";

const edgesOf = (g: Graph): EdgeSpec[] => g.edges ?? [];

interface KindInfo {
  cycle: boolean;
  flow: boolean;
}

/** 연결 종류 id → 속성(최신 버전). 모르는 종류는 사이클이 아닌 흐름 연결로 본다(서버 `loop_regions`·`validate_graph`와 같다). */
function kindInfo(edgeTypes: readonly EdgeTypeDescriptor[]): (kind: string) => KindInfo {
  const byId = new Map<string, EdgeTypeDescriptor>();
  for (const t of edgeTypes) {
    const cur = byId.get(t.id);
    if (cur === undefined || (t.version ?? 0) >= (cur.version ?? 0)) byId.set(t.id, t);
  }
  return (kind) => {
    const d = byId.get(kind);
    if (d === undefined) return { cycle: false, flow: true };
    return { cycle: d.cycle !== null && d.cycle !== undefined, flow: (d.scheduling ?? "flow") === "flow" };
  };
}

function reach(start: string, next: ReadonlyMap<string, readonly string[]>): Set<string> {
  const found = new Set([start]);
  const work = [start];
  while (work.length > 0) {
    const cur = work.pop() as string;
    for (const n of next.get(cur) ?? []) {
      if (!found.has(n)) {
        found.add(n);
        work.push(n);
      }
    }
  }
  return found;
}

/** 흐름 연결(사이클 연결 제외)의 앞·뒤 인접 목록. 없는 노드를 가리키는 연결은 뺀다. */
function adjacency(graph: Graph, info: (kind: string) => KindInfo, exclude?: string): { succ: Map<string, string[]>; pred: Map<string, string[]> } {
  const ids = new Set((graph.nodes ?? []).map((n) => n.id));
  const succ = new Map<string, string[]>();
  const pred = new Map<string, string[]>();
  for (const e of edgesOf(graph)) {
    if (e.id === exclude) continue;
    const s = e.source.node;
    const t = e.target.node;
    if (!ids.has(s) || !ids.has(t)) continue;
    const k = info(e.kind);
    if (!k.flow || k.cycle) continue;
    succ.set(s, [...(succ.get(s) ?? []), t]);
    pred.set(t, [...(pred.get(t) ?? []), s]);
  }
  return { succ, pred };
}

/**
 * 사이클 연결 하나의 반복 영역 노드 id(그래프 노드 순서). 서버 `loop_regions`와 같은 정의다:
 * 연결 `s → t`에서 `t`가 흐름 연결(사이클 연결은 모두 뺀다)로 `s`에 닿으면, 그 경로 위의 노드(`s`·`t` 포함).
 * 자기 자신으로 돌아가는 연결은 그 노드 하나. 사이클 연결이 아니거나(디스크립터 `cycle` 없음) 닫는 경로가 없으면 빈 배열.
 * 연결 종류 이름을 모르고 디스크립터 `cycle`·`scheduling`만 본다.
 */
export function loopRegion(graph: Graph, edgeTypes: readonly EdgeTypeDescriptor[], edgeId: string): string[] {
  const info = kindInfo(edgeTypes);
  const edge = edgesOf(graph).find((e) => e.id === edgeId);
  if (edge === undefined) return [];
  const k = info(edge.kind);
  if (!k.cycle || !k.flow) return [];
  const ids = new Set((graph.nodes ?? []).map((n) => n.id));
  const exit = edge.source.node;
  const entry = edge.target.node;
  if (!ids.has(exit) || !ids.has(entry)) return [];
  const { succ, pred } = adjacency(graph, info);
  const forward = reach(entry, succ);
  if (!forward.has(exit)) return [];
  const backward = reach(exit, pred);
  return (graph.nodes ?? []).map((n) => n.id).filter((id, i, all) => all.indexOf(id) === i && forward.has(id) && backward.has(id));
}

/** `closesFlowLoop`이 보는 새 연결의 최소 모양. */
export type NewEdgeLike = Pick<EdgeSpec, "kind"> & { source: { node: string }; target: { node: string } };

/**
 * 새 연결이 흐름 순환을 닫는가: 새 연결의 종류가 `scheduling = flow`이고, 도착 노드에서 출발 노드로 가는 흐름 경로
 * (사이클 연결은 뺀다)가 이미 있을 때 참. `none`/`entry`/`exit` 종류는 순환 검사 대상이 아니라 항상 거짓.
 * 자기 자신으로의 연결은 별도 규칙(`self`)이라 여기서는 참(자기 순환)으로 본다.
 */
export function closesFlowLoop(graph: Graph, newEdge: NewEdgeLike, edgeTypes: readonly EdgeTypeDescriptor[]): boolean {
  const info = kindInfo(edgeTypes);
  if (!info(newEdge.kind).flow) return false;
  const from = newEdge.target.node;
  const to = newEdge.source.node;
  if (from === to) return true;
  const { succ } = adjacency(graph, info);
  return reach(from, succ).has(to);
}
