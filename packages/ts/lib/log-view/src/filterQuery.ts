import type { FilterFieldSpec, LogFilterValue } from "./types";

/**
 * 화면 전용 URL 파라미터 예약 목록(F-21). 이 이름은 `LogFilter`로 해석하지 않고 서버 요청에 싣지 않는다.
 * 서버 `LogFilter`에 같은 이름이 생기면 화면 파라미터 쪽 이름을 바꾸고 `findReservedConflicts`로 확인한다.
 */
export const reservedParams: readonly string[] = ["through", "lane", "view", "range", "tab"];

export interface SplitParams {
  /** 서버로 보낼 필터(예약 이름 제외, 알 수 없는 이름 포함). */
  filter: LogFilterValue;
  /** 화면 전용 파라미터(그대로 보존). */
  screen: Record<string, string[]>;
  /** 예약도 아니고 `fields`에도 없는 이름("알 수 없는 필터" 경고 대상). `fields`가 없으면 항상 빈 배열. */
  unknown: string[];
}

function toParams(input: string | URLSearchParams): URLSearchParams {
  return typeof input === "string" ? new URLSearchParams(input) : input;
}

/** URL 쿼리를 필터와 화면 전용 파라미터로 나눈다. 같은 이름이 반복되면 다중 값. 빈 값은 버린다. */
export function splitSearchParams(input: string | URLSearchParams, opts: { reserved?: readonly string[]; fields?: readonly FilterFieldSpec[] } = {}): SplitParams {
  const reserved = new Set(opts.reserved ?? reservedParams);
  const known = opts.fields ? new Set(opts.fields.map((f) => f.name)) : undefined;
  const params = toParams(input);
  const filter: LogFilterValue = {};
  const screen: Record<string, string[]> = {};
  const unknown: string[] = [];
  for (const name of new Set(params.keys())) {
    const values = params.getAll(name).filter((v) => v !== "");
    if (values.length === 0) continue;
    if (reserved.has(name)) {
      screen[name] = values;
      continue;
    }
    filter[name] = values.length === 1 ? (values[0] as string) : values;
    if (known && !known.has(name)) unknown.push(name);
  }
  return { filter, screen, unknown };
}

/** 필터를 서버 요청용 쿼리로. 예약 이름은 (실수로 들어 있어도) 제외한다. 반복 키 = 다중 값. */
export function buildFilterQuery(value: LogFilterValue, opts: { reserved?: readonly string[] } = {}): URLSearchParams {
  const reserved = new Set(opts.reserved ?? reservedParams);
  const out = new URLSearchParams();
  for (const [name, v] of Object.entries(value)) {
    if (reserved.has(name)) continue;
    for (const item of Array.isArray(v) ? v : [v]) if (item !== "") out.append(name, item);
  }
  return out;
}

/** 화면 URL 쓰기용: 필터 + 화면 전용 파라미터를 한 쿼리로. 화면 전용이 필터와 같은 이름이면 필터가 지고 화면 전용만 남는다. */
export function buildScreenSearch(value: LogFilterValue, screen: Record<string, readonly string[]>, opts: { reserved?: readonly string[] } = {}): URLSearchParams {
  const out = buildFilterQuery(value, opts);
  for (const [name, values] of Object.entries(screen)) for (const v of values) if (v !== "") out.append(name, v);
  return out;
}

/** 필드 이름 중 예약 이름과 겹치는 것(충돌 테스트용). */
export function findReservedConflicts(fieldNames: readonly string[], reserved: readonly string[] = reservedParams): string[] {
  const r = new Set(reserved);
  return fieldNames.filter((n) => r.has(n));
}

/** 필터가 하나라도 걸려 있는지(빈 값 제외). */
export function hasActiveFilter(value: LogFilterValue): boolean {
  return Object.values(value).some((v) => (Array.isArray(v) ? v.length > 0 : v !== ""));
}
