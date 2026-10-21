/**
 * 로그 화면의 데이터 표(`docs/design/screen-logs.md`). 탭·필터 필드·기간 프리셋·열·시간 상수·저장소 키가 전부 여기 있고,
 * 화면 코드는 이 표만 읽는다. 범주·출처·위젯·차원·지표 이름은 이 파일에도 없다(서버 데이터).
 * 필터 필드 이름은 서버 `LogFilter` 이름(`GET /logs/schema`의 `filters`)이며, 서버에 이름이 늘면 한 줄만 더한다.
 */
import type { FilterInput } from "@agent-console/log-view";
import { LOG_PROJECT_UNGROUPED } from "@agent-console/contracts";
import { logsMessages as t } from "./messages";
import data from "./logsData.json";

/** 이 화면이 맡는 역할(라우트 `serves`·`requires`와 같은 값). 모듈 id가 아니다. */
export const LOGS_ROLE = "logs";

/** 로그 상위 탭. `segment`는 `/logs/<segment>` 경로 조각. 순서 = 탭 순서(`Alt+숫자`). */
export const LOG_TABS = [
  { id: "sessions", segment: "sessions" },
  { id: "search", segment: "search" },
  { id: "dashboards", segment: "dashboards" },
] as const;
export type LogTabId = (typeof LOG_TABS)[number]["id"];
export const DEFAULT_LOG_TAB: LogTabId = "sessions";

/** 화면 상태를 저장하는 localStorage 키(서버 설정이 아니다). */
export const LOGS_STORAGE = {
  lastTab: "ac.logs.lastTab",
  lastDashboard: "ac.logs.lastDashboard",
  timeMode: "ac.logs.timeMode",
  speed: "ac.logs.speed",
  skipGaps: "ac.logs.skipGaps",
  flowCollapsed: "ac.logs.flow.collapsed",
  flowHeight: "ac.logs.flow.height",
  detailWidth: "ac.logs.detailW",
  openedSession: "ac.logs.openedSession",
  colsSessions: "ac.logs.cols.sessions",
  colsSession: "ac.logs.cols.session",
  savedFilters: "ac.logs.savedFilters",
  autoRefresh: "ac.logs.dash.auto",
  /** 첫 사용 배너 D의 닫힘 표시(`ac.hint.<id>`의 id) */
  hintOtherSources: "logs",
} as const;

/** 화면 숫자(디바운스·상한·기본 크기). 명세 표의 값이며 코드 분기가 아니다. */
export const LOGS_LIMITS = {
  eventsPage: 100,
  sessionsPage: 200,
  runLogsPage: 100,
  searchMaxLength: 500,
  liveDebounceMs: 2000,
  sourcesDebounceMs: 1000,
  dashboardDebounceMs: 5000,
  runTabDebounceMs: 1000,
  previewDebounceMs: 400,
  maxConcurrentAggregates: 4,
  /** 상세 캐시 시간(uid별) */
  detailStaleMs: 5 * 60_000,
  /** 큰 세션 안내 기준(L11 임시안): 진행 문구 / 느림 배너 */
  bigSessionProgress: 5_000,
  bigSessionWarn: 20_000,
  /** 스크러버 오류 틱 최대 */
  maxErrorTicks: 200,
  detailWidthMin: 320,
  detailWidthMax: 640,
  detailWidthDefault: 440,
  /** 이 폭 미만이면 상세 패널이 드로어가 된다 */
  drawerBelow: 1280,
  deleteHistory: 10,
  deleteToastMs: 5000,
  tableMinRows: 8,
  /** 표 한 행 높이(dense, px) — 최소 행 수와 곱해 흐름 패널 자동 접기 기준을 만든다 */
  tableRowHeight: 32,
  flowHeightMin: 96,
  flowHeightMax: 480,
  flowHeightDefault: 240,
} as const;

export interface RangePreset {
  id: string;
  /** 지금부터 거슬러 올라갈 초. null = 전체(기간 제한 없음) */
  seconds: number | null;
}
/** 화면 전용 URL 파라미터 이름(서버 필터가 아니다 — `log-view`의 `reservedParams`와 같은 목록, 충돌 테스트가 확인한다). */
export const SCREEN_PARAMS = { through: "through", lane: "lane", view: "view", range: "range", tab: "tab" } as const;

