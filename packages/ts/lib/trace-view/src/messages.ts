import ko from "./locales/ko.json";

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

/** 기본 문구는 한국어(`locales/ko.json`). 영어는 `@agent-console/trace-view/locales/en`을 `messages`로 넘긴다. */
export const defaultTraceMessages: TraceMessages = ko;
