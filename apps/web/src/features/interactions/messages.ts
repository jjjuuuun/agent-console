/** 상호작용 응답 공용 문구(채팅·실행 상세가 공유). 화면별로 다른 문구가 필요하면 훅/컴포넌트에 덮어 넘긴다. */
export const interactionMessages = {
  closed: "이미 답했거나 닫힌 요청입니다. 최신 상태로 새로 고쳤습니다.",
  notFound: "요청을 찾을 수 없습니다. 최신 상태로 새로 고쳤습니다.",
  offline: "연결이 끊겨 보낼 수 없습니다. 입력한 내용은 유지됩니다.",
  failed: "응답을 보내지 못했습니다",
  payload: "요청 내용",
  send: "보내기",
} as const;

export type InteractionMessages = { -readonly [K in keyof typeof interactionMessages]: string };
