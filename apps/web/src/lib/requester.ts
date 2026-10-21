import type { Interaction } from "@agent-console/contracts";

/**
 * 응답을 기다리는 요청자의 표시 이름. 우선순위: 에이전트 이름 -> 서버가 준 `node_label`
 * -> 호출자가 그래프에서 찾은 노드 이름 -> 노드 id(마지막 수단).
 * `node_label`이 노드 id와 같으면 라벨이 없다는 뜻이라(서버가 id로 채움) 건너뛴다.
 * @param agentName 요청자(`actor`)의 에이전트 표시 이름(없으면 undefined)
 * @param graphNodeName 화면이 이미 가진 그래프에서 구한 노드 이름(없으면 undefined)
 */
export function requesterName(interaction: Pick<Interaction, "node_id" | "node_label">, agentName: string | undefined, graphNodeName?: string): string {
  const label = interaction.node_label;
  const fromServer = typeof label === "string" && label !== "" && label !== interaction.node_id ? label : undefined;
  return agentName ?? fromServer ?? graphNodeName ?? interaction.node_id;
}
