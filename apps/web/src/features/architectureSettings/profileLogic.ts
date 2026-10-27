/**
 * 구조도 프로필 목록·편집의 순수 함수(화면·서버를 모른다). 프로필 안의 칸·연결 이름은 읽지 않는다.
 * 설정 문서의 `profiles` 맵(id -> 프로필 | null)과 서버 병합 목록을 맞춰 보여 줄 행을 만든다.
 */
import type { ArchitectureProfileInfo, ArchitectureProfileList } from "@agent-console/contracts";

export type ProfilesMap = Record<string, unknown>;

export interface ProfileRow {
  id: string;
  title: string;
  /** 보이는 출처(열린 문자열). 사용자 프로필이 덮어쓰면 사용자 출처 값 */
  origin: string;
  /** 사용자 프로필이 덮어쓴 기본·플러그인 프로필의 출처 */
  overrides: string | undefined;
  disabled: boolean;
  /** 저장된 설정과 달라졌다(저장 전 변경) */
  dirty: boolean;
  /** 검사 문제·칸·연결 수. 저장 전 변경이면 서버가 모르는 값이라 null */
  issues: number | null;
  cells: number | null;
  edges: number | null;
}

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

/** 값 깊은 비교(JSON 값). */
export function sameValue(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (Array.isArray(a)) return Array.isArray(b) && a.length === b.length && a.every((x, i) => sameValue(x, b[i]));
  if (isObject(a) && isObject(b)) {
    const ka = Object.keys(a);
    return ka.length === Object.keys(b).length && ka.every((k) => k in b && sameValue(a[k], b[k]));
  }
  return false;
}

/** 사용자 덮어쓰기를 걷어 낸 원래(기본·플러그인) 출처. 사용자만의 프로필이면 undefined. */
function baseOrigin(s: ArchitectureProfileInfo | undefined, userOrigin: string): string | undefined {
  if (s === undefined) return undefined;
  return s.origin === userOrigin ? (s.overrides ?? undefined) : s.origin;
}

export interface RowsResult {
  rows: ProfileRow[];
  /** 끈 프로필(목록 아래 접힘) */
  disabled: ProfileRow[];
}

/**
 * 서버 병합 목록(저장된 설정 기준) 위에 편집 중인 `profiles` 초안을 겹쳐 행을 만든다.
 * 초안에 객체가 있으면 사용자 프로필, null이면 끔, 키가 없으면 원래 프로필로 돌아간다.
 */
export function buildRows(list: ArchitectureProfileList | undefined, draft: ProfilesMap, saved: ProfilesMap, includeDefaults: boolean, origins: { isDefault: (origin: string) => boolean; user: string }): RowsResult {
  const server = new Map((list?.profiles ?? []).map((p) => [p.id, p]));
  const ids = [...new Set([...server.keys(), ...Object.keys(draft)])];
  const rows: ProfileRow[] = [];
  const disabled: ProfileRow[] = [];
  for (const id of ids) {
    const s = server.get(id);
    const d = draft[id];
    const base = baseOrigin(s, origins.user);
    const dirty = !sameValue(d, saved[id]);
    const bodyTitle = isObject(d) && typeof d["title"] === "string" && d["title"] !== "" ? d["title"] : undefined;
    const counts = !dirty && s !== undefined ? { issues: s.issues ?? 0, cells: s.cells ?? 0, edges: s.edges ?? 0 } : { issues: null, cells: null, edges: null };
    const make = (origin: string, overrides: string | undefined, off: boolean): ProfileRow => ({ id, title: bodyTitle ?? (s?.title && s.title !== "" ? s.title : id), origin, overrides, disabled: off, dirty, ...counts });
    if (isObject(d)) rows.push(make(origins.user, base, false));
    else if (d === null) {
      if (base !== undefined) disabled.push(make(base, undefined, true));
    } else if (base !== undefined) {
      if (origins.isDefault(base) && !includeDefaults) continue;
      rows.push(make(base, undefined, false));
    }
  }
  return { rows, disabled };
}

/** 프로필 하나를 사용자 프로필로 넣는다(같은 id면 통째로 바꾼다). */
export const setProfile = (profiles: ProfilesMap, id: string, body: unknown): ProfilesMap => ({ ...profiles, [id]: body });

/** 끄기: 그 id를 null로 둔다(기본·플러그인 프로필을 목록에서 뺀다). */
export const disableProfile = (profiles: ProfilesMap, id: string): ProfilesMap => ({ ...profiles, [id]: null });

/**
 * 지우기: 프로필 단위 null. 저장된 적 없는 프로필이면 키만 지운다(설정 파일에 null이 남지 않게).
 */
export function deleteProfile(profiles: ProfilesMap, id: string, saved: ProfilesMap): ProfilesMap {
  return saved[id] === undefined ? removeKey(profiles, id) : { ...profiles, [id]: null };
}

/** 다시 켜기·기본값으로 되돌리기: 그 id의 사용자 항목(덮어쓰기 또는 null)을 지운다. */
export function removeKey(profiles: ProfilesMap, id: string): ProfilesMap {
  const next = { ...profiles };
  delete next[id];
  return next;
}

/** 복제 기본 id(`{id}-custom`)가 이미 쓰이면 번호를 붙여 비어 있는 id를 낸다. */
export function suggestCloneId(id: string, taken: ReadonlySet<string>, suffix = "custom"): string {
  const first = `${id}-${suffix}`;
  if (!taken.has(first)) return first;
  for (let n = 2; ; n++) if (!taken.has(`${first}-${n}`)) return `${first}-${n}`;
}
