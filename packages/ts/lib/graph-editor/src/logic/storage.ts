/** 브라우저 로컬 저장소 같은 키-값 저장소의 최소 형태(주입용). `window.localStorage`가 그대로 맞는다. */
export interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

/** 기본 저장소: 브라우저의 `localStorage`(접근이 막혔거나 없으면 `null` = 기억하지 않음). */
export function defaultStorage(): KeyValueStorage | null {
  try {
    return typeof window !== "undefined" && window.localStorage !== undefined ? window.localStorage : null;
  } catch {
    return null;
  }
}

/** JSON 값을 읽는다. 없거나 깨졌거나 저장소 오류면 `undefined`. */
export function readJson(storage: KeyValueStorage | null, key: string): unknown {
  if (storage === null) return undefined;
  try {
    const raw = storage.getItem(key);
    return raw === null ? undefined : (JSON.parse(raw) as unknown);
  } catch {
    return undefined;
  }
}

/** JSON 값을 쓴다. 실패(용량·권한)는 조용히 무시한다. */
export function writeJson(storage: KeyValueStorage | null, key: string, value: unknown): void {
  if (storage === null) return;
  try {
    storage.setItem(key, JSON.stringify(value));
  } catch {
    // 기억하지 못할 뿐 기능에는 영향이 없다
  }
}
