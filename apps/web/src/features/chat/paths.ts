import { ROUTE_ROLES, routePath } from "../library";
/** 라우트 설정 데이터에서 역할로 다른 화면의 경로를 찾는다(라우트 id·경로를 코드에 박지 않는다). */
export { routePath, ROUTE_ROLES };

export const chatPaths = {
  chat: () => routePath(ROUTE_ROLES.conversations),
  conversation: (id: string) => `${routePath(ROUTE_ROLES.conversations)}/${encodeURIComponent(id)}`,
  teams: () => routePath(ROUTE_ROLES.graph),
  team: (id: string) => `${routePath(ROUTE_ROLES.graph)}/${encodeURIComponent(id)}`,
  run: (runId: string, nodeId?: string, edgeId?: string) =>
    `${routePath(ROUTE_ROLES.runs)}/${encodeURIComponent(runId)}${edgeId ? `#edge=${encodeURIComponent(edgeId)}` : nodeId ? `#node=${encodeURIComponent(nodeId)}` : ""}`,
  runsOfConversation: (id: string) => `${routePath(ROUTE_ROLES.runs)}?conversation_id=${encodeURIComponent(id)}`,
  settings: () => routePath(ROUTE_ROLES.settings),
};
