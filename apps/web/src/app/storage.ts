/** localStorage 접근을 try/catch로 감싼 안전한 래퍼. 실패하면 기본값/무시(메모리만 동작). */
export interface SafeStorage {
  get(key: string): string | null;
  set(key: string, value: string): void;
  remove(key: string): void;
  /** 저장된 모든 키(실패하면 빈 배열) */
  keys(): string[];
}

function browserStorage(): Storage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

/** @param storage 주입(테스트). 생략하면 `localStorage`. */
export function createSafeStorage(storage: Storage | null = browserStorage()): SafeStorage {
  return {
    get(key) {
      try {
        return storage?.getItem(key) ?? null;
      } catch {
        return null;
      }
    },
    set(key, value) {
      try {
        storage?.setItem(key, value);
      } catch {
        /* 저장 실패는 무시한다(메모리 상태로 계속 동작) */
      }
    },
    remove(key) {
      try {
        storage?.removeItem(key);
      } catch {
        /* 무시 */
      }
    },
    keys() {
      try {
        return storage === null ? [] : Array.from({ length: storage.length }, (_, i) => storage.key(i)).filter((k): k is string => k !== null);
      } catch {
        return [];
      }
    },
  };
}

export const appStorage: SafeStorage = createSafeStorage();

/** JSON 값을 읽는다. 없거나 깨졌으면 `fallback`. */
export function readJson<T>(storage: SafeStorage, key: string, fallback: T): T {
  const raw = storage.get(key);
  if (raw === null) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}
