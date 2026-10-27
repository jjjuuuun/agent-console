import { withJosa } from "./josa";

/** 구조도 표현 컴포넌트가 쓰는 문구. 값은 `{n}` 같은 자리표시자를 가진 틀이다(docs/design/screen-architecture.md §12). */
export const defaultMessages = {
  // 지표 (formatMetric)
  metricCount: "{n}회",
  metricErrors: "오류 {n}",
  metricTokens: "토큰 {n}",
  metricDuration: "소요 {n}",
  metricInferred: "추정",
  metricNotCollected: "수집 안 됨",
  metricDash: "–",
  metricNameCount: "횟수",
  metricNameErrors: "오류",
  metricNameTokens: "토큰",
  metricNameDuration: "소요",
  durationMs: "{n}ms",
  durationS: "{n}s",
  ariaDurationMs: "{n}밀리초",
  ariaDurationS: "{n}초",
  metricAvg: "평균",
  metricMax: "최대",
  metricSamples: "표본 {n}개",
  // 상태
  badgePartial: "부분",
  badgeEvent: "이벤트",
  edgeStructural: "구조 연결",
  edgeObserved: "관측",
  // 접근 이름
  ariaDiagram: "구조도: {title}",
  ariaSkip: "구조도를 건너뛰고 이벤트 표로 가기",
  ariaEdgeFlow: "{from}에서 {to|으로/로}",
  ariaPartial: "부분: {reason}",
  ariaHighlighted: "선택한 이벤트가 지나감",
  ariaZones: "영역",
  // 도구줄
  zoomIn: "확대",
  zoomOut: "축소",
  scaleReset: "100%로 되돌리기",
  fit: "맞춤",
  fitAuto: "자동 맞춤",
  fitWidth: "폭 맞춤",
  fitContain: "전체 맞춤",
  fit100: "100%",
  fitMoreBelow: "아래 칸 {n}개 ↓",
  fitMoreBelowHelp: "아래로 스크롤해 가려진 칸 보기",
  viewGroup: "보기 방식",
  viewDiagram: "그림",
  viewList: "목록",
  legend: "범례",
  close: "닫기",
  // 목록·정보 줄
  listCells: "칸 {n}",
  listEdges: "연결 {n}",
  listUnassigned: "분류 안 됨",
  listUnavailable: "수집 안 됨 항목 {n}",
  unavailableItem: "수집 안 됨: {item} — {reason}",
  hintEmpty: "칸이나 연결을 누르면 아래 표가 그 이벤트로 걸러집니다.",
  drill: "하위 구조도",
  preview: "미리보기",
  groupOthers: "그 밖 {n}",
  noName: "(이름 없음)",
  flow: "{from} → {to}",
  notCollectedHelp: "이 범위의 로그 출처가 기록하지 않습니다",
  // 범례
  legendRequest: "요청·호출",
  legendReturn: "결과·응답",
  legendStructural: "구조 연결(순서로만 아는 연결, 횟수 없음)",
  legendNotCollected: "수집 안 됨(이 범위의 로그 출처가 채울 수 없음)",
  legendPartial: "부분 수집(일부만 보임, 이유는 칸을 누르면)",
  legendInferred: "추정값(기록된 값이 아니라 계산한 값)",
  legendError: "오류가 있음",
  legendSelected: "이 칸으로 이벤트 표를 걸러 둠",
  legendHighlighted: "표에서 고른 이벤트가 지나간 곳",
  legendZone: "영역(점선은 모델 입력 준비·출력 처리·도구 순환 같은 안쪽 영역)",
  // 상태 화면
  loading: "구조도를 그리는 중…",
  empty: "그릴 칸이 없습니다.",
  layoutNote: "배치 미리보기 — 숫자와 수집 상태는 표시하지 않습니다.",
} as const;

export type ArchViewMessages = { [K in keyof typeof defaultMessages]: string };

/**
 * 틀의 `{이름}` 자리를 값으로 바꾼다. 없는 이름은 그대로 둔다.
 * `{이름|으로/로}`는 값 뒤에 받침에 맞는 조사(받침 있을 때/없을 때)를 붙인다(`josa`).
 */
export function formatMessage(template: string, vars: Record<string, string | number> = {}): string {
  return template.replace(/\{(\w+)(?:\|([^{}|]+))?\}/g, (m, k: string, pair?: string) => {
    if (!(k in vars)) return m;
    const v = String(vars[k]);
    return pair ? withJosa(v, pair) : v;
  });
}

/** 부분 문구 표를 기본 문구와 합친다. */
export function resolveMessages(partial?: Partial<ArchViewMessages>): ArchViewMessages {
  return partial ? { ...defaultMessages, ...partial } : defaultMessages;
}
