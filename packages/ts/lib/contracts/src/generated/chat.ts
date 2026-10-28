/**
 * 자동 생성 파일 — 직접 수정하지 말 것.
 * 소스: packages/py/base/ac-contracts (Pydantic 모델) → schema/agent-console.schema.json → 이 파일.
 * 다시 생성: uv run poe contracts   드리프트 검사: uv run poe contracts-check
 */

// 계약 하위 모듈 `chat`: @agent-console/contracts/chat
export type {
  ChatReply,
  ChatTurn,
  Conversation,
  ConversationSessions,
  ConversationSummary,
  CreateConversationRequest,
  MissingSessionPolicy,
  PostMessageRequest,
  QueuedMessage,
  SessionRef,
  SessionStatus,
  UpdateConversationRequest,
} from "./contracts.generated";

export const CONTRACT_MODULE = "chat" as const;
export const CONTRACT_VERSION = "1.2.0" as const;