/** 기간 프리셋. 화면 전용 URL 파라미터 `range`의 값이 이 id다(`all`은 기간 없음). */
export const RANGE_PRESETS: readonly RangePreset[] = [
  { id: "1h", seconds: 3600 },
  { id: "24h", seconds: 86_400 },
  { id: "7d", seconds: 7 * 86_400 },
  { id: "30d", seconds: 30 * 86_400 },
  { id: "all", seconds: null },
];
/** 목록 화면별 기본 기간(화면 선택이며 서버 기본이 아니다). */
export const DEFAULT_RANGE: Readonly<Record<"sessions" | "search", string>> = { sessions: "7d", search: "24h" };
/** 사용자 지정 기간의 `range` 값 구분자(`<since ISO>..<until ISO>`). */
export const CUSTOM_RANGE_SEP = "..";

/** 필터 값 입력 방식과 선택지 소스(이름만 있고 값은 서버 데이터). */
export type FilterOptionsSource = "sources" | "categories" | "projects";
export interface FilterFieldDef {
  name: string;
  input: FilterInput;
  optionsFrom?: FilterOptionsSource;
}

/** 이름 데이터(`logsData.json`). 서버 필터 이름이 늘면 그 파일에 한 줄을 추가한다(화면 코드 분기 없음). */
export const FILTER_FIELDS: readonly FilterFieldDef[] = data.filterFields as FilterFieldDef[];
/** 검색어 필드 이름(항상 보이는 입력). */
export const SEARCH_FIELD: string = data.searchField;
/** 화면 코드가 직접 다뤄야 하는 필터 이름(칩 선택 → `category` 등). 이름은 데이터에서만 온다. */
export const FILTER_KEYS = data.filterKeys;

/** 필터 이름 → 이벤트 필드(제안 목록을 불러온 항목에서 뽑는 용도). */
export const SUGGEST_FROM: Readonly<Record<string, string>> = data.suggestFrom;

/** 검색 화면의 보기 id 목록(첫째 = 이벤트 표, 둘째 = 위임 행렬). 이름은 데이터 파일에서 온다. */
export const SEARCH_VIEWS: readonly string[] = data.searchViews;

export const SESSION_COLUMN_IDS: readonly string[] = data.sessionColumns.all;
export const SESSION_COLUMNS_DEFAULT: readonly string[] = data.sessionColumns.default;
export const EVENT_COLUMN_IDS: readonly string[] = data.eventColumns.all;
export const SESSION_EVENT_COLUMNS_DEFAULT: readonly string[] = data.eventColumns.session;
export const SEARCH_EVENT_COLUMNS_DEFAULT: readonly string[] = data.eventColumns.search;
export const RUN_TAB_COLUMNS: readonly string[] = data.eventColumns.runTab;
/** 열 id 중 화면 코드가 특별히 다루는 것(시각 표기 전환·레인 필터 등). */
export const CELL_IDS = data.cellIds;

/** 묶이지 않은 항목 정책 선택지(계약 `LogUngroupedPolicy` 값 + 문구 키). 값이 목록에 없으면 원문으로 보존한다. */
export const UNGROUPED_OPTIONS: readonly { value: string; label: string; description: string }[] = [
  { value: "cwd", label: t.settings.projects.ungrouped.cwd.label, description: t.settings.projects.ungrouped.cwd.description },
  { value: "repo_root", label: t.settings.projects.ungrouped.repo_root.label, description: t.settings.projects.ungrouped.repo_root.description },
  { value: "none", label: t.settings.projects.ungrouped.none.label, description: t.settings.projects.ungrouped.none.description },
];

/** 분류 체계 `tone`의 알려진 어휘(계약 문서 상수). 모르는 값은 원문 그대로 보존한다. */
export const TONE_VOCABULARY: readonly string[] = ["danger", "warning", "success", "info", "neutral"];
/** 오류 행으로 보는 tone(판정은 log-view `isErrorEvent` 한 곳. 여기는 편집 화면 라벨용). */
export const ERROR_TONE = "danger";

/** 프로젝트 필터의 "묶이지 않음" 값(계약 상수). */
export const UNGROUPED_PROJECT_VALUE = LOG_PROJECT_UNGROUPED;

/** 대시보드 기본 격자 열 수와 좁은 화면 열 수. */
export const DASHBOARD_COLUMNS = { wide: 12, narrow: 6, narrowBelow: 1280 } as const;

/** 서버 가림 경고 코드(서버 정보 경고 목록에서 찾는다). */
export const WARNING_CODES = { redactionUnavailable: "logs.redaction_unavailable", unknownClassifier: "logs.unknown_classifier" } as const;

/** 단축키 범위(라우트의 `shortcutScopes`와 같은 값). */
export const LOGS_SCOPES = { common: "logs", session: "logs-session", search: "logs-search", dashboard: "logs-dashboard" } as const;

/** 보관본 형식 목록. */
export const ARCHIVE_FORMATS = ["html", "json"] as const;
