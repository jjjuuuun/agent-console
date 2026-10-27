/**
 * 지표 표기 순수 함수(docs/design/screen-architecture.md §3). 어떤 상태도 값을 0으로 바꾸지 않는다.
 */
import type { ArchitectureMetric } from "@agent-console/contracts/architecture";
import { defaultMetricKinds } from "./defaults";
import { formatMessage, resolveMessages } from "./messages";
import type { ArchViewMessages } from "./messages";
import type { MetricKindSpec } from "./types";

export interface MetricText {
  /** 지표 이름(데이터의 키). */
  name: string;
  /** 칸 지표 줄·칩에 보이는 글자. */
  text: string;
  /** 접근 이름 조각. */
  aria: string;
  /** 정보 줄에 보이는 풀어 쓴 글자(전체 값). */
  long: string;
  status: ArchitectureMetric["status"];
  /** 값. 수집 안 됨이면 null이고 0이 아니다. */
  value: number | null;
  /** 추정 표기를 붙여야 한다(상태가 inferred이거나 지표가 늘 추정). */
  inferred: boolean;
  /** 수집 안 됨(값 없음). */
  missing: boolean;
}

export interface FormatMetricOptions {
  name?: string;
  kind?: MetricKindSpec["kind"];
  /** 늘 추정인 지표. */
  inferred?: boolean;
  /** 칩처럼 좁은 곳: 10,000 이상 횟수를 `12.4k`로. */
  compact?: boolean;
  /** 칸 줄 우선 순서를 정하는 지표 종류 표(기본 `defaultMetricKinds`). */
  kinds?: Readonly<Record<string, MetricKindSpec>>;
}

const trim1 = (n: number): string => (Math.round(n * 10) / 10).toString();

/** 천 단위 쉼표 정수. */
export function groupDigits(n: number): string {
  return Math.round(n).toLocaleString("en-US");
}

/** `12.4k` 같은 약식 수. 1,000 미만은 정수 그대로. */
export function abbreviateNumber(n: number): string {
  return Math.abs(n) < 1000 ? groupDigits(n) : `${trim1(n / 1000)}k`;
}

/** 밀리초를 `340ms`·`1.2s`로. */
export function formatDurationMs(ms: number, messages: ArchViewMessages = resolveMessages(), aria = false): string {
  if (ms < 1000) return formatMessage(aria ? messages.ariaDurationMs : messages.durationMs, { n: Math.round(ms) });
  return formatMessage(aria ? messages.ariaDurationS : messages.durationS, { n: trim1(ms / 1000) });
}

/**
 * 지표 하나를 표기로 바꾼다. `value: null`은 "–"/"수집 안 됨"이다.
 * @param metric 서버가 준 지표
 * @param messages 문구 표(생략하면 기본)
 */
export function formatMetric(metric: ArchitectureMetric, messages: ArchViewMessages = resolveMessages(), options: FormatMetricOptions = {}): MetricText {
  const name = options.name ?? "";
  const spec = options.kinds?.[name] ?? defaultMetricKinds[name];
  const kind = options.kind ?? spec?.kind ?? "number";
  const alwaysInferred = options.inferred ?? spec?.inferred ?? false;
  const value = metric.value === undefined ? null : metric.value;
  const missing = metric.status === "not_collected" || value === null;
  const inferred = !missing && (metric.status === "inferred" || alwaysInferred);
  const label = nameOf(kind, name, messages);
  if (missing) {
    return { name, text: messages.metricDash, aria: `${label} ${messages.metricNotCollected}`.trim(), long: `${label}: ${messages.metricNotCollected}`.trim(), status: "not_collected", value: null, inferred: false, missing: true };
  }
  let text: string;
  let aria: string;
  let long: string;
  switch (kind) {
    case "times": {
      const n = options.compact && value >= 10_000 ? abbreviateNumber(value) : groupDigits(value);
      text = options.compact ? n : formatMessage(messages.metricCount, { n });
      aria = formatMessage(messages.metricCount, { n: groupDigits(value) });
      long = `${label} ${groupDigits(value)}`;
      break;
    }
    case "failures":
      text = formatMessage(messages.metricErrors, { n: groupDigits(value) });
      aria = text;
      long = text;
      break;
    case "tokenCount":
      text = abbreviateNumber(value);
      aria = formatMessage(messages.metricTokens, { n: text });
      long = formatMessage(messages.metricTokens, { n: groupDigits(value) });
      break;
    case "millis":
      text = formatDurationMs(value, messages);
      aria = formatMessage(messages.metricDuration, { n: formatDurationMs(value, messages, true) });
      long = formatMessage(messages.metricDuration, { n: text });
      break;
    default:
      text = groupDigits(value);
      aria = `${label} ${text}`.trim();
      long = aria;
  }
  if (inferred) {
    text = `~${text} ${messages.metricInferred}`;
    aria = `${aria} ${messages.metricInferred}`;
    long = `${long} (${messages.metricInferred})`;
  }
  return { name, text, aria, long, status: metric.status, value, inferred, missing: false };
}

function nameOf(kind: MetricKindSpec["kind"], name: string, m: ArchViewMessages): string {
  switch (kind) {
    case "times": return m.metricNameCount;
    case "failures": return m.metricNameErrors;
    case "tokenCount": return m.metricNameTokens;
    case "millis": return m.metricNameDuration;
    default: return name;
  }
}

/** 지표 모음을 한 줄 우선 순서로 정렬해 표기 조각으로. 아는 이름은 `kinds` 선언 순서, 모르는 이름은 뒤에 데이터 순서로. */
export function metricPieces(
  metrics: Readonly<Record<string, ArchitectureMetric>> | undefined,
  messages: ArchViewMessages = resolveMessages(),
  options: { compact?: boolean; kinds?: Readonly<Record<string, MetricKindSpec>>; only?: readonly string[] } = {},
): MetricText[] {
  if (!metrics) return [];
  const kinds = options.kinds ?? defaultMetricKinds;
  const known = Object.keys(kinds);
  const names = Object.keys(metrics).filter((n) => !options.only || options.only.includes(n));
  const ordered = [...names.filter((n) => known.includes(n)).sort((a, b) => known.indexOf(a) - known.indexOf(b)), ...names.filter((n) => !known.includes(n))];
  return ordered.map((n) => formatMetric(metrics[n] as ArchitectureMetric, messages, { name: n, kinds, compact: options.compact }));
}

/**
 * 합계. `null`(수집 안 됨)은 더하지 않고, 하나라도 값이 없으면 합계가 있는 것만의 합임을 `complete: false`로 알린다.
 * 값이 모두 없으면 `total`은 null이다(0이 아니다).
 */
export function sumMetrics(values: ReadonlyArray<number | null | undefined>): { total: number | null; complete: boolean } {
  let total: number | null = null;
  let complete = true;
  for (const v of values) {
    if (v === null || v === undefined) complete = false;
    else total = (total ?? 0) + v;
  }
  return { total, complete };
}

/** 정렬용 키: 값 없음은 0이 아니라 맨 뒤. 오름차순 비교 함수. */
export function compareMetricValue(a: number | null | undefined, b: number | null | undefined): number {
  const an = a === null || a === undefined;
  const bn = b === null || b === undefined;
  if (an && bn) return 0;
  if (an) return 1;
  if (bn) return -1;
  return (a as number) - (b as number);
}
