import type { Agent, ChatTurn, Graph, Interaction, NodeSpec } from "@agent-console/contracts";
import type { AgentView } from "@agent-console/chat";
import { resolveAvatar } from "../../library";
import { requesterName } from "../../../lib/requester";
import { agentOfNode, nodeName, nodeRole, type NamingContext } from "./team";

const NO_DELEGATORS: ReadonlyMap<string, string> = new Map();

export interface ActorContext {
  graph: Graph | undefined;
  naming: NamingContext;
}

export interface ActorTexts {
  /** "{parent} 안의 {name}" */
  inside: (parent: string, name: string) => string;
}

/**
 * 상호작용 요청자 표기. 주 에이전트는 "이름 · 역할", 서브에이전트(`node_path` 길이 2 이상)는 "위임자 안의 대상",
 * 에이전트가 없는 요청(사용자 노드의 검토 등)은 노드 이름.
 */
export function actorLabel(interaction: Interaction, ctx: ActorContext, texts: ActorTexts): string {
  const nodes = new Map((ctx.graph?.nodes ?? []).map((n) => [n.id, n]));
  const path = interaction.node_path ?? [];
  const agent: Agent | undefined = interaction.actor ? ctx.naming.agents.get(interaction.actor) : undefined;
  if (path.length >= 2) {
    const parent = nodeName(nodes.get(path[0]!), path[0]!, ctx.naming);
    const child = agent?.name ?? nodeName(nodes.get(path[path.length - 1]!), path[path.length - 1]!, ctx.naming);
    return texts.inside(parent, child);
  }
  const node = nodes.get(path[0] ?? interaction.node_id);
  const name = requesterName(interaction, agent?.name, nodeName(node, path[0] ?? interaction.node_id, ctx.naming));
  const role = nodeRole(node, ctx.naming) ?? agent?.role;
  return role ? `${name} · ${role}` : name;
}

/**
 * 답변 카드 머리용 에이전트 표기. 답변을 낸 에이전트가 그 노드 자신의 에이전트와 다르면(위임받은 서브에이전트)
 * 노드 쪽 에이전트 이름을 `parentName`으로 단다.
 */
export function buildAgentView(
  turns: readonly ChatTurn[],
  ctx: ActorContext,
  delegators: ReadonlyMap<string, string> = NO_DELEGATORS,
  /** 에이전트·노드의 칩 문구(없으면 칩 없음). 문구는 호출자가 데이터에서 정한다 */
  badgeOf?: (agent: Agent | undefined, node: NodeSpec | undefined) => string | undefined,
): (agentId: string) => AgentView {
  const nodes = new Map((ctx.graph?.nodes ?? []).map((n) => [n.id, n]));
  const parents = new Map<string, string>();
  const delegated = new Map<string, string>();
  const badges = new Map<string, string>();
  for (const turn of turns) {
    for (const reply of turn.replies ?? []) {
      const node = nodes.get(reply.node_id);
      if (!node || !reply.agent_id) continue;
      // 독립 위임으로 불린 대상의 답변: "{위임자}가 맡긴 {대상}"(호출 NodeRun 여부로 판정, 서브에이전트 "안의"와 구분)
      const delegator = delegators.get(reply.node_id);
      if (delegator !== undefined) delegated.set(reply.agent_id, delegator);
      const badge = badgeOf?.(ctx.naming.agents.get(reply.agent_id), node);
      if (badge !== undefined && badge !== "") badges.set(reply.agent_id, badge);
      const own = agentOfNode(node, ctx.naming);
      if (own !== undefined && own.id !== reply.agent_id) parents.set(reply.agent_id, own.name);
    }
  }
  return (agentId) => {
    const agent = ctx.naming.agents.get(agentId);
    const avatar = agent === undefined ? undefined : resolveAvatar(agent);
    if (agent === undefined && nodes.has(agentId)) {
      const node = nodes.get(agentId);
      const role = nodeRole(node, ctx.naming);
      const nodeBadge = badgeOf?.(undefined, node);
      return { name: nodeName(node, agentId, ctx.naming), ...(role ? { role } : {}), ...(nodeBadge ? { badge: nodeBadge } : {}) };
    }
    const parentName = parents.get(agentId);
    const delegatedBy = delegated.get(agentId);
    const badge = badges.get(agentId);
    return { name: agent?.name ?? agentId, ...(avatar ? { avatar } : {}), ...(agent?.role ? { role: agent.role } : {}), ...(parentName ? { parentName } : {}), ...(delegatedBy ? { delegatedBy } : {}), ...(badge ? { badge } : {}) };
  };
}
