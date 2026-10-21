import type { Agent, BackendDescriptor, Graph, NodeSpec, NodeTypeDescriptor } from "@agent-console/contracts";
import { effectiveBackendId } from "./effective";
import type { UnresolvedBackend } from "./unresolved";

export interface BackendPrecheckInput {
  graph: Graph;
  nodeTypes: readonly NodeTypeDescriptor[];
  /** 에이전트 정의 목록(노드 설정의 정의 id로 찾는다) */
  agents: readonly Agent[];
  /** 공통 설정 `agent_defaults.backend` */
  defaultBackend: string | null | undefined;
  /** 고를 수 있는 백엔드(서버 디스크립터) */
  options: readonly BackendDescriptor[];
}

/**
 * 실행 전 백엔드 사전 점검(서버 `backend.unresolved`와 같은 해석 순서의 클라이언트 쪽 근사).
 * 정의(`binds`)에 묶인 실행 가능 노드 중 묶인 정의가 에이전트 목록에 있고 해석된 백엔드가 비어 있는 노드의 화면 이름을 모은다.
 * 서버 응답과 같은 모양(`UnresolvedBackend`)이라 해결 카드(`BackendChooserCard`)에 그대로 넘긴다. 문제가 없으면 undefined.
 */
export function precheckBackends({ graph, nodeTypes, agents, defaultBackend, options }: BackendPrecheckInput): UnresolvedBackend | undefined {
  const typeById = new Map(nodeTypes.map((t) => [t.id, t]));
  const agentById = new Map(agents.map((a) => [a.id, a]));
  const teamBackend = (graph.settings as Record<string, unknown> | null | undefined)?.["backend"];
  const labels: string[] = [];
  for (const node of (graph.nodes ?? []) as NodeSpec[]) {
    const binds = typeById.get(node.type)?.binds;
    if (binds == null || typeById.get(node.type)?.executable === false) continue;
    const ref = node.config?.[binds.field];
    const agent = typeof ref === "string" ? agentById.get(ref) : undefined;
    if (agent === undefined || (agent.kind !== undefined && agent.kind !== binds.kind)) continue;
    if (effectiveBackendId(agent, node, defaultBackend, teamBackend) === undefined) labels.push(node.label ?? agent.name ?? node.id);
  }
  return labels.length === 0 ? undefined : { labels, options: [...options] };
}
