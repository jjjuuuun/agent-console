/**
 * 대화 목록 정렬 방식 어휘(`chat.list_sort` 값). 계약은 이 값을 자유 문자열로 두고 해석을 웹에 맡긴다.
 * 설정 화면(고르기)과 채팅 화면(정렬)이 같은 표를 쓴다. 새 방식은 여기에 한 줄과 `compare`를 더한다.
 * 기본(비워 둠) = 응답 대기 우선.
 */
export interface ChatSortMode {
  id: string;
  /** `messages`의 키(설정 화면 라벨) */
  titleKey: string;
  /** 설정 화면의 설명 키 */
  descriptionKey: string;
}

export const CHAT_SORT_MODES: readonly ChatSortMode[] = [
  { id: "pending_first", titleKey: "settings.chatSort.pending_first.title", descriptionKey: "settings.chatSort.pending_first.description" },
  { id: "updated", titleKey: "settings.chatSort.updated.title", descriptionKey: "settings.chatSort.updated.description" },
];

/** 값이 비었거나 모르는 방식이면 첫 항목(기본). */
export function resolveChatSort(value: string | null | undefined): ChatSortMode {
  return CHAT_SORT_MODES.find((m) => m.id === value) ?? CHAT_SORT_MODES[0]!;
}
