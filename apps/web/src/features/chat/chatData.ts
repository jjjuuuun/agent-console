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
  conversationPages: (project: string | null, archived: boolean | undefined, q = "") => queryKeys.list("conversations", { project, archived, paged: true, ...(q === "" ? {} : { q }) }),
  graphs: () => queryKeys.list("graphs"),
  agents: () => queryKeys.list("agents"),
  resources: () => queryKeys.list("resources"),
  graph: (id: string, project: string | null = null) => ["graph", id, project] as const,
  plan: (id: string, project: string | null = null) => queryKeys.list("graph-plan", { id, project }),
  conversation: (id: string, project?: string | null) => (project === undefined ? (["chat", "conversation", id] as const) : (["chat", "conversation", id, project] as const)),
  turns: (id: string, project?: string | null) => (project === undefined ? (["chat", "turns", id] as const) : (["chat", "turns", id, project] as const)),
  queue: (id: string, project?: string | null) => (project === undefined ? (["chat", "queue", id] as const) : (["chat", "queue", id, project] as const)),
  runEvents: (runId: string) => ["chat", "run-events", runId] as const,
  /** 대화가 있는 기록 공간(`GET /conversations/{id}/locate`). */
  locate: (id: string) => ["chat", "locate", id] as const,
};

const loaders = {
  conversationsPage: (rest: RestClient, project: string | null, archived: boolean | undefined, cursor: string | null, q = "") =>
    rest.conversationsPage({ limit: CONVERSATION_PAGE_SIZE, ...(q === "" ? {} : { q }), ...(project === null ? {} : { project }), ...(archived === undefined ? {} : { archived }), ...(cursor === null ? {} : { cursor }) }),
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
 * @param options.q 제목 부분 일치 검색어(서버가 거른다). 바뀌면 첫 페이지부터 다시 읽는다. 앞뒤 공백은 떼고 200자까지만 보낸다.
 */
export function useConversationList(options: { archived?: boolean; q?: string } = {}) {
  const project = useProjectId();
  const archived = options.archived;
  const q = (options.q ?? "").trim().slice(0, 200);
  const paged = useApiPagedQuery<ConversationSummary>(chatKeys.conversationPages(project, archived, q), (rest, cursor) => loaders.conversationsPage(rest, project, archived, cursor, q));
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

/** 대화가 속한 기록 공간을 알아낸 결과. `ready`가 거짓이면 다른 공간을 찾는 중이다(대화 단위 호출·없음 표시를 미룬다). */
export interface ConversationScope {
  /** 대화 단위 호출의 `?project=` 값(null = 붙이지 않음, 앱 기록). */
  project: string | null;
  ready: boolean;
}

/**
 * 대화 id가 속한 기록 공간(프로젝트 기록 DB). 서버는 대화 단위 REST에 `?project=`가 있어야 프로젝트 기록의 대화를 준다.
 * 1. 현재 범위 목록(대화 목록과 같은 질의 키라 따로 읽지 않는다)을 읽는 동안은 현재 프로젝트로 바로 부른다(지금까지의 동작).
 * 2. 목록에 있으면 그 항목의 `project_id`(없으면 현재 프로젝트).
 * 3. 목록에 없으면(첫 페이지 밖·다른 프로젝트의 대화를 주소로 바로 연 경우) 서버 `GET /conversations/{id}/locate`(계약 0.14.7)의
 *    `project_id`. 찾는 동안은 `ready: false`.
 * 4. 찾기가 실패하면(없음·여러 곳·옛 서버) 현재 프로젝트(없으면 null) - 상세 호출이 그 결과(404 등)를 보인다.
 */
export function useConversationScope(id: string): ConversationScope {
  const current = useProjectId();
  const list = useApiPagedQuery<ConversationSummary>(chatKeys.conversationPages(current, undefined), (rest, cursor) => loaders.conversationsPage(rest, current, undefined, cursor));
  const listed = list.items?.find((c) => c.id === id);
  const listDone = list.items !== undefined || list.isError;
  const needLocate = listDone && listed === undefined && id !== "";
  const located = useApiQuery(chatKeys.locate(id), (rest) => rest.locateConversation(id), { enabled: needLocate, retry: false, staleTime: 60_000 });
  if (listed !== undefined) return { project: listed.project_id ?? current, ready: true };
  if (!needLocate) return { project: current, ready: true };
  if (located.data !== undefined) return { project: located.data.project_id ?? null, ready: true };
  return { project: current, ready: located.isError };
}

/** `useConversationScope`의 `project`만(찾는 중에는 현재 프로젝트). */
export function useConversationProject(id: string): string | null {
  return useConversationScope(id).project;
}

/** 대화 상세. `enabled`가 거짓이면 질의하지 않는다(읽어 둔 결과는 그대로). */
export function useConversationDetail(id: string, project: string | null = null, enabled = true) {
  return useApiQuery(chatKeys.conversation(id, project), (rest) => rest.getConversation(id, project), { enabled });
}

export function useQueueList(id: string, project: string | null = null, enabled = true) {
  return useApiQuery(chatKeys.queue(id, project), (rest) => rest.listQueue(id, project), { enabled });
}

/** 대화 하나의 팀 구성 계획 요약(답변·입구 자리, `GET /graphs/{id}/plan`). id가 없으면 질의하지 않는다. */
export function useChatPlan(graphId: string | undefined, projectId: string | null = null) {
  const { space } = useApi();
  return useQuery({ queryKey: chatKeys.plan(graphId ?? "", projectId), queryFn: () => space(projectId).getGraphPlan(graphId as string), enabled: graphId !== undefined && graphId !== "", staleTime: 5_000 });
}
