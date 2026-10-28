/**
 * 범위 종류 표의 행 계산(순수 함수, 서버·화면을 모른다). 서버 병합 목록(저장된 설정 기준) 위에 편집 중인
 * `scope_kinds` 초안을 겹친다: 객체 = 사용자 종류, null = 끔, 키 없음 = 원래 종류로 돌아감.
 */
import type { MemoryScopeKindInfo, MemoryScopeSummary } from "@agent-console/contracts/memory";
import { KIND_SPEC_KEYS, ORIGIN } from "./memorySettingsConfig";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string | undefined => (typeof v === "string" ? v : undefined);

export interface KindRow {
  id: string;
  label: string;
  description: string;
  /** id 틀. 빈 문자열 = 범위 하나, null = 계산 범위(틀 없음) */
  template: string | null;
  origin: string;
  /** 사용자 종류가 덮어쓴 기본·플러그인 종류의 출처 */
  overrides: string | undefined;
  disabled: boolean;
  dirty: boolean;
  /** 그 종류의 항목 수 합계 */
  entries: number;
}

export interface KindRows {
  rows: KindRow[];
  /** 끈 종류(목록 아래 접힘) */
  disabled: KindRow[];
}

/** 사용자 덮어쓰기를 걷어 낸 원래 출처. 사용자만의 종류면 undefined. */
function baseOrigin(s: MemoryScopeKindInfo | undefined): string | undefined {
  if (s === undefined) return undefined;
  return s.origin === ORIGIN.user ? (s.overrides ?? undefined) : s.origin;
}

/** 종류 id → 항목 수 합계 */
export function entriesByKind(scopes: readonly MemoryScopeSummary[] | undefined): Map<string, number> {
  const out = new Map<string, number>();
  for (const s of scopes ?? []) out.set(s.scope.kind, (out.get(s.scope.kind) ?? 0) + s.entries);
  return out;
}

export function buildKindRows(
  list: readonly MemoryScopeKindInfo[] | undefined,
  draft: Obj,
  saved: Obj,
  includeDefaults: boolean,
  counts: ReadonlyMap<string, number>,
  same: (a: unknown, b: unknown) => boolean,
): KindRows {
  const server = new Map((list ?? []).map((k) => [k.kind, k]));
  const ids = [...new Set([...server.keys(), ...Object.keys(draft)])];
  const rows: KindRow[] = [];
  const disabled: KindRow[] = [];
  for (const id of ids) {
    const s = server.get(id);
    const d = draft[id];
    const base = baseOrigin(s);
    const dirty = !same(d, saved[id]);
    const make = (origin: string, overrides: string | undefined, off: boolean): KindRow => {
      const spec = isObj(d) ? d : undefined;
      return {
        id,
        label: str(spec?.[KIND_SPEC_KEYS.label]) ?? s?.label ?? id,
        description: str(spec?.[KIND_SPEC_KEYS.description]) ?? s?.description ?? "",
        template: spec === undefined ? (s?.id ?? null) : (str(spec[KIND_SPEC_KEYS.template]) ?? ""),
        origin,
        overrides,
        disabled: off,
        dirty,
        entries: counts.get(id) ?? 0,
      };
    };
    if (isObj(d)) rows.push(make(ORIGIN.user, base, false));
    else if (d === null) {
      if (base !== undefined) disabled.push(make(base, undefined, true));
    } else if (s !== undefined) {
      const origin = s.origin;
      if (origin === ORIGIN.default && !includeDefaults) continue;
      if (s.disabled === true) {
        // 저장은 끔인데 초안이 끔 표시를 지웠다 = 다시 켜는 중
        rows.push(make(base ?? origin, undefined, false));
      } else rows.push(make(origin, s.overrides ?? undefined, false));
    }
  }
  return { rows, disabled };
}

export type KindAction = "view" | "edit" | "clone" | "disable" | "enable" | "remove" | "revert";

/** 행 상태 → 행 동작 목록(명세 §10.3). */
export function kindActions(row: Pick<KindRow, "origin" | "overrides" | "disabled">): KindAction[] {
  if (row.disabled) return ["enable"];
  if (row.origin !== ORIGIN.user) return ["view", "clone", "disable"];
  return row.overrides === undefined ? ["edit", "remove"] : ["edit", "revert"];
}

/** 출처 → 사람이 읽는 이름. 모르는 값은 원문. */
export function originText(row: Pick<KindRow, "origin" | "overrides">, m: { default: string; user: string; userOverride: string; plugin: (name: string) => string }): string {
  if (row.origin === ORIGIN.user) return row.overrides === undefined ? m.user : m.userOverride;
  if (row.origin === ORIGIN.default) return m.default;
  if (row.origin.startsWith(ORIGIN.pluginPrefix)) return m.plugin(row.origin.slice(ORIGIN.pluginPrefix.length));
  return row.origin;
}
