/** `localStorage`와 같은 모양(주입). 읽기·쓰기 실패는 삼키고 기본값으로 동작한다. */
export interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

/** 목록 보기 선택(묶는 기준·속성 키·정렬). */
export interface ViewState {
  groupBy?: string;
  attrKey?: string;
  sort?: string;
}

export const viewStorageKey = (listId: string): string => `ac.list.view.${listId}`;
export const collapsedStorageKey = (listId: string, groupById: string): string => `ac.list.collapsed.${listId}.${groupById}`;

/** 저장된 보기 상태를 읽는다. 없거나 깨졌으면 `fallback`. */
export function loadViewState(storage: KeyValueStorage | undefined, listId: string, fallback: ViewState = {}): ViewState {
  try {
    const raw = storage?.getItem(viewStorageKey(listId));
    if (raw === null || raw === undefined) return fallback;
    const parsed: unknown = JSON.parse(raw);
    if (parsed === null || typeof parsed !== "object") return fallback;
    const p = parsed as Record<string, unknown>;
    const out: ViewState = {};
    if (typeof p.groupBy === "string") out.groupBy = p.groupBy;
    if (typeof p.attrKey === "string") out.attrKey = p.attrKey;
    if (typeof p.sort === "string") out.sort = p.sort;
    return { ...fallback, ...out };
  } catch {
    return fallback;
  }
}

/** 보기 상태를 저장한다. 실패하면 false. */
export function saveViewState(storage: KeyValueStorage | undefined, listId: string, state: ViewState): boolean {
  try {
    storage?.setItem(viewStorageKey(listId), JSON.stringify(state));
    return storage !== undefined;
  } catch {
    return false;
  }
}

/** 접은 묶음 키들을 읽는다. */
export function loadCollapsed(storage: KeyValueStorage | undefined, listId: string, groupById: string): Set<string> {
  try {
    const raw = storage?.getItem(collapsedStorageKey(listId, groupById));
    if (raw === null || raw === undefined) return new Set();
    const parsed: unknown = JSON.parse(raw);
    return new Set(Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : []);
  } catch {
    return new Set();
  }
}

/** 접은 묶음 키들을 저장한다. 실패하면 false. */
export function saveCollapsed(storage: KeyValueStorage | undefined, listId: string, groupById: string, keys: ReadonlySet<string>): boolean {
  try {
    storage?.setItem(collapsedStorageKey(listId, groupById), JSON.stringify([...keys]));
    return storage !== undefined;
  } catch {
    return false;
  }
}
