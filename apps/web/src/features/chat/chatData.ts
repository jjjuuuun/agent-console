import type { RestClient } from "@agent-console/api-client";
import { useQuery } from "@tanstack/react-query";
import { useApi } from "../../app/ApiContext";
import { queryKeys, useApiQuery } from "../../app/queries";
import { useProjectId } from "../../app/projectScope";

/** 채팅 화면이 쓰는 질의 키. 쓰기 뒤에는 `["list"]` 접두로 한꺼번에 무효화한다(목록 키 규칙). */
export const chatKeys = {
  /** 프로젝트를 주면 그 프로젝트 목록의 키, 생략하면 모든 대화 목록 키의 접두(무효화·일괄 갱신용). */
  conversations: (project?: string | null) => (project == null ? queryKeys.list("conversations") : queryKeys.list("conversations", { project })),
  graphs: () => queryKeys.list("graphs"),
  agents: () => queryKeys.list("agents"),
  resources: () => queryKeys.list("resources"),
  graph: (id: string, project: string | null = null) => ["graph", id, project] as const,
  plan: (id: string, project: string | null = null) => queryKeys.list("graph-plan", { id, project }),
  conversation: (id: string) => ["chat", "conversation", id] as const,
  turns: (id: string) => ["chat", "turns", id] as const,
  queue: (id: string) => ["chat", "queue", id] as const,
  runEvents: (runId: string) => ["chat", "run-events", runId] as const,
};

const loaders = {
  conversations: (rest: RestClient, project: string | null) => rest.listConversations(project === null ? undefined : { project }),
  graphs: (rest: RestClient) => rest.listGraphs(),
  agents: (rest: RestClient) => rest.listAgents(),
  resources: (rest: RestClient) => rest.listResources(),
  edgeTypes: (rest: RestClient) => rest.listEdgeTypes(),
  nodeTypes: (rest: RestClient) => rest.listNodeTypes(),
  interactionKinds: (rest: RestClient) => rest.listInteractionKinds(),
  backends: (rest: RestClient) => rest.listBackends(),
};

/** 현재 프로젝트의 대화 목록(프로젝트 기능이 꺼져 있으면 모두). */
export function useConversationList() {
  const project = useProjectId();
  return useApiQuery(chatKeys.conversations(project), (rest) => loaders.conversations(rest, project));
}
export const useGraphList = (enabled = true) => useApiQuery(chatKeys.graphs(), loaders.graphs, { enabled });
export const useAgentList = (enabled = true) => useApiQuery(chatKeys.agents(), loaders.agents, { enabled });
export const useEdgeTypeList = () => useApiQuery(queryKeys.descriptors("edge-types"), loaders.edgeTypes, { staleTime: 60_000 });
export const useNodeTypeList = () => useApiQuery(queryKeys.descriptors("node-types"), loaders.nodeTypes, { staleTime: 60_000 });
export const useInteractionKindList = () => useApiQuery(queryKeys.descriptors("interaction-kinds"), loaders.interactionKinds, { staleTime: 60_000 });
/** 실행 백엔드 디스크립터(칩 문구·바꾸기 카드의 데이터). 설정 화면과 같은 질의 키를 쓴다. */
export const useBackendList = () => useApiQuery(queryKeys.descriptors("backends"), loaders.backends, { staleTime: 60_000 });

/** 대화 하나의 팀 구성 그래프. id가 없으면 질의하지 않는다. */
export function useChatGraph(graphId: string | undefined, projectId: string | null = null) {
  const { space } = useApi();
  return useQuery({ queryKey: chatKeys.graph(graphId ?? "", projectId), queryFn: () => space(projectId).getGraph(graphId as string), enabled: graphId !== undefined && graphId !== "", staleTime: 5_000 });
}

export function useConversationDetail(id: string) {
  return useApiQuery(chatKeys.conversation(id), (rest) => rest.getConversation(id));
}

export function useQueueList(id: string) {
  return useApiQuery(chatKeys.queue(id), (rest) => rest.listQueue(id));
}

/** 대화 하나의 팀 구성 계획 요약(답변·입구 자리, `GET /graphs/{id}/plan`). id가 없으면 질의하지 않는다. */
export function useChatPlan(graphId: string | undefined, projectId: string | null = null) {
  const { space } = useApi();
  return useQuery({ queryKey: chatKeys.plan(graphId ?? "", projectId), queryFn: () => space(projectId).getGraphPlan(graphId as string), enabled: graphId !== undefined && graphId !== "", staleTime: 5_000 });
}
