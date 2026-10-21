/** 위임 흐름 타임라인 문구. 앱이 `messages`로 덮어쓴다. */
export interface TraceMessages {
  treeLabel: string;
  empty: string;
  sameSession: string;
  separateSession: string;
  userWait: string; // {duration}
  statusText: Record<string, string>;
  /** 접근성 이름: "{name}, {method}, {status}, {duration}" */
  rowLabel: string;
  running: string;
  collapse: string;
  expand: string;
  showUserWait: string;
  follow: string;
  zoomIn: string;
  zoomOut: string;
  detailLabel: string;
  closeDetail: string;
  tokensTotal: string; // {n}
  /** 수치 열 툴팁. {n} = 총 토큰 */
  tokensTitle: string;
  /** 수치 열 토큰 단위 */
  tokensUnit: string;
  /** 방식 글자 표시 토글 */
  showMethodText: string;
  units: { s: string; m: string; h: string };
  /** 반복 회차 이름 뒤 표기. {n} = 회차 + 1 */
  iterationSuffix: string;
  /** 같은 노드를 여러 번 부른 호출 표기. {n} = 호출 번호 + 1 */
  callSuffix: string;
  /** 자식 실행 묶음 행 기본 제목. {id} = 자식 Run id 앞 6자 */
  childRunTitle: string;
  /** 묶음 행 보조 문구. {n} = 묶음 안 span 수 */
  groupSpanCount: string;
  /** 묶음 행 [열기] 버튼 */
  openChildRun: string;
  /** 묶음 행 접근성 이름 앞에 붙는 말 */
  childRunLabel: string;
  /** 키보드 안내(묶음 행) */
  groupHint: string;
}

export const defaultTraceMessages: TraceMessages = {
  treeLabel: "위임 흐름",
  empty: "위임 흐름이 없습니다 — 이 실행은 단일 에이전트로 처리되었습니다",
  sameSession: "같은 세션",
  separateSession: "별도 세션",
  userWait: "사용자 대기 {duration}",
  statusText: {
    running: "실행 중",
    succeeded: "완료",
    completed: "완료",
    failed: "실패",
    waiting: "응답 대기",
    skipped: "건너뜀",
    cancelled: "취소됨",
    pending: "대기",
    queued: "대기열",
    answered: "답함",
    expired: "만료",
    interrupted: "중단됨",
  },
  rowLabel: "{name}, {method}, {status}, {duration}",
  running: "진행 중",
  collapse: "접기",
  expand: "펼치기",
  showUserWait: "사용자 대기 포함",
  follow: "끝 따라가기",
  zoomIn: "확대",
  zoomOut: "축소",
  detailLabel: "상세",
  closeDetail: "닫기",
  tokensTotal: "{n} 토큰(총)",
  tokensTitle: "총 토큰 {n}",
  tokensUnit: "tok",
  showMethodText: "방식 글자 표시",
  units: { s: "초", m: "분", h: "시간" },
  iterationSuffix: " #{n}",
  callSuffix: " · 호출 {n}",
  childRunTitle: "자식 실행 {id}",
  groupSpanCount: "span {n}개",
  openChildRun: "열기",
  childRunLabel: "자식 실행",
  groupHint: "Enter로 접고 펴기, Ctrl+Enter로 자식 실행 열기",
};
