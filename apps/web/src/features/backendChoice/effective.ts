import type { Agent, NodeSpec } from "@agent-console/contracts";

/**
 * 노드가 실제로 쓸 백엔드 id: 노드 설정 `backend` → 에이전트 `backend` → 팀 구성 `settings.backend` → 공통 기본값(서버 `_backends.py`와 같은 순서). 모두 비면 undefined.
 * 노드 설정 키 이름은 에이전트 필드와 같은 `backend`다(설정 화면의 필드).
 */
export function effectiveBackendId(agent: Agent | undefined, node: NodeSpec | undefined, defaultBackend: string | null | undefined, teamBackend?: unknown): string | undefined {
  const fromNode = node?.config?.["backend"];
  if (typeof fromNode === "string" && fromNode !== "") return fromNode;
  if (agent?.backend) return agent.backend;
  if (typeof teamBackend === "string" && teamBackend !== "") return teamBackend;
  return defaultBackend || undefined;
}
