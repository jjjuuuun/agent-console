import ko from "./locales/ko.json";

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
  /** 시각 열 머리의 표시 방식 메뉴 */
  timeMode: { label: string; datetime: string; time: string; elapsed: string };
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
  /** [+ 필터] 메뉴 맨 아래의 "현재 필터를 즐겨찾기로 저장…" 항목 */
  saveCurrentFilter: string;
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
  /** [재생 설정 ▾] 단추 이름(속도·공백 건너뛰기 팝오버) */
  playSettings: string;
  playSettingsShort: string;
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

/** 기본 문구는 한국어(`locales/ko.json`의 `messages`). 영어는 `@agent-console/log-view/locales/en`의 `messages`를 넘긴다. */
export const defaultLogViewMessages: LogViewMessages = ko.messages;

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
