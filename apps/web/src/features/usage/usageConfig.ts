import type { RollupDimension } from "./usageLib";

/** 사용량 화면의 앱 기본값(데이터). 창 이름·출처 id는 여기에 없다. */

/** `/usage`·`/usage/sources` 자동 갱신 간격(ms). */
export const USAGE_POLL_MS = 30_000;

/** 대표값 규칙(기본)의 "공식" 신뢰 등급 값. 디스크립터 `trust` 문자열과 비교한다. */
export const OFFICIAL_TRUST = "official";

/** 집계 보기(차원) 목록. 표시 이름은 messages.rollup.views. */
export const USAGE_ROLLUP_VIEWS: readonly RollupDimension[] = ["agent_id", "graph_id", "model", "day"];
export const DEFAULT_ROLLUP_VIEW: RollupDimension = "agent_id";

/** 집계 기간 선택지(화면 선택). days가 null이면 전체. */
export const USAGE_ROLLUP_PERIODS: readonly { id: string; days: number | null }[] = [
  { id: "today", days: 1 },
  { id: "7d", days: 7 },
  { id: "30d", days: 30 },
];
export const DEFAULT_ROLLUP_PERIOD = "7d";

/**
 * 초기화까지 남은 시간이 이보다 길면 "N일 N시간" 대신 날짜로 보인다(초). 표시 기준 데이터.
 * 예: 월 한도가 먼 미래에 초기화되면 "초기화까지 41일"보다 날짜가 읽기 쉽다.
 */
export const RESET_DATE_AFTER_SECONDS = 30 * 86_400;

// ---------------------------------------------------------------- 사용량 표시기(usage-everywhere.md)

/** 사용량 화면의 전체 보고 조회 키. */
export const USAGE_REPORT_KEY = ["usage", "report"] as const;
/** 셸 표시기의 창 부분만 조회 키(`parts=windows`). 응답에 집계가 없으므로 전체 보고 키와 나눈다. */
export const USAGE_WINDOWS_KEY = ["usage", "windows"] as const;
/** 표시기가 요청하는 보고 부분(실행 기록을 읽지 않는 가벼운 응답, design §3R.5 E-14). */
export const INDICATOR_USAGE_PARTS: readonly string[] = ["windows"];
export const USAGE_SOURCES_KEY = ["usage", "sources"] as const;

/** 표시기가 "지금"을 갱신하는 간격(ms). 분 단위 표기라 15초면 충분하다. */
export const INDICATOR_NOW_MS = 15_000;
/** 출처 목록을 신선하다고 보는 시간(ms). 표시기는 주기 폴링 없이 이 시간만 캐시한다. */
export const INDICATOR_SOURCES_STALE_MS = 5 * 60_000;
/** 수동 새로 고침 연타 방지(ms). */
export const INDICATOR_REFRESH_GAP_MS = 5_000;
/** 좁은 화면 판정(플로팅 칩이 항목 하나만 보인다)과 그때 보일 항목 수. */
export const INDICATOR_NARROW_QUERY = "(max-width: 639px)";
export const INDICATOR_NARROW_MAX_ITEMS = 1;
/** 설정 화면에서 사용량 섹션 앵커. */
export const INDICATOR_SETTINGS_HASH = "#usage";
/** 단축키로 연 요약이 고정되는 시간(ms)과 호버 지연. */
export const INDICATOR_PEEK_MS = 6_000;
export const INDICATOR_HOVER_OPEN_MS = 300;
export const INDICATOR_HOVER_CLOSE_MS = 150;
/** 요약 팝오버에 그리는 최대 창 수. */
export const INDICATOR_POPOVER_MAX = 8;
/** 설정에 값이 없을 때 쓰는 "기본 단축키" 동작 id·키(사용자는 설정 `ui.keybindings`로 바꾼다). */
export const INDICATOR_PEEK_SHORTCUT = { id: "usage.peek", keys: "Alt+U", titleKey: "shortcuts.usagePeek" } as const;

/** 표시기를 놓을 곳 표(데이터). `host`는 셸이 표시기를 꽂는 자리 이름, `layout`은 모양. 새 배치 = 한 줄 추가. */
export const INDICATOR_HOSTS = { sidebarFooter: "sidebar-footer", sidebarHeader: "sidebar-header", float: "float" } as const;
export type IndicatorHost = (typeof INDICATOR_HOSTS)[keyof typeof INDICATOR_HOSTS];
export interface IndicatorPlacement {
  id: string;
  host: IndicatorHost;
  layout: "block" | "chip";
  corner?: "top-left" | "top-right" | "bottom-left" | "bottom-right";
}
export const INDICATOR_PLACEMENTS: readonly IndicatorPlacement[] = [
  { id: "sidebar-bottom", host: INDICATOR_HOSTS.sidebarFooter, layout: "block" },
  { id: "sidebar-top", host: INDICATOR_HOSTS.sidebarHeader, layout: "block" },
  { id: "float-bottom-right", host: INDICATOR_HOSTS.float, layout: "chip", corner: "bottom-right" },
  { id: "float-bottom-left", host: INDICATOR_HOSTS.float, layout: "chip", corner: "bottom-left" },
  { id: "float-top-right", host: INDICATOR_HOSTS.float, layout: "chip", corner: "top-right" },
];
/** 모르는 배치 id일 때 대신 쓰는 배치(표의 첫 줄). */
export const FALLBACK_PLACEMENT: IndicatorPlacement = INDICATOR_PLACEMENTS[0]!;

/** 항목에 보일 요소 표(데이터). 순서는 설정 `fields`가 정한다. 새 요소 = 한 줄 + 렌더 한 곳. */
export const INDICATOR_FIELD = { label: "label", value: "value", gauge: "gauge", reset: "reset", trust: "trust", observed: "observed" } as const;
export const INDICATOR_FIELDS: readonly string[] = Object.values(INDICATOR_FIELD);

/** 값 앞에 `~`를 붙이는 신뢰 등급(추정·비공식). 디스크립터 `trust` 문자열과 비교한다. */
export const APPROX_TRUST: readonly string[] = ["estimated", "unofficial"];
/** 사용량 화면의 연결 안내 앵커(미니의 "연결 방법" 링크가 가리킨다) */
export const USAGE_SETUP_HASH = "#setup";

/** 색 규칙 `tone` 표(데이터): id → 아이콘 글자(색 단독 금지)·색 토큰. 모르는 tone은 중립. 글자가 빈 tone(정상)은 글리프를 그리지 않는다(소음 제거). */
export const INDICATOR_TONES: Readonly<Record<string, { glyph: string; cssVar: string }>> = {
  info: { glyph: "ⓘ", cssVar: "--ac-info" },
  success: { glyph: "", cssVar: "--ac-success" },
  warning: { glyph: "▲", cssVar: "--ac-warning" },
  danger: { glyph: "✕", cssVar: "--ac-danger" },
};
