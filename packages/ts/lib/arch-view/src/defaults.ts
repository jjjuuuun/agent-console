/**
 * X24 확장 지점의 기본 대응표(docs/design/screen-architecture.md §2.1·§2.3).
 * 데이터에 들어 있는 `tone`·`style`·`view`·지표 이름은 열린 문자열이고, 여기 없으면 중립 모양으로 그린다.
 * 이 표는 prop(`tones`·`edgeStyles`·`metricKinds`)으로 더하거나 바꿀 수 있다. 값은 CSS 색이 아니라 토큰 변수 이름이다.
 */
import type { EdgeStyleSpec, MetricKindSpec } from "./types";

/** tone → 토큰 변수 이름. */
export const defaultTones: Readonly<Record<string, string>> = {
  blue: "--ac-cat-1",
  teal: "--ac-cat-2",
  pink: "--ac-cat-3",
  orange: "--ac-cat-4",
  gold: "--ac-cat-5",
  purple: "--ac-cat-6",
  sky: "--ac-cat-7",
  rose: "--ac-cat-8",
};
/** 모르는 tone·없음. */
export const NEUTRAL_TONE = "--ac-cat-neutral";

/** 연결 style → 선 모양. */
export const defaultEdgeStyles: Readonly<Record<string, EdgeStyleSpec>> = {
  request: { stroke: "--ac-cat-7" },
  return: { stroke: "--ac-cat-4" },
  inferred: { stroke: "--ac-edge", dash: "--ac-edge-pattern-1" },
};
/** 모르는 style·구조 연결. */
export const NEUTRAL_EDGE_STYLE: EdgeStyleSpec = { stroke: "--ac-edge", dash: "--ac-edge-pattern-1" };

/** 지표 이름 → 표기 종류. 선언 순서가 한 줄에 놓이는 우선 순서다(횟수 → 오류 → 토큰 → 소요). */
export const defaultMetricKinds: Readonly<Record<string, MetricKindSpec>> = {
  count: { kind: "times" },
  errors: { kind: "failures" },
  tokens: { kind: "tokenCount" },
  duration: { kind: "millis" },
  inferred_duration: { kind: "millis", inferred: true },
};

/**
 * 칸·연결 상태가 읽는 지표 두 개의 이름(서버 투영 어휘). 횟수가 observed여야 이벤트 표를 걸러낼 수 있고,
 * 오류 수가 0보다 크면 오류 모양을 입힌다. 이 밖의 지표 이름은 코드가 모른다.
 */
export const METRIC_COUNT = "count";
export const METRIC_ERRORS = "errors";

/** 토큰 변수 이름 형식. 이 모양이 아닌 값(임의 색)은 받지 않는다. */
const TOKEN_VAR = /^--ac-[a-z0-9-]+$/;
export function isTokenVar(name: unknown): name is string {
  return typeof name === "string" && TOKEN_VAR.test(name);
}

/** tone 이름을 토큰 변수로. 모르거나 잘못된 값이면 중립. */
export function resolveTone(tone: string | null | undefined, tones: Readonly<Record<string, string>> = defaultTones): string {
  if (!tone || !Object.prototype.hasOwnProperty.call(tones, tone)) return NEUTRAL_TONE;
  const v = tones[tone];
  return isTokenVar(v) ? v : NEUTRAL_TONE;
}

/** style 이름을 선 모양으로. 모르거나 잘못된 값이면 중립(점선). */
export function resolveEdgeStyle(style: string | null | undefined, styles: Readonly<Record<string, EdgeStyleSpec>> = defaultEdgeStyles): EdgeStyleSpec {
  if (!style || !Object.prototype.hasOwnProperty.call(styles, style)) return NEUTRAL_EDGE_STYLE;
  const s = styles[style];
  if (!s || !isTokenVar(s.stroke)) return NEUTRAL_EDGE_STYLE;
  return isTokenVar(s.dash) ? s : { stroke: s.stroke };
}

/** 기본 연결 style의 범례 문구 키(`messages`). 새 style은 `edgeLegend` prop으로 글자를 준다. */
export const defaultEdgeLegendKeys: Readonly<Record<string, string>> = {
  request: "legendRequest",
  return: "legendReturn",
  inferred: "legendStructural",
};
