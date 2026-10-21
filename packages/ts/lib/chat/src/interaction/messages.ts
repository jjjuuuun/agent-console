/** 상호작용 카드 문구. 앱이 `messages`로 덮어쓴다. 종류·결정 이름은 여기에 없다(서버 데이터). */
export interface InteractionMessages {
  waitingFor: string; // {duration}
  remaining: string; // {time}
  disconnected: string;
  answeredLine: string; // {summary}, {duration}
  answeredGeneric: string;
  expiredLine: string; // {duration}
  expiredDetail: string;
  cancelledLine: string; // {reason}
  closeReasons: Record<string, string>;
  answeredBy: Record<string, string>;
  expand: string;
  collapse: string;
  sendFailed: string;
  /** 접근성 이름: "{title}, {actor}, {state}" */
  cardLabel: string;
  stateLabels: Record<string, string>;
  interruptedTitle: string;
  interruptedBody: string;
  resendAsMessage: string;
  units: { s: string; m: string; h: string };
  choices: {
    customOption: string;
    customPlaceholder: string;
    freePlaceholder: string;
    submit: string;
    allRequired: string;
    answerSummary: string; // {first}
    answerSummaryMore: string; // {first}, {n}
  };
  permission: {
    toolTitle: string; // {name}
    reason: string; // {reason}
    path: string; // {path}
    showAll: string;
    showLess: string;
    allow: string;
    allowForRun: string;
    deny: string;
    denyReasonLabel: string;
    denySend: string;
    editInput: string;
    editAndAllow: string;
    invalidJson: string;
    summaryAllow: string;
    summaryAllowForRun: string;
    summaryDeny: string; // {reason}
    summaryDenyPlain: string;
  };
  review: {
    sourceNode: string; // {label}
    confirm: string; // {label}
    feedbackLabel: string;
    editLabel: string;
    expandContent: string;
    collapseContent: string;
    edited: string;
    hasFeedback: string;
    decisionsLabel: string;
  };
  fallback: {
    payload: string;
    responseLabel: string;
    invalidJson: string;
    submit: string;
  };
}

export const defaultInteractionMessages: InteractionMessages = {
  waitingFor: "응답 대기 {duration}",
  remaining: "남은 시간 {time}",
  disconnected: "연결 끊김",
  answeredLine: "답함: {summary} · {duration}",
  answeredGeneric: "답함",
  expiredLine: "만료됨 — 응답 없음 · {duration}",
  expiredDetail: "에이전트에게 ‘응답 없음’이 전달되었습니다",
  cancelledLine: "취소됨 — {reason}",
  closeReasons: { cancelled: "실행 취소", node_finished: "노드 종료", timeout: "응답 없음", interrupted: "서버 재시작" },
  answeredBy: { timeout: "시간 초과", system: "시스템" },
  expand: "펼치기",
  collapse: "접기",
  sendFailed: "보내지 못했습니다.",
  cardLabel: "{title}, {actor}, {state}",
  stateLabels: { pending: "응답 대기", answered: "답함", expired: "만료", cancelled: "취소됨", interrupted: "끊김" },
  interruptedTitle: "서버가 다시 시작되어 응답 대기가 끊겼습니다",
  interruptedBody: "이 요청에는 더 이상 답할 수 없습니다. 답을 새 메시지로 보내면 에이전트가 앞 맥락을 이어 받습니다(세션 이어쓰기).",
  resendAsMessage: "답을 새 메시지로 보내기",
  units: { s: "초", m: "분", h: "시간" },
  choices: {
    customOption: "직접 입력",
    customPlaceholder: "직접 입력",
    freePlaceholder: "답을 입력하세요",
    submit: "보내기",
    allRequired: "모든 질문에 답하세요",
    answerSummary: "{first}",
    answerSummaryMore: "{first} 외 {n}건",
  },
  permission: {
    toolTitle: "‘{name}’ 도구를 실행하려고 합니다",
    reason: "이유: {reason}",
    path: "경로: {path}",
    showAll: "전체 보기",
    showLess: "줄이기",
    allow: "허용",
    allowForRun: "이번 실행 동안 허용",
    deny: "거부…",
    denyReasonLabel: "거부 사유(선택)",
    denySend: "거부 보내기",
    editInput: "입력 고쳐서 허용",
    editAndAllow: "수정해서 허용",
    invalidJson: "올바른 JSON이 아닙니다",
    summaryAllow: "허용",
    summaryAllowForRun: "이번 실행 동안 허용",
    summaryDeny: "거부: {reason}",
    summaryDenyPlain: "거부",
  },
  review: {
    sourceNode: "{label}의 결과",
    confirm: "확정: {label}",
    feedbackLabel: "의견",
    editLabel: "내용 수정",
    expandContent: "전체 보기",
    collapseContent: "줄이기",
    edited: "수정함",
    hasFeedback: "의견 있음",
    decisionsLabel: "결정",
  },
  fallback: {
    payload: "요청 내용",
    responseLabel: "응답(JSON)",
    invalidJson: "올바른 JSON이 아닙니다",
    submit: "보내기",
  },
};
