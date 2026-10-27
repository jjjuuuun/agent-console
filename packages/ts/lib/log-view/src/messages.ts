/** 로그 표시 문구. 앱이 `messages` prop(부분 객체)으로 덮어쓴다. `{name}` 자리는 `fmt`로 채운다. */
export interface LogViewMessages {
  // 공통
  loading: string;
  empty: string;
  errorTitle: string;
  retry: string;
  none: string; // 값 없음 표시 ("–")
  copy: string;
  close: string;
  more: string; // [더 보기]
  // 이벤트 표
  eventTable: string;
  errorBadge: string;
  errorRow: string; // 오류 행 접근성 보충
  currentPosition: string;
  jumpToCurrent: string;
  groupBlocks: string; // {n}
  expandGroup: string;
  collapseGroup: string;
  moreLoading: string;
  noMore: string;
  noRows: string;
  columns: Record<string, string>; // 열 id -> 머리글(모르는 id는 id 원문)
  timeAbsolute: string;
  timeRelative: string;
  // 필터 막대
  filterBar: string;
  searchPlaceholder: string;
  searchLabel: string;
  addFilter: string;
  removeFilter: string; // {name}
  unknownFilter: string;
  filterValueLabel: string; // {name}
  timeSince: string;
  timeUntil: string;
  savedFilters: string;
  saveFilter: string;
  saveFilterName: string;
  noSavedFilters: string;
  applySaved: string; // {name}
  deleteSaved: string; // {name}
  clearFilters: string;
  multiMore: string; // {n}
  // 범주 칩
  categoryChips: string;
  allCategories: string;
  chipTitle: string; // {name} {total} {current}
  // 상세
  detailTitle: string;
  detailTabs: Record<string, string>; // overview detail raw evidence related
  detailEmpty: string;
  redactedNotice: string;
  detailTruncated: string;
  relatedTruncated: string;
  evidenceNotice: string;
  noDetail: string;
  usageNote: string;
  overview: Record<string, string>; // 필드 id -> 라벨
  /** `필드.값` -> 표시 문구(예: stage 값). 없으면 원문. */
  values: Record<string, string>;
  apply: string;
  openEvent: string;
  // 세션 목록
  sessionList: string;
  sessionLimit: string; // {n}
  sessionColumns: Record<string, string>;
  sortStartAsc: string;
  sortStartDesc: string;
  tokenTip: string;
  tokenOnce: string;
  // 재생 막대
  playback: string;
  play: string;
  pause: string;
  replay: string;
  prev: string;
  next: string;
  scrubber: string;
  speed: string;
  skipGaps: string;
  positionText: string; // {v} {n} {time} {title}
  beforeStart: string; // {n}
  playbackStarted: string;
  playbackPaused: string;
  playbackEnded: string;
  // 레인
  laneRibbon: string;
  laneLabel: string; // {name} {n}
  noLanes: string;
  // handoff
  handoffMatrix: string;
  handoffCell: string; // {from} {to} {n}
  handoffEmpty: string;
  handoffLimit: string; // {n}
  // 대시보드
  dashboard: string;
  widgetRefresh: string;
  widgetEdit: string;
  widgetRemove: string;
  widgetDuplicate: string;
  widgetMove: string;
  widgetNoData: string;
  widgetNoDataHint: string;
  widgetNullValue: string;
  widgetShowTable: string;
  widgetShowChart: string;
  widgetChartFailed: string;
  widgetChartLabel: string; // {title} {dims} {metric} {n}
  widgetMoreHidden: string; // {n}
  widgetUpdated: string; // {ago}
  widgetInvalid: string; // {message}
  widgetUntitled: string;
  dropAt: string;
  unknownWidget: string; // {kind}
  unknownWidgetHint: string;
  unknownWidgetJson: string;
  editJson: string;
  // 위젯 편집기
  editorTitle: string;
  editorKind: string;
  editorTitleField: string;
  editorMetric: string;
  editorGroupBy: string;
  editorAddDimension: string;
  editorRemoveDimension: string; // {name}
  editorFilter: string;
  editorOptions: string;
  editorPreview: string;
  editorApply: string;
  editorCancel: string;
  editorWidth: string;
  editorHeight: string;
  editorGroupByCount: string; // {min} {max}
  editorTimeFirst: string;
  editorTimeUnknown: string;
  editorKindRequired: string;
  editorMetricRequired: string;
  editorComboHint: string;
  // 템플릿
  templateTitle: string;
  templateNone: string;
  templateBlank: string;
  templateNew: string;
  templateAppend: string;
  templateApply: string;
  templateWidgets: string; // {n}
  templateUnknown: string; // {n}
  templateName: string;
  // 색 선택
  colorAuto: string;
  colorSlot: string; // {n}
  colorNeutral: string;
  // 단위
  units: { ms: string; s: string; m: string; h: string };
}

