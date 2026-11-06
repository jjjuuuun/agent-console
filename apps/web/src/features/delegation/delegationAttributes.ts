import { KNOWN_DELEGATION_BACKENDS as BACKENDS, KNOWN_DELEGATION_SESSIONS as SESSIONS } from "@agent-console/contracts/constants";
import type { DelegationStrategyDescriptor, EdgeSpec, EdgeTypeDescriptor } from "@agent-console/contracts";
import { effectiveStrategyId } from "./edgeChips";
import { delegationMessages as dm } from "./messages";

/**
 * 위임 방식·연결 종류의 화면용 속성 어댑터(screen-delegation.md §14.2·§14.9). 화면은 이 파일이 돌려주는 값만 쓴다.
 * 계약 키 이름이 바뀌면 `ATTRIBUTE_SOURCE`만 고친다. 방식·연결 종류 id는 여기에 없다.
 */

/** 속성 표시에 쓰는 방식의 부분 모양(디스크립터 전체가 아니어도 된다). 값이 없거나 null이면 그 속성은 "없음"이다. */
export type StrategyAttributeSource = Partial<Pick<DelegationStrategyDescriptor, "session" | "max_depth" | "backend" | "nestable">>;

/** 표시 행 하나의 데이터. 값 문구는 메시지 표에서 온다. 표에 없는 값은 `raw`를 원문(mono)으로 보인다. */
export interface AttributeCell {
  key: string;
  label: string;
  /** 서버 값 그대로 */
  raw: string | number | boolean | null;
  /** 긴 문구(행·비교표 아래). 위임자 이름이 필요한 문구는 `delegator`로 채운다 */
  long: string;
  /** 짧은 문구(옵션 보조 줄·비교표 셀). 요약에서 생략하는 값은 undefined */
  short: string | undefined;
  /** 메시지 표에 없는 값(원문 mono로 보인다) */
  unknownValue: boolean;
}

/** 행 순서가 곧 화면 순서다(앱 데이터 한 곳). */
export const ATTRIBUTE_ROWS: readonly string[] = ["session", "max_depth", "backend", "nestable"];

/** 속성 키 → 디스크립터 필드. 계약 키가 다르면 여기만 바꾼다. */
const ATTRIBUTE_SOURCE: Readonly<Record<string, keyof StrategyAttributeSource>> = { session: "session", max_depth: "max_depth", backend: "backend", nestable: "nestable" };

const isText = (v: unknown): v is string => typeof v === "string" && v !== "";

/** 방식의 실행 세션 값. 없거나 빈 문자열이면 undefined(칩·패턴·행을 만들지 않는다). */
export function sessionOf(strategy: StrategyAttributeSource | undefined): string | undefined {
  const v = strategy?.[ATTRIBUTE_SOURCE["session"] as "session"];
  return isText(v) ? v : undefined;
}

/**
 * 연결의 세션 값. 위임 연결(`invocation`)은 유효 방식의 `session`(연결 설정 덮어쓰기 → 종류 기본)이고,
 * 그 밖의 연결은 종류 디스크립터의 `session`이다. 방식을 목록에서 못 찾으면 undefined.
 */
export function edgeSessionOf(
  edge: Pick<EdgeSpec, "config">,
  kind: Pick<EdgeTypeDescriptor, "invocation" | "session"> | undefined,
  strategies: readonly (Pick<DelegationStrategyDescriptor, "id"> & StrategyAttributeSource)[],
): string | undefined {
  if (kind === undefined) return undefined;
  if (kind.invocation != null) {
    const id = effectiveStrategyId(edge, kind);
    return id === undefined ? undefined : sessionOf(strategies.find((s) => s.id === id));
  }
  return isText(kind.session) ? kind.session : undefined;
}

/** 세션 값 → 칩 글자(표에 없는 값은 원문). */
export function sessionText(value: string): string {
  return dm.session.value[value] ?? value;
}

/** 세션 값 → 툴팁/접근성 설명. */
export function sessionTip(value: string, delegator?: string): string {
  if (value === SESSIONS.SAME) return delegator === undefined || delegator === "" ? dm.session.tipSameNoDelegator : dm.session.tipSame(delegator);
  if (value === SESSIONS.SEPARATE) return dm.session.tipSeparate;
  return dm.session.unknownTip(value);
}

/** 방식의 속성 행들(표 순서). 디스크립터에 값이 없는 속성은 행을 만들지 않는다. 방식이 undefined면 빈 배열. */
export function attributeRows(strategy: StrategyAttributeSource | undefined, delegator = ""): AttributeCell[] {
  if (strategy === undefined) return [];
  const out: AttributeCell[] = [];
  for (const key of ATTRIBUTE_ROWS) {
    const field = ATTRIBUTE_SOURCE[key];
    if (field === undefined) continue;
    const raw = strategy[field];
    const delegatorText = delegator === "" ? dm.attr.delegatorFallback : delegator;
    if (key === "session") {
      if (!isText(raw)) continue;
      const long = dm.attr.session.long;
      const known = raw === SESSIONS.SAME || raw === SESSIONS.SEPARATE;
      out.push({ key, label: dm.attr.session.label, raw, long: raw === SESSIONS.SAME ? long.same(delegatorText) : raw === SESSIONS.SEPARATE ? long.separate : raw, short: dm.attr.session.short[raw as "same"] ?? raw, unknownValue: !known });
    } else if (key === "max_depth") {
      if (raw === undefined) continue;
      const l = dm.attr.max_depth.long;
      const s = dm.attr.max_depth.short;
      if (raw === null) out.push({ key, label: dm.attr.max_depth.label, raw, long: l.none, short: s.none, unknownValue: false });
      else if (typeof raw === "number") out.push({ key, label: dm.attr.max_depth.label, raw, long: raw === 1 ? l.one : l.n(raw), short: s.n(raw), unknownValue: false });
    } else if (key === "backend") {
      if (!isText(raw)) continue;
      const l = dm.attr.backend.long;
      const known = raw === BACKENDS.DELEGATOR || raw === BACKENDS.TARGET;
      out.push({ key, label: dm.attr.backend.label, raw, long: known ? l[raw as "delegator"] : raw, short: known ? dm.attr.backend.short[raw as "delegator"] : raw, unknownValue: !known });
    } else if (key === "nestable") {
      if (typeof raw !== "boolean") continue;
      out.push({ key, label: dm.attr.nestable.label, raw, long: raw ? dm.attr.nestable.long.yes : dm.attr.nestable.long.no, short: raw ? dm.attr.nestable.short.yes : undefined, unknownValue: false });
    }
  }
  return out;
}

/** 옵션 보조 줄 요약: 짧은 문구를 표 순서로 " · "로 잇는다(값이 없는 속성은 건너뜀). */
export function attributeSummary(strategy: StrategyAttributeSource | undefined): string {
  return attributeRows(strategy)
    .flatMap((r) => (r.short === undefined ? [] : [r.short]))
    .join(" · ");
}

/** 방식에 표시할 속성이 하나라도 있는가("동작 방식" 블록을 만들지 결정). */
export function hasAttributes(strategy: StrategyAttributeSource | undefined): boolean {
  return attributeRows(strategy).length > 0;
}
