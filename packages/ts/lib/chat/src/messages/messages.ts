import ko from "../locales/ko.json";

/** 메시지 영역(`MessageList`·`TurnView`·`ReplyGroup`·`ProgressStrip`) 문구. 앱이 `messages`로 덮어쓴다. */
export interface ChatMessages {
  /** 내 메시지의 보조 이름(대기열 행 등). 화면에는 "나" 라벨을 그리지 않는다. */
  you: string;
  /** 내 메시지 말풍선의 접근성 이름 */
  yourMessage: string;
  copy: string;
  /** 답변 머리의 복사 아이콘 이름 */
  copyReply: string;
  copied: string;
  resend: string;
  showMore: string;
  showLess: string;
  openRun: string;
  intermediate: string;
  intermediateHidden: string; // {n}
  intermediateHiddenLink: string;
  collapse: string;
  expand: string;
  insideOf: string; // {parent}, {name}
  /** 독립 위임 대상의 답변 머리 */
  delegatedBy: string; // {parent}, {name}
  queuedChip: string; // {n}
  queuedCancel: string;
  queuedHeldChip: string; // {n}
  queuedCancelHeld: string;
  queuedRelease: string;
  queuedRecall: string;
  queuedBusy: string;
  resumedChip: string; // {run}
  loadingOlder: string;
  startOfConversation: string;
  newContent: string;
  jumpToPending: string;
  stop: string;
  stopping: string;
  tokens: string; // {n}
  someTokensTotalOnly: string;
  waitingFor: string; // {n}
  turnStatus: Record<string, string>;
  stepStatus: Record<string, string>;
  progressSummary: string; // {n}
  /** 1초 이상 걸렸을 때만 쓰는 요약. {n}, {duration} */
  progressSummaryDuration: string;
  /** 요약 끝에 붙는 현재 단계. {name} */
  progressNow: string;
  moreSteps: string; // {n}
  sameSession: string;
  /** 중첩 팀 칩 진행 숫자. {done}, {total} */
  childProgress: string;
  /** 접힌 중첩 팀 칩의 현재 단계. {name} */
  childCurrent: string;
  /** 중첩 팀 칩 [실행 상세] 링크. {name} = 칩 이름(접근성 이름용) */
  childOpen: string;
  /** 자식 실행 아이콘 링크의 툴팁 */
  childOpenTip: string;
  /** 중첩 팀 칩 펼침 단추 접근성 이름. {name} */
  childToggle: string;
  /** 경고 단계 앞에 붙는 접근성 문구 */
  stepWarning: string;
  progressLabel: string;
  listLabel: string;
  errorOpenRun: string;
  units: { s: string; m: string; h: string };
}

/** 기본 문구는 한국어(`locales/ko.json`의 `chat`). 영어는 `@agent-console/chat/locales/en`의 `chat`을 넘긴다. */
export const defaultChatMessages: ChatMessages = ko.chat;
