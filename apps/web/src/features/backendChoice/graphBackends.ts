import type { Agent, Graph, NodeSpec, NodeTypeDescriptor } from "@agent-console/contracts";
import { effectiveBackendId } from "./effective";

export interface GraphBackendsInput {
  graph: Graph;
  nodeTypes: readonly NodeTypeDescriptor[];
  agents: readonly Agent[];
  /** 공통 설정 `agent_defaults.backend` */
  defaultBackend: string | null | undefined;
}

/**
 * 그래프의 실행 가능 노드가 실제로 쓸 백엔드 id 집합(노드 → 에이전트 → 팀 구성 → 공통 기본값 순서).
 * 정의(`binds`)에 묶인 노드만 본다. 해석되지 않는 노드는 건너뛴다(그 문제는 `precheckBackends`가 다룬다).
 */
export function graphBackendIds({ graph, nodeTypes, agents, defaultBackend }: GraphBackendsInput): Set<string> {
  const typeById = new Map(nodeTypes.map((t) => [t.id, t]));
  const agentById = new Map(agents.map((a) => [a.id, a]));
  const teamBackend = (graph.settings as Record<string, unknown> | null | undefined)?.["backend"];
  const out = new Set<string>();
  for (const node of (graph.nodes ?? []) as NodeSpec[]) {
    const type = typeById.get(node.type);
    if (type?.binds == null || type.executable === false) continue;
    const ref = node.config?.[type.binds.field];
    const agent = typeof ref === "string" ? agentById.get(ref) : undefined;
    if (agent === undefined || (agent.kind !== undefined && agent.kind !== type.binds.kind)) continue;
    const id = effectiveBackendId(agent, node, defaultBackend, teamBackend);
    if (id !== undefined) out.add(id);
  }
  return out;
}
