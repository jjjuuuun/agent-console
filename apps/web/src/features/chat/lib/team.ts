import type { Agent, Graph, GraphSummary, NodeSpec, NodeTypeDescriptor, TeamPlanSummary } from "@agent-console/contracts";

/** 연결 종류 id → 디스크립터. */
export function indexById<T extends { id: string }>(items: readonly T[] | undefined): ReadonlyMap<string, T> {
  return new Map((items ?? []).map((i) => [i.id, i]));
}

/** 서버가 계산한 입구 목록이 있으면 "입구 없음"을 판정한다. 계산하지 않았으면(null) 모른다(undefined). */
export function hasEntry(team: Pick<GraphSummary, "entry_labels">): boolean | undefined {
  return team.entry_labels == null ? undefined : team.entry_labels.length > 0;
}

export interface NamingContext {
  nodeTypes: ReadonlyMap<string, NodeTypeDescriptor>;
  agents: ReadonlyMap<string, Agent>;
}

/** 노드가 묶인 정의(에이전트 라이브러리 항목)를 찾는다. 종류 이름이 아니라 정의 종류가 서로 같은지로 판단한다. */
export function agentOfNode(node: NodeSpec, ctx: NamingContext): Agent | undefined {
  const binds = ctx.nodeTypes.get(node.type)?.binds;
  if (!binds) return undefined;
  const ref = node.config?.[binds.field];
  const agent = typeof ref === "string" ? ctx.agents.get(ref) : undefined;
  return agent !== undefined && agent.kind === binds.kind ? agent : undefined;
}

/** 노드 표시 이름: 노드 라벨 → 묶인 에이전트 이름 → 노드 id. */
export function nodeName(node: NodeSpec | undefined, nodeId: string, ctx: NamingContext): string {
  if (!node) return nodeId;
  return node.label || agentOfNode(node, ctx)?.name || node.id;
}

/** 노드 역할 표시: 노드 config의 `role` → 에이전트 역할. */
export function nodeRole(node: NodeSpec | undefined, ctx: NamingContext): string | undefined {
  if (!node) return undefined;
  const own = node.config?.["role"];
  if (typeof own === "string" && own !== "") return own;
  return agentOfNode(node, ctx)?.role || undefined;
}

export interface ReplyEdge {
  edgeId: string;
  nodeId: string;
  label: string | null;
  order: number | null;
  final: boolean;
  stream: boolean;
}

/**
 * 답변 자리 목록. 서버의 계획 요약(`TeamPlanSummary.answers`)에서만 읽는다.
 * 연결 설정의 키(라벨·순서·마지막 답변·스트림)는 연결 종류가 정하는 데이터라 화면이 직접 읽지 않는다.
 */
export function replyEdgesOf(plan: Pick<TeamPlanSummary, "answers"> | undefined): ReplyEdge[] {
  return (plan?.answers ?? []).map((a) => ({
    edgeId: a.edge_id,
    nodeId: a.node_id,
    label: a.label ?? null,
    order: a.order ?? null,
    final: a.final !== false,
    stream: a.stream === true,
  }));
}

export interface TeamSummary {
  /** 사용자 메시지를 받는 노드 이름들 */
  entries: string[];
  /** 답변을 내는 노드 이름들 */
  answers: string[];
  /** 되묻기·승인을 열 수 있는 노드 이름들(계획 요약의 `grants` 키) */
  askers: string[];
}

/** 빈 대화에서 보여 줄 팀 구성 요약. 입구·답변·허용 노드는 서버 계획 요약에서 읽고 이름만 그래프에서 찾는다. */
export function summarizeTeam(plan: TeamPlanSummary, graph: Graph | undefined, ctx: NamingContext): TeamSummary {
  const nodes = new Map((graph?.nodes ?? []).map((n) => [n.id, n]));
  const names = (ids: Iterable<string>) => [...new Set(ids)].map((id) => nodeName(nodes.get(id), id, ctx));
  return {
    entries: names((plan.entries ?? []).map((e) => e.node_id)),
    answers: names((plan.answers ?? []).map((a) => a.node_id)),
    askers: names(Object.keys(plan.grants ?? {})),
  };
}
