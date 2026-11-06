/**
 * 세션별 백엔드 id(실행 상세 세션 팝오버의 백엔드 열). NodeRun·TraceSpan에는 백엔드 필드가 없어서, 실행이 쓴 그래프 스냅샷의
 * 세션을 연 노드에 유효 백엔드 선택 규칙(`effectiveBackendId`: 노드 → 에이전트 → 팀 구성 → 공통 기본값)을 적용해 구한다.
 * 실행 뒤에 에이전트 정의나 공통 기본값이 바뀌었으면 실제와 다를 수 있다(화면은 이 열을 "추정"으로 표시한다).
 * 노드 타입 id·백엔드 id는 비교하지 않는다. 정의에 묶이지 않은 노드나 해석되지 않는 세션은 결과에 없다.
 */
import type { Agent, Graph, NodeSpec, NodeTypeDescriptor } from "@agent-console/contracts";
import { effectiveBackendId } from "../backendChoice";
import type { RunSessions } from "./runSessions";

export interface SessionBackendsInput {
  sessions: RunSessions;
  graph: Graph | undefined;
  nodeTypes: readonly NodeTypeDescriptor[];
  agents: readonly Agent[];
  /** 공통 설정 `agent_defaults.backend` */
  defaultBackend: string | null | undefined;
}

/** 세션 id → 백엔드 id. */
export function sessionBackendIds({ sessions, graph, nodeTypes, agents, defaultBackend }: SessionBackendsInput): Map<string, string> {
  const out = new Map<string, string>();
  if (graph === undefined) return out;
  const typeById = new Map(nodeTypes.map((t) => [t.id, t]));
  const agentById = new Map(agents.map((a) => [a.id, a]));
  const nodeById = new Map(((graph.nodes ?? []) as NodeSpec[]).map((n) => [n.id, n]));
  const teamBackend = (graph.settings as Record<string, unknown> | null | undefined)?.["backend"];
  for (const s of sessions.list) {
    const node = s.nodeId === undefined ? undefined : nodeById.get(s.nodeId);
    const type = node === undefined ? undefined : typeById.get(node.type);
    if (node === undefined || type?.binds == null) continue;
    const ref = node.config?.[type.binds.field];
    const agent = typeof ref === "string" ? agentById.get(ref) : undefined;
    if (agent === undefined) continue;
    const id = effectiveBackendId(agent, node, defaultBackend, teamBackend);
    if (id !== undefined) out.set(s.id, id);
  }
  return out;
}
