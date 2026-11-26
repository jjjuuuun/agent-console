import ko from "../locales/ko.json";

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
  /** 되묻기 답 입력칸 안내(`chat.answer.*`). */
  answer: {
    /** 카드 힌트 줄: 답은 아래 입력창에서. */
    hintComposer: string;
    /** 입력창이 "새 메시지" 모드일 때의 힌트 줄. */
    hintCardPaused: string;
    /** 카드 접근성 이름에 덧붙이는 말. {label} = 기본 접근성 이름 */
    cardLabelExternal: string;
  };
  fallback: {
    payload: string;
    responseLabel: string;
    invalidJson: string;
    submit: string;
  };
}

/** 기본 문구는 한국어(`locales/ko.json`의 `interaction`). 영어는 `@agent-console/chat/locales/en`의 `interaction`을 넘긴다. */
export const defaultInteractionMessages: InteractionMessages = ko.interaction;
