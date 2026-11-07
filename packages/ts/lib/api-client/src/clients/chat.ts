/** 채팅 REST: 대화·턴·메시지 전송·대기열. */
import type {
  ChatTurn,
  Conversation,
  ConversationPage,
  ConversationSummary,
  CreateConversationRequest,
  PostMessageRequest,
  QueuedMessage,
  Run,
  UpdateConversationRequest,
} from "@agent-console/contracts";
import type { AssignProjectRequest, AssignProjectResult, ProjectCounts, RecordsMoveRequest, RecordsMoveResult } from "@agent-console/contracts/projects";
import { enc, query, SPACE_PARAM, withQueryParam, type RestIo } from "../io";

/** 대화 단위 호출의 공간 인자: 프로젝트 id를 주면 `?project=<id>`가 붙는다(생략·null·빈 문자열 = 붙지 않음, 하위 호환). */
export type ConversationSpace = string | null | undefined;
const at = (path: string, project: ConversationSpace): string => (project === null || project === undefined || project === "" ? path : withQueryParam(path, SPACE_PARAM, project));

/** GET `/conversations` 필터. */
export interface ListConversationsParams {
  graph_id?: string;
  archived?: boolean;
  /** 그 프로젝트의 대화만(`project_id`, 불투명 문자열). 생략 = 모두. */
  project?: string;
  /** `app` = 앱 저장소에 남은 옛 기록, `project` = 프로젝트 폴더 기록(기본). */
  source?: string;
}

/** GET `/conversations/page` 질의(6R.12). 커서는 불투명 문자열이라 응답 `next_cursor`를 그대로 넘긴다. */
export interface ConversationsPageParams extends ListConversationsParams {
  cursor?: string | null;
  /** 한 페이지 크기(서버 기본값을 따른다). */
  limit?: number;
}

/** GET `/conversations/{id}/turns` 페이지 매김. */
export interface ListTurnsParams {
  /** 이 턴(run_id) 앞의 것만. 서버가 정한 커서를 그대로 넘긴다. */
  before?: string;
  limit?: number;
  /** 대화가 있는 프로젝트(기록 DB). 생략 = 앱 저장소. */
  project?: string | null;
}

/** POST `/conversations/{id}/messages` 응답: 바로 시작한 Run 또는 대기열 항목. */
export type PostMessageResult = { run: Run } | { queued: QueuedMessage };

export interface ChatClient {
  /** `project_id`별 대화 수(보관한 대화 포함. `ProjectCounts`). */
  getConversationProjectCounts(): Promise<ProjectCounts>;
  /** 대화를 프로젝트에 넣는다(`ids` 또는 `from_null`). 못 옮긴 것은 결과 `skipped`에 이유와 함께. */
  assignConversationsToProject(request: AssignProjectRequest): Promise<AssignProjectResult>;
  /** 앱에 남은 옛 기록을 프로젝트 폴더의 기록 DB로 옮긴다(`select` project·null·ids). 같은 id는 `skipped`, 못 옮긴 것은 `failed`. */
  moveConversationsToProject(request: RecordsMoveRequest): Promise<RecordsMoveResult>;
  listConversations(params?: ListConversationsParams): Promise<ConversationSummary[]>;
  /** 대화 커서 페이지(`GET /conversations/page`, 갱신 시각 내림차순). `next_cursor`가 null이면 끝. */
  conversationsPage(params?: ConversationsPageParams): Promise<ConversationPage>;
  createConversation(request: CreateConversationRequest): Promise<Conversation>;
  getConversation(id: string, project?: ConversationSpace): Promise<Conversation>;
  /** 이름·보관·팀 구성 전환(`graph_id`). */
  updateConversation(id: string, patch: UpdateConversationRequest, project?: ConversationSpace): Promise<Conversation>;
  deleteConversation(id: string, project?: ConversationSpace): Promise<void>;
  listTurns(id: string, params?: ListTurnsParams): Promise<ChatTurn[]>;
  /**
   * 메시지 전송. 바로 시작하면 `{run}`, 대기열에 넣었으면 `{queued}`.
   * `chat.busy_policy = reject`이면 `ApiError`(409 `conversation_busy`, `isConversationBusy`).
   */
  postMessage(id: string, request: PostMessageRequest, project?: ConversationSpace): Promise<PostMessageResult>;
  /** 대기열 항목 취소. */
  cancelQueuedMessage(id: string, queuedId: string, project?: ConversationSpace): Promise<void>;
  /** 대화의 대기열(1 = 다음 차례). 서버 메모리에만 있어 서버를 다시 시작하면 비어 있다. */
  listQueue(id: string, project?: ConversationSpace): Promise<QueuedMessage[]>;
  /** 재시작으로 멈춘 대기열 항목을 푼다(`held=false`). */
  releaseQueuedMessage(conversationId: string, queuedId: string, project?: ConversationSpace): Promise<QueuedMessage>;
}

export function createChatClient(io: RestIo): ChatClient {
  return {
    getConversationProjectCounts: () => io.request("GET", "/conversations/project-counts"),
    assignConversationsToProject: (request) => io.request("POST", "/conversations/assign-project", { body: request }),
    moveConversationsToProject: (request) => io.request("POST", "/conversations/move-to-project", { body: request }),
    listConversations: (params) => io.request("GET", `/conversations${query(params)}`),
    conversationsPage: (params) => io.request("GET", `/conversations/page${query(params)}`),
    createConversation: (req) => io.request("POST", "/conversations", { body: req }),
    getConversation: (id, project) => io.request("GET", at(`/conversations/${enc(id)}`, project)),
    updateConversation: (id, patch, project) => io.request("PATCH", at(`/conversations/${enc(id)}`, project), { body: patch }),
    deleteConversation: (id, project) => io.request("DELETE", at(`/conversations/${enc(id)}`, project)),
    listTurns: (id, params) => {
      const { project, ...rest } = params ?? {};
      return io.request("GET", at(`/conversations/${enc(id)}/turns${query(rest)}`, project));
    },
    postMessage: async (id, req, project) => {
      const body = await io.request<Run | QueuedMessage>("POST", at(`/conversations/${enc(id)}/messages`, project), { body: req });
      return "queued" in body && body.queued === true ? { queued: body } : { run: body as Run };
    },
    cancelQueuedMessage: (id, queuedId, project) => io.request("DELETE", at(`/conversations/${enc(id)}/queue/${enc(queuedId)}`, project)),
    listQueue: (id, project) => io.request("GET", at(`/conversations/${enc(id)}/queue`, project)),
    releaseQueuedMessage: (cid, qid, project) => io.request("POST", at(`/conversations/${enc(cid)}/queue/${enc(qid)}/release`, project)),
  };
}
