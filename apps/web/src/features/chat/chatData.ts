import type { RestClient } from "@agent-console/api-client";
import { queryKeys, useApiQuery } from "../../app/queries";

/** 채팅 화면이 쓰는 질의 키. 쓰기 뒤에는 `["list"]` 접두로 한꺼번에 무효화한다(목록 키 규칙). */
export const chatKeys = {
  conversations: () => queryKeys.list("conversations"),
  graphs: () => queryKeys.list("graphs"),
  agents: () => queryKeys.list("agents"),
  resources: () => queryKeys.list("resources"),
  graph: (id: string) => ["graph", id] as const,
  plan: (id: string) => queryKeys.list("graph-plan", id),
  conversation: (id: string) => ["chat", "conversation", id] as const,
  turns: (id: string) => ["chat", "turns", id] as const,
  queue: (id: string) => ["chat", "queue", id] as const,
  runEvents: (runId: string) => ["chat", "run-events", runId] as const,
};

const loaders = {
  conversations: (rest: RestClient) => rest.listConversations(),
  graphs: (rest: RestClient) => rest.listGraphs(),
  agents: (rest: RestClient) => rest.listAgents(),
  resources: (rest: RestClient) => rest.listResources(),
  edgeTypes: (rest: RestClient) => rest.listEdgeTypes(),
  nodeTypes: (rest: RestClient) => rest.listNodeTypes(),
  interactionKinds: (rest: RestClient) => rest.listInteractionKinds(),
  presets: (rest: RestClient) => rest.listPresets(),
  backends: (rest: RestClient) => rest.listBackends(),
};

export const useConversationList = () => useApiQuery(chatKeys.conversations(), loaders.conversations);
export const useGraphList = (enabled = true) => useApiQuery(chatKeys.graphs(), loaders.graphs, { enabled });
export const useAgentList = (enabled = true) => useApiQuery(chatKeys.agents(), loaders.agents, { enabled });
export const useResourceCount = (enabled = true) => useApiQuery(chatKeys.resources(), loaders.resources, { enabled });
export const useEdgeTypeList = () => useApiQuery(queryKeys.descriptors("edge-types"), loaders.edgeTypes, { staleTime: 60_000 });
export const useNodeTypeList = () => useApiQuery(queryKeys.descriptors("node-types"), loaders.nodeTypes, { staleTime: 60_000 });
export const useInteractionKindList = () => useApiQuery(queryKeys.descriptors("interaction-kinds"), loaders.interactionKinds, { staleTime: 60_000 });
/** 실행 백엔드 디스크립터(칩 문구·바꾸기 카드의 데이터). 설정 화면과 같은 질의 키를 쓴다. */
export const useBackendList = () => useApiQuery(queryKeys.descriptors("backends"), loaders.backends, { staleTime: 60_000 });
export const usePresetList = (enabled = true) => useApiQuery(queryKeys.list("presets"), loaders.presets, { enabled });

/** 대화 하나의 팀 구성 그래프. id가 없으면 질의하지 않는다. */
export function useChatGraph(graphId: string | undefined) {
  return useApiQuery(chatKeys.graph(graphId ?? ""), (rest) => rest.getGraph(graphId as string), { enabled: graphId !== undefined && graphId !== "" });
}

export function useConversationDetail(id: string) {
  return useApiQuery(chatKeys.conversation(id), (rest) => rest.getConversation(id));
}

export function useQueueList(id: string) {
  return useApiQuery(chatKeys.queue(id), (rest) => rest.listQueue(id));
}

/** 대화 하나의 팀 구성 계획 요약(답변·입구 자리, `GET /graphs/{id}/plan`). id가 없으면 질의하지 않는다. */
export function useChatPlan(graphId: string | undefined) {
  return useApiQuery(chatKeys.plan(graphId ?? ""), (rest) => rest.getGraphPlan(graphId as string), { enabled: graphId !== undefined && graphId !== "" });
}