export const defaultLogViewMessages: LogViewMessages = {
  loading: "불러오는 중…",
  empty: "표시할 항목이 없습니다",
  errorTitle: "불러오지 못했습니다",
  retry: "다시 시도",
  none: "–",
  copy: "복사",
  close: "닫기",
  more: "더 보기",
  eventTable: "이벤트 표",
  errorBadge: "오류",
  errorRow: "오류 이벤트",
  currentPosition: "현재 위치",
  jumpToCurrent: "현재 위치로",
  groupBlocks: "응답 · {n}개 블록",
  expandGroup: "펼치기",
  collapseGroup: "접기",
  moreLoading: "더 불러오는 중…",
  noMore: "마지막 결과입니다",
  noRows: "조건에 맞는 이벤트가 없습니다",
  columns: {
    time: "시각", lane: "레인", category: "범주", title: "제목", duration: "소요", summary: "요약",
    stage: "단계", status: "상태", tool: "도구", model: "모델", run_id: "run_id", session: "세션", source: "출처", ref: "ref", cwd: "cwd",
  },
  timeAbsolute: "절대 시각으로 보기",
  timeRelative: "상대 시각으로 보기",
  filterBar: "필터",
  searchPlaceholder: "검색어",
  searchLabel: "검색어",
  addFilter: "+ 필터",
  removeFilter: "{name} 필터 지우기",
  unknownFilter: "알 수 없는 필터",
  filterValueLabel: "{name} 값",
  timeSince: "시작",
  timeUntil: "끝",
  savedFilters: "즐겨찾는 필터",
  saveFilter: "현재 필터 저장",
  saveFilterName: "저장할 이름",
  noSavedFilters: "저장된 필터가 없습니다",
  applySaved: "{name} 적용",
  deleteSaved: "{name} 삭제",
  clearFilters: "필터 지우기",
  multiMore: "+{n}",
  categoryChips: "범주 필터",
  allCategories: "전체",
  chipTitle: "전체 {total} · 현재 위치까지 {current}",
  detailTitle: "상세",
  detailTabs: { overview: "개요", detail: "상세 JSON", raw: "원문 JSON", evidence: "근거", related: "관련" },
  detailEmpty: "이벤트를 선택하세요",
  redactedNotice: "비밀로 의심되는 값은 저장 전에 가려진 사본입니다. 원본 파일은 읽기만 하며 바꾸지 않습니다.",
  detailTruncated: "내용이 길어 일부만 보입니다",
  relatedTruncated: "관련 이벤트가 많아 일부만 보입니다",
  evidenceNotice: "명시 id로 연결된 항목만 보여줍니다",
  noDetail: "상세가 없습니다",
  usageNote: "(스레드, 메시지)당 최대 출력 1회만 집계",
  overview: {
    source: "출처", ref: "ref", lane: "레인", route: "보낸 곳 → 받는 곳", via: "전달 수단", tool: "도구", call_id: "call_id", turn_id: "turn_id",
    message_id: "message_id", session: "세션", cwd: "cwd", model: "모델", run_id: "run_id", node_path: "노드 경로", stage: "단계", status: "상태",
    evidence: "근거", tags: "태그", usage: "토큰 표본", observed_at: "수집 시각", documents: "문서",
  },
  values: {},
  apply: "적용",
  openEvent: "이 이벤트 열기",
  sessionList: "세션 목록",
  sessionLimit: "상위 {n}개만 표시합니다. 기간이나 프로젝트로 좁혀 보세요.",
  sessionColumns: {
    start: "시작", session: "세션", title: "제목", project: "프로젝트", threads: "에이전트", events: "이벤트", errors: "오류", models: "모델", tokens: "토큰", length: "길이", source: "출처",
  },
  sortStartAsc: "시작 시각 오름차순",
  sortStartDesc: "시작 시각 내림차순",
  tokenTip: "입력 {input} · 출력 {output} · 캐시 읽기 {read} · 캐시 생성 {creation}",
  tokenOnce: "같은 응답은 한 번만 집계됩니다",
  playback: "재생",
  play: "재생",
  pause: "일시정지",
  replay: "처음부터 재생",
  prev: "이전 이벤트",
  next: "다음 이벤트",
  scrubber: "재생 위치",
  speed: "속도",
  skipGaps: "공백 건너뛰기",
  positionText: "{v}번째 / {n} · {time} · {title}",
  beforeStart: "시작 전 · 0 / {n}",
  playbackStarted: "재생 시작",
  playbackPaused: "재생 일시정지",
  playbackEnded: "재생이 끝났습니다",
  laneRibbon: "레인",
  laneLabel: "{name}, {n}개 이벤트",
  noLanes: "레인 정보가 없습니다 — 이벤트 표를 사용하세요",
  handoffMatrix: "위임 행렬",
  handoffCell: "{from}에서 {to}로 {n}회",
  handoffEmpty: "집계할 위임이 없습니다",
  handoffLimit: "횟수가 많은 상위 {n}개 연결만 표시합니다",
  dashboard: "대시보드",
  widgetRefresh: "이 위젯 새로 고침",
  widgetEdit: "위젯 편집",
  widgetRemove: "위젯 삭제",
  widgetDuplicate: "위젯 복제",
  widgetMove: "위젯 이동 (Ctrl+↑↓)",
  widgetNoData: "조건에 맞는 데이터가 없습니다",
  widgetNoDataHint: "필터와 기간을 확인하세요",
  widgetNullValue: "값 없음",
  widgetShowTable: "표로 보기",
  widgetShowChart: "차트로 보기",
  widgetChartFailed: "차트를 불러오지 못해 표로 보여줍니다",
  widgetChartLabel: "{title}: {dims} 별 {metric} 차트, {n}개 항목",
  widgetMoreHidden: "외 {n}개 항목은 표시하지 않았습니다",
  widgetUpdated: "{ago} 전",
  widgetInvalid: "위젯 설정이 올바르지 않습니다: {message}",
  widgetUntitled: "이름 없는 위젯",
  dropAt: "여기에 놓기",
  unknownWidget: "알 수 없는 위젯 ({kind})",
  unknownWidgetHint: "이 앱에서 그릴 수 없는 종류입니다. 설정은 그대로 보존됩니다.",
  unknownWidgetJson: "질의·옵션 JSON 보기",
  editJson: "JSON으로 편집",
  editorTitle: "위젯",
  editorKind: "종류",
  editorTitleField: "제목",
  editorMetric: "지표",
  editorGroupBy: "묶는 기준",
  editorAddDimension: "+ 차원 추가",
  editorRemoveDimension: "{name} 차원 빼기",
  editorFilter: "필터",
  editorOptions: "표시 옵션",
  editorPreview: "미리보기",
  editorApply: "위젯 적용",
  editorCancel: "취소",
  editorWidth: "너비(열)",
  editorHeight: "높이(행)",
  editorGroupByCount: "묶는 기준은 {min}~{max}개여야 합니다",
  editorTimeFirst: "첫 번째 차원은 시간 차원이어야 합니다",
  editorTimeUnknown: "시간 차원 여부를 확인할 수 없어 서버 검증에 맡깁니다",
  editorKindRequired: "종류를 고르세요",
  editorMetricRequired: "지표를 고르세요",
  editorComboHint: "목록에 없는 이름도 입력할 수 있습니다",
  templateTitle: "템플릿에서 시작",
  templateNone: "사용할 수 있는 템플릿이 없습니다. 빈 대시보드에서 위젯을 직접 추가하세요.",
  templateBlank: "빈 대시보드 만들기",
  templateNew: "새 대시보드로 만들기",
  templateAppend: "현재 대시보드에 위젯 추가",
  templateApply: "적용",
  templateWidgets: "위젯 {n}개",
  templateUnknown: "알 수 없는 위젯 {n}개",
  templateName: "대시보드 제목",
  colorAuto: "자동",
  colorSlot: "색 {n}",
  colorNeutral: "중립",
  units: { ms: "ms", s: "초", m: "분", h: "시간" },
};

/** 부분 messages를 기본값에 얕게 합친다(중첩 객체 `columns`·`overview` 등은 키 단위로 합친다). */
export function mergeMessages(partial?: DeepPartial<LogViewMessages>): LogViewMessages {
  const base = defaultLogViewMessages as unknown as Record<string, unknown>;
  const out: Record<string, unknown> = { ...base };
  if (partial) {
    for (const [k, v] of Object.entries(partial as Record<string, unknown>)) {
      if (v === undefined) continue;
      const b = base[k];
      out[k] = typeof v === "object" && v !== null && typeof b === "object" && b !== null ? { ...(b as object), ...(v as object) } : v;
    }
  }
  return out as unknown as LogViewMessages;
}

export type DeepPartial<T> = { [K in keyof T]?: T[K] extends string ? string : Partial<T[K]> };

/** `{name}` 자리 채우기. 없는 키는 그대로 둔다. */
export function fmt(template: string, vars: Record<string, string | number | null | undefined>): string {
  return template.replace(/\{(\w+)\}/g, (whole, key: string) => (key in vars && vars[key] != null ? String(vars[key]) : whole));
}
