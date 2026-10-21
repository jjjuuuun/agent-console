import type { ConditionItem, ConditionOperatorDescriptor, ConditionSpec } from "@agent-console/contracts";
import { delegationMessages } from "./messages";

/** 조건 항목·묶음은 계약 모델(`ConditionItem`·`ConditionSpec`)이 정한 모양이다. 연산자 id·경로 값은 데이터다. */
export type { ConditionItem, ConditionOperatorDescriptor, ConditionSpec };

/** 폼으로 그릴 수 있는 모드: 한 목록만 있거나 둘 다 없다. `both`는 폼으로 그릴 수 없다(데이터 보존). */
export type ConditionMode = "all" | "any";
export type ConditionShape = ConditionMode | "both" | "none";

const nonEmpty = (v: unknown): boolean => Array.isArray(v) && v.length > 0;

/** 조건 묶음의 모양. `all`·`any`가 둘 다 항목을 가지면 `both`(폼으로 그릴 수 없다). */
export function conditionShape(spec: ConditionSpec | null | undefined): ConditionShape {
  if (nonEmpty(spec?.all) && nonEmpty(spec?.any)) return "both";
  if (nonEmpty(spec?.all)) return "all";
  if (nonEmpty(spec?.any)) return "any";
  if (Array.isArray(spec?.all)) return "all";
  if (Array.isArray(spec?.any)) return "any";
  return "none";
}

/** 폼 모드(둘 다/없음이면 기본 `all`). */
export function formMode(spec: ConditionSpec | null | undefined): ConditionMode {
  const s = conditionShape(spec);
  return s === "any" ? "any" : "all";
}

/** 폼 모드의 항목 목록. */
export function itemsOf(spec: ConditionSpec | null | undefined): readonly ConditionItem[] {
  const s = conditionShape(spec);
  if (s === "any") return spec?.any ?? [];
  if (s === "all") return spec?.all ?? [];
  return [];
}

/** 항목 목록을 갈아 끼운 새 묶음(모르는 키는 보존, 다른 모드의 빈 목록은 지운다). 항목이 0개여도 모드 키는 남긴다. */
export function withItems(spec: ConditionSpec | null | undefined, mode: ConditionMode, items: readonly ConditionItem[]): ConditionSpec {
  const { all: _all, any: _any, ...rest } = (spec ?? {}) as ConditionSpec;
  void _all;
  void _any;
  return { ...rest, [mode]: [...items] };
}

/** 키 하나 없이 비어 있는 묶음인가. */
export function isEmptySpec(spec: ConditionSpec | null | undefined): boolean {
  if (spec === null || spec === undefined) return true;
  return Object.keys(spec).length === 0;
}

/** 모드를 바꾼 새 묶음: 항목은 그대로 두고 키만 `all` ↔ `any`로 옮긴다. */
export function switchMode(spec: ConditionSpec | null | undefined, mode: ConditionMode): ConditionSpec {
  const items = itemsOf(spec);
  const { all: _all, any: _any, ...rest } = (spec ?? {}) as ConditionSpec;
  void _all;
  void _any;
  return { ...rest, [mode]: [...items] };
}

/** `negate`를 켜면 true, 끄면 키를 지운다(기본값으로 채우지 않는 희소 저장). */
export function withNegate(spec: ConditionSpec | null | undefined, negate: boolean): ConditionSpec {
  const { negate: _n, ...rest } = (spec ?? {}) as ConditionSpec;
  void _n;
  return negate ? { ...rest, negate: true } : { ...rest };
}

// ---------------------------------------------------------------- 값 모양

/** 값 입력 모양(연산자 `value_schema`에서 정한다). */
export type ValueKind = "string" | "number" | "boolean" | "array" | "json" | "none";

type Schema = Record<string, unknown>;
const isObj = (v: unknown): v is Schema => typeof v === "object" && v !== null && !Array.isArray(v);

