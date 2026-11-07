import type { RestClient } from "@agent-console/api-client";
import { useQuery } from "@tanstack/react-query";
import { useApi } from "../../app/ApiContext";
import { queryKeys, useApiQuery } from "../../app/queries";
import { useProjectId } from "../../app/projectScope";
import { useApiPagedQuery } from "../../app/pagedQuery";
import type { ConversationSummary } from "@agent-console/contracts";

/** 채팅 화면이 쓰는 질의 키(대화 단위 키는 project를 생략하면 접두 키 = 무효화용). 쓰기 뒤에는 `["list"]` 접두로 한꺼번에 무효화한다(목록 키 규칙). */
export const chatKeys = {
  /** 프로젝트를 주면 그 프로젝트 목록의 키, 생략하면 모든 대화 목록 키의 접두(무효화·일괄 갱신용). */
  conversations: (project?: string | null) => (project == null ? queryKeys.list("conversations") : queryKeys.list("conversations", { project })),
  /** 대화 목록 페이지(무한 질의) 키. `chatKeys.conversations()` 접두 아래라 한꺼번에 무효화된다. */
  conversationPages: (project: string | null, archived: boolean | undefined) => queryKeys.list("conversations", { project, archived, paged: true }),
  graphs: () => queryKeys.list("graphs"),
  agents: () => queryKeys.list("agents"),
  resources: () => queryKeys.list("resources"),
  graph: (id: string, project: string | null = null) => ["graph", id, project] as const,
  plan: (id: string, project: string | null = null) => queryKeys.list("graph-plan", { id, project }),
  conversation: (id: string, project?: string | null) => (project === undefined ? (["chat", "conversation", id] as const) : (["chat", "conversation", id, project] as const)),
  turns: (id: string, project?: string | null) => (project === undefined ? (["chat", "turns", id] as const) : (["chat", "turns", id, project] as const)),
  queue: (id: string, project?: string | null) => (project === undefined ? (["chat", "queue", id] as const) : (["chat", "queue", id, project] as const)),
  runEvents: (runId: string) => ["chat", "run-events", runId] as const,
};

const loaders = {
  conversationsPage: (rest: RestClient, project: string | null, archived: boolean | undefined, cursor: string | null) =>
    rest.conversationsPage({ limit: CONVERSATION_PAGE_SIZE, ...(project === null ? {} : { project }), ...(archived === undefined ? {} : { archived }), ...(cursor === null ? {} : { cursor }) }),
  graphs: (rest: RestClient) => rest.listGraphs(),
  agents: (rest: RestClient) => rest.listAgents(),
  resources: (rest: RestClient) => rest.listResources(),
  edgeTypes: (rest: RestClient) => rest.listEdgeTypes(),
  nodeTypes: (rest: RestClient) => rest.listNodeTypes(),
  interactionKinds: (rest: RestClient) => rest.listInteractionKinds(),
  backends: (rest: RestClient) => rest.listBackends(),
};

/** 대화 목록을 한 번에 읽는 수(서버 커서 페이지) */
export const CONVERSATION_PAGE_SIZE = 50;

/**
 * 현재 프로젝트의 대화 목록(서버 `?project=`·커서 페이지, 프로젝트 기능이 꺼져 있으면 모두).
 * `data`는 읽은 페이지를 이어 붙인 목록이고, `loadMore`로 다음 페이지를 읽는다. 프로젝트가 바뀌면 첫 페이지부터 다시 읽는다.
 * @param options.archived true/false = 서버가 보관 여부로 거른다, 생략 = 모두
 */
export function useConversationList(options: { archived?: boolean } = {}) {
  const project = useProjectId();
  const archived = options.archived;
  const paged = useApiPagedQuery<ConversationSummary>(chatKeys.conversationPages(project, archived), (rest, cursor) => loaders.conversationsPage(rest, project, archived, cursor));
  const { items, isPending, ...rest } = paged;
  return { ...rest, data: items as ConversationSummary[] | undefined, isLoading: isPending };
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

/**
 * 대화 id가 속한 프로젝트(기록 DB). 현재 프로젝트가 있으면 그것, 모든 프로젝트 보기이면 읽어 둔 목록 항목의 `project_id`, 모르면 null(앱 저장소).
 * 서버는 대화 단위 REST에 `?project=`가 있어야 프로젝트 기록의 대화를 준다.
 */
export function useConversationProject(id: string): string | null {
  const current = useProjectId();
  const { items } = useApiPagedQuery<ConversationSummary>(chatKeys.conversationPages(current, undefined), (rest, cursor) => loaders.conversationsPage(rest, current, undefined, cursor), { enabled: current === null });
  return current ?? items?.find((c) => c.id === id)?.project_id ?? null;
}

export function useConversationDetail(id: string, project: string | null = null) {
  return useApiQuery(chatKeys.conversation(id, project), (rest) => rest.getConversation(id, project));
}

export function useQueueList(id: string, project: string | null = null) {
  return useApiQuery(chatKeys.queue(id, project), (rest) => rest.listQueue(id, project));
}

/** 대화 하나의 팀 구성 계획 요약(답변·입구 자리, `GET /graphs/{id}/plan`). id가 없으면 질의하지 않는다. */
export function useChatPlan(graphId: string | undefined, projectId: string | null = null) {
  const { space } = useApi();
  return useQuery({ queryKey: chatKeys.plan(graphId ?? "", projectId), queryFn: () => space(projectId).getGraphPlan(graphId as string), enabled: graphId !== undefined && graphId !== "", staleTime: 5_000 });
}
