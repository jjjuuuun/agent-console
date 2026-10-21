/** 채팅 REST: 대화·턴·메시지 전송·대기열. */
import type {
  ChatTurn,
  Conversation,
  ConversationSummary,
  CreateConversationRequest,
  PostMessageRequest,
  QueuedMessage,
  Run,
  UpdateConversationRequest,
} from "@agent-console/contracts";
import { enc, query, type RestIo } from "../io";

/** GET `/conversations` 필터. */
export interface ListConversationsParams {
  graph_id?: string;
  archived?: boolean;
}

/** GET `/conversations/{id}/turns` 페이지 매김. */
export interface ListTurnsParams {
  /** 이 턴(run_id) 앞의 것만. 서버가 정한 커서를 그대로 넘긴다. */
  before?: string;
  limit?: number;
}

/** POST `/conversations/{id}/messages` 응답: 바로 시작한 Run 또는 대기열 항목. */
export type PostMessageResult = { run: Run } | { queued: QueuedMessage };

export interface ChatClient {
  listConversations(params?: ListConversationsParams): Promise<ConversationSummary[]>;
  createConversation(request: CreateConversationRequest): Promise<Conversation>;
  getConversation(id: string): Promise<Conversation>;
  /** 이름·보관·팀 구성 전환(`graph_id`). */
  updateConversation(id: string, patch: UpdateConversationRequest): Promise<Conversation>;
  deleteConversation(id: string): Promise<void>;
  listTurns(id: string, params?: ListTurnsParams): Promise<ChatTurn[]>;
  /**
   * 메시지 전송. 바로 시작하면 `{run}`, 대기열에 넣었으면 `{queued}`.
   * `chat.busy_policy = reject`이면 `ApiError`(409 `conversation_busy`, `isConversationBusy`).
   */
  postMessage(id: string, request: PostMessageRequest): Promise<PostMessageResult>;
  /** 대기열 항목 취소. */
  cancelQueuedMessage(id: string, queuedId: string): Promise<void>;
  /** 대화의 대기열(1 = 다음 차례). 서버 메모리에만 있어 서버를 다시 시작하면 비어 있다. */
  listQueue(id: string): Promise<QueuedMessage[]>;
  /** 재시작으로 멈춘 대기열 항목을 푼다(`held=false`). */
  releaseQueuedMessage(conversationId: string, queuedId: string): Promise<QueuedMessage>;
}

export function createChatClient(io: RestIo): ChatClient {
  return {
    listConversations: (params) => io.request("GET", `/conversations${query(params)}`),
    createConversation: (req) => io.request("POST", "/conversations", { body: req }),
    getConversation: (id) => io.request("GET", `/conversations/${enc(id)}`),
    updateConversation: (id, patch) => io.request("PATCH", `/conversations/${enc(id)}`, { body: patch }),
    deleteConversation: (id) => io.request("DELETE", `/conversations/${enc(id)}`),
    listTurns: (id, params) => io.request("GET", `/conversations/${enc(id)}/turns${query(params)}`),
    postMessage: async (id, req) => {
      const body = await io.request<Run | QueuedMessage>("POST", `/conversations/${enc(id)}/messages`, { body: req });
      return "queued" in body && body.queued === true ? { queued: body } : { run: body as Run };
    },
    cancelQueuedMessage: (id, queuedId) => io.request("DELETE", `/conversations/${enc(id)}/queue/${enc(queuedId)}`),
    listQueue: (id) => io.request("GET", `/conversations/${enc(id)}/queue`),
    releaseQueuedMessage: (cid, qid) => io.request("POST", `/conversations/${enc(cid)}/queue/${enc(qid)}/release`),
  };
}