/** 값이 필요 없다는 스키마(`false` 또는 `{not: {}}`). */
export function forbidsValue(schema: unknown): boolean {
  if (schema === false) return true;
  if (!isObj(schema)) return false;
  const not = schema["not"];
  return isObj(not) && Object.keys(not).length === 0;
}

/**
 * 연산자 `value_schema`의 입력 모양. 비었거나(`{}`) 알 수 없으면 `undefined`(= 자유 입력 + 형식 선택).
 * `type`이 여럿(`["string","null"]`)이면 null을 뺀 첫 값을 본다.
 */
export function valueKindOf(schema: unknown): ValueKind | undefined {
  if (forbidsValue(schema)) return "none";
  if (!isObj(schema) || Object.keys(schema).length === 0) return undefined;
  const raw = schema["type"];
  const type = Array.isArray(raw) ? raw.find((x) => x !== "null") : raw;
  switch (type) {
    case "string":
      return "string";
    case "number":
    case "integer":
      return "number";
    case "boolean":
      return "boolean";
    case "array":
      return "array";
    case undefined:
      return undefined;
    default:
      return "json";
  }
}

/** 자유 입력에서 값을 어떤 형식으로 다룰지 기본값을 현재 값에서 추정한다(문자열이 기본). */
export function guessFreeKind(value: unknown): "string" | "number" | "boolean" | "json" {
  if (typeof value === "number") return "number";
  if (typeof value === "boolean") return "boolean";
  if (value !== null && typeof value === "object") return "json";
  return "string";
}

// ---------------------------------------------------------------- 요약

const ITEM_MAX = 36;

export type SummaryMessages = typeof delegationMessages.condition.summary;

export interface ConditionSummary {
  /** 칩·한 줄에 쓰는 문구(항목이 길면 말줄임) */
  text: string;
  /** 접근성 이름·툴팁·요약 줄에 쓰는 전문 */
  full: string;
  /** 항목이 0개 */
  empty: boolean;
}

function clip(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
}

/** 값 표시: 문자열 ‘값’, 숫자·불리언 그대로, 배열 `[a, b, …]`(3개 초과 `외 N개`), 객체 JSON 한 줄, 값 없음이면 빈 문자열. */
export function formatConditionValue(value: unknown, m: SummaryMessages = delegationMessages.condition.summary): string {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") return `‘${value}’`;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    const shown = value.slice(0, 3).map((v) => (typeof v === "string" ? v : JSON.stringify(v)));
    const more = value.length > 3 ? `, ${m.valueMore(value.length - 3)}` : "";
    return `[${shown.join(", ")}${more}]`;
  }
  try {
    return JSON.stringify(value) ?? "";
  } catch {
    return String(value);
  }
}

/**
 * 조건 요약(순수 함수): 입력 `(spec, operators, pathTitles)` → `{text, full, empty}`.
 * 항목 문구 `{경로 표시} {연산자 표시} {값 표시}`, 2개까지 접속사로 잇고 3개 이상이면 첫 2개 + `외 N개`, `negate`면 앞에 `아닌 경우: `.
 * 접속 단어는 `messages`(기본 한국어).
 */
export function summarizeConditions(
  spec: ConditionSpec | null | undefined,
  operators: readonly Pick<ConditionOperatorDescriptor, "id" | "title">[] | null | undefined,
  pathTitles: Readonly<Record<string, string>> | undefined,
  messages: SummaryMessages = delegationMessages.condition.summary,
): ConditionSummary {
  const items = itemsOf(spec);
  const mode = formMode(spec);
  if (conditionShape(spec) === "both") {
    // 폼으로 그릴 수 없는 묶음도 요약은 두 목록을 모두 센다
    const all = [...(spec?.all ?? []), ...(spec?.any ?? [])];
    return summarizeItems(all, " 그리고 ", operators, pathTitles, messages, spec?.negate === true);
  }
  return summarizeItems(items, mode === "any" ? messages.or : messages.and, operators, pathTitles, messages, spec?.negate === true);
}

