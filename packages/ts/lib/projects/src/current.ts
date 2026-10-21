/**
 * 현재 프로젝트 상태: 주소 쿼리(`?project=<id>`)와 브라우저 저장소를 오가는 작은 저장소.
 * React 등 프레임워크를 모른다(`subscribe`/`get`은 `useSyncExternalStore`에 그대로 쓸 수 있다).
 * 저장소·주소는 모두 주입한다(없으면 메모리만).
 *
 * 값: 프로젝트 id 문자열, `null` = 모든 프로젝트.
 */
import { normalizeScope, type CurrentProject } from "./scope";

/** 기본 주소 쿼리 이름. */
export const DEFAULT_PROJECT_PARAM = "project";
/** 기본 브라우저 저장 키(ux-overhaul §12.1). */
export const DEFAULT_PROJECT_STORAGE_KEY = "ac.project";

/** `Storage`의 부분 집합(테스트·다른 저장소 주입용). */
export interface ProjectStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/** 주소 쿼리 읽기·쓰기(`location.search`/`history.replaceState` 위에 앱이 얹는다). `search`는 `?a=b` 또는 `a=b`. */
export interface ProjectLocation {
  getSearch(): string;
  setSearch(search: string): void;
}

/**
 * 쿼리에서 프로젝트 값을 읽는다.
 * @returns 쿼리에 없으면 undefined, `?project=`처럼 비어 있으면 null(모든 프로젝트), 아니면 id
 */
export function readProjectParam(search: string, param: string = DEFAULT_PROJECT_PARAM): CurrentProject | undefined {
  const params = new URLSearchParams(search);
  if (!params.has(param)) return undefined;
  return normalizeScope(params.get(param));
}

/**
 * 쿼리에 프로젝트 값을 쓴다. null이면 쿼리에서 뺀다. 다른 쿼리는 그대로 두고, 결과는 `?`로 시작(비면 빈 문자열).
 */
export function writeProjectParam(search: string, id: CurrentProject, param: string = DEFAULT_PROJECT_PARAM): string {
  const params = new URLSearchParams(search);
  const v = normalizeScope(id);
  if (v === null) params.delete(param);
  else params.set(param, v);
  const out = params.toString();
  return out === "" ? "" : `?${out}`;
}

/**
 * 시작 값 정하기: 주소 > 저장값 > 모든 프로젝트.
 * @param known 존재하는 프로젝트 id. 주면 거기 없는 값은 버리고 null(모든 프로젝트)로 한다.
 */
export function resolveCurrentProject(input: {
  fromUrl?: CurrentProject | undefined;
  fromStorage?: CurrentProject | undefined;
  known?: Iterable<string> | undefined;
}): CurrentProject {
  const picked = input.fromUrl !== undefined ? input.fromUrl : (input.fromStorage ?? null);
  if (picked === null || input.known === undefined) return picked;
  return new Set(input.known).has(picked) ? picked : null;
}

export interface CurrentProjectStoreOptions {
  storage?: ProjectStorage | undefined;
  location?: ProjectLocation | undefined;
  /** 저장 키. 기본 `ac.project`. */
  storageKey?: string;
  /** 쿼리 이름. 기본 `project`. */
  param?: string;
  /** 시작 때부터 알고 있는 프로젝트 id(보통은 목록을 받은 뒤 `reconcile`로 정리한다). */
  known?: Iterable<string>;
}

export interface CurrentProjectStore {
  /** 현재 값(null = 모든 프로젝트). */
  get(): CurrentProject;
  /** 바꾼다. 저장소·주소에도 반영하고 구독자에게 알린다. 값이 같으면 아무것도 하지 않는다. */
  set(id: CurrentProject): void;
  /** 값이 바뀔 때 부른다. 해제 함수를 돌려준다. */
  subscribe(listener: () => void): () => void;
  /** 프로젝트 목록을 받은 뒤 호출: 현재 값이 목록에 없으면 모든 프로젝트로 돌린다. */
  reconcile(known: Iterable<string>): void;
}

function safe<T>(fn: () => T): T | undefined {
  try {
    return fn();
  } catch {
    return undefined;
  }
}

/**
 * 현재 프로젝트 저장소를 만든다. 저장소 접근 실패(사생활 모드 등)는 던지지 않고 메모리에만 둔다.
 */
export function createCurrentProjectStore(options: CurrentProjectStoreOptions = {}): CurrentProjectStore {
  const { storage, location } = options;
  const key = options.storageKey ?? DEFAULT_PROJECT_STORAGE_KEY;
  const param = options.param ?? DEFAULT_PROJECT_PARAM;

  const stored = storage === undefined ? undefined : safe(() => storage.getItem(key));
  const search = location === undefined ? undefined : safe(() => location.getSearch());
  let current = resolveCurrentProject({
    fromUrl: search === undefined ? undefined : readProjectParam(search, param),
    fromStorage: stored === undefined ? undefined : normalizeScope(stored),
    known: options.known,
  });
  const listeners = new Set<() => void>();

  const persist = (): void => {
    if (storage !== undefined) {
      safe(() => {
        if (current === null) storage.removeItem(key);
        else storage.setItem(key, current);
      });
    }
    if (location !== undefined) {
      safe(() => {
        const now = location.getSearch();
        if ((readProjectParam(now, param) ?? null) !== current) location.setSearch(writeProjectParam(now, current, param));
      });
    }
  };
  // 저장값으로 시작했는데 주소에 없으면 주소에도 맞춘다(공유 가능하게).
  persist();

  const set = (id: CurrentProject): void => {
    const next = normalizeScope(id);
    if (next === current) return;
    current = next;
    persist();
    for (const l of [...listeners]) l();
  };

  return {
    get: () => current,
    set,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    reconcile(known) {
      if (current !== null && !new Set(known).has(current)) set(null);
    },
  };
}
