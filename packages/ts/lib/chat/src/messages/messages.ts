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

export const defaultChatMessages: ChatMessages = {
  you: "나",
  yourMessage: "나의 메시지",
  copy: "복사",
  copyReply: "답변 복사",
  copied: "복사됨",
  resend: "다시 보내기",
  showMore: "더 보기",
  showLess: "접기",
  openRun: "실행 상세",
  intermediate: "중간 결과",
  intermediateHidden: "중간 결과 {n}개 숨김",
  intermediateHiddenLink: "실행 상세에서 보기",
  collapse: "접기",
  expand: "펼치기",
  insideOf: "{parent} 안의 {name}",
  delegatedBy: "{parent}가 맡긴 {name}",
  queuedChip: "대기열 #{n}",
  queuedCancel: "대기열에서 빼기",
  queuedHeldChip: "멈춤 #{n}",
  queuedCancelHeld: "취소",
  queuedRelease: "실행",
  queuedRecall: "입력창으로 가져오기",
  queuedBusy: "처리 중…",
  resumedChip: "이어 가기 · 이전 실행 {run}",
  loadingOlder: "이전 대화를 불러오는 중",
  startOfConversation: "대화의 처음입니다",
  newContent: "새 내용",
  jumpToPending: "응답 대기 카드로 이동",
  stop: "중지",
  stopping: "중지하는 중…",
  tokens: "토큰 {n}",
  someTokensTotalOnly: "일부는 총 토큰만",
  waitingFor: "응답 대기 {n}",
  turnStatus: {
    queued: "대기열",
    running: "실행 중",
    paused: "일시 정지",
    waiting: "응답 대기 중",
    completed: "완료",
    failed: "실패",
    cancelled: "취소됨",
    interrupted: "중단됨",
  },
  stepStatus: {
    running: "작업 중",
    succeeded: "완료",
    completed: "완료",
    failed: "실패",
    waiting: "응답 대기",
    skipped: "건너뜀",
    cancelled: "취소됨",
  },
  progressSummary: "진행 {n}단계",
  progressSummaryDuration: "진행 {n}단계 · {duration}",
  progressNow: "지금: {name}",
  moreSteps: "…외 {n}단계",
  sameSession: "같은 세션",
  childProgress: "노드 {done}/{total}",
  childCurrent: "현재: {name}",
  childOpen: "{name} 실행 상세",
  childOpenTip: "자식 실행 열기",
  childToggle: "{name} 단계 펼치기·접기",
  stepWarning: "주의",
  progressLabel: "진행 상황",
  listLabel: "대화",
  errorOpenRun: "실행 상세에서 원인 보기",
  units: { s: "초", m: "분", h: "시간" },
};