function summarizeItems(
  items: readonly ConditionItem[],
  join: string,
  operators: readonly Pick<ConditionOperatorDescriptor, "id" | "title">[] | null | undefined,
  pathTitles: Readonly<Record<string, string>> | undefined,
  m: SummaryMessages,
  negate: boolean,
): ConditionSummary {
  if (items.length === 0) return { text: m.none, full: m.none, empty: true };
  const titleOf = new Map((operators ?? []).map((o) => [o.id, o.title]));
  const phrase = (item: ConditionItem): string => {
    const path = pathTitles?.[item.path] ?? item.path;
    const op = titleOf.get(item.op) ?? item.op;
    const value = formatConditionValue(item.value, m);
    return [path, op, value].filter((p) => p !== "").join(" ");
  };
  const phrases = items.map(phrase);
  const prefix = negate ? m.negate : "";
  const head = phrases.slice(0, 2).map((p) => clip(p, ITEM_MAX));
  const text = prefix + head.join(join) + (phrases.length > 2 ? m.more(phrases.length - 2) : "");
  const full = prefix + phrases.join(join);
  return { text, full, empty: false };
}

// ---------------------------------------------------------------- 판정 근거 어댑터

export interface ConditionItemOutcomeView {
  path: string;
  op: string;
  value?: unknown;
  actual?: unknown;
  hasActual: boolean;
  result: boolean;
  mode?: ConditionMode;
  reason?: string;
}

export interface ConditionOutcomeView {
  result: boolean;
  combinator?: ConditionMode;
  negate?: boolean;
  items?: ConditionItemOutcomeView[];
}

const isMode = (v: unknown): v is ConditionMode => v === "all" || v === "any";

/**
 * 연결 통과·건너뜀 이벤트의 조건 판정 근거를 화면이 읽는 모양으로 바꾸는 **유일한 곳**(S1).
 * 모양이 맞지 않으면 null이고, 호출자는 원본을 JSON으로 보인다. 키가 없으면 그 부분만 생략한다.
 */
export function mapConditionOutcome(raw: unknown): ConditionOutcomeView | null {
  if (!isObj(raw) || typeof raw["result"] !== "boolean") return null;
  const out: ConditionOutcomeView = { result: raw["result"] };
  if (isMode(raw["combinator"])) out.combinator = raw["combinator"];
  if (typeof raw["negate"] === "boolean") out.negate = raw["negate"];
  const items = raw["items"];
  if (items !== undefined && items !== null) {
    if (!Array.isArray(items)) return null;
    const mapped: ConditionItemOutcomeView[] = [];
    for (const it of items) {
      if (!isObj(it) || typeof it["path"] !== "string" || typeof it["op"] !== "string" || typeof it["result"] !== "boolean") return null;
      const view: ConditionItemOutcomeView = { path: it["path"], op: it["op"], result: it["result"], hasActual: "actual" in it && it["actual"] !== undefined };
      if ("value" in it && it["value"] !== undefined && it["value"] !== null) view.value = it["value"];
      if (view.hasActual) view.actual = it["actual"];
      if (isMode(it["mode"])) view.mode = it["mode"];
      if (typeof it["reason"] === "string") view.reason = it["reason"];
      mapped.push(view);
    }
    out.items = mapped;
  }
  return out;
}

/** 실제 값 한 줄 표시(문자열은 그대로, 그 밖은 JSON). `max` 초과면 잘리고 `truncated`가 true. */
export function actualPreview(actual: unknown, max = 180): { text: string; full: string; truncated: boolean } {
  const full = typeof actual === "string" ? actual : (() => {
    try {
      return JSON.stringify(actual) ?? String(actual);
    } catch {
      return String(actual);
    }
  })();
  return full.length > max ? { text: `${full.slice(0, max - 1)}…`, full, truncated: true } : { text: full, full, truncated: false };
}
