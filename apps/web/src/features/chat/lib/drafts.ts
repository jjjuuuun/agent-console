import type { SafeStorage } from "../../../app/storage";

/** 대화별 입력 초안 저장 키. */
export const DRAFT_KEY_PREFIX = "ac.draft.";
export const LAST_GRAPH_KEY = "ac.chat.lastGraph";

export function draftKey(conversationId: string): string {
  return `${DRAFT_KEY_PREFIX}${conversationId}`;
}

export function readDraft(storage: SafeStorage, conversationId: string): string {
  return storage.get(draftKey(conversationId)) ?? "";
}

/** 빈 문자열이면 지운다(전송 성공 시). 저장 실패는 무시된다. */
export function writeDraft(storage: SafeStorage, conversationId: string, text: string): void {
  if (text === "") storage.remove(draftKey(conversationId));
  else storage.set(draftKey(conversationId), text);
}
