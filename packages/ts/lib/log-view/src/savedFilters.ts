import type { SavedFilter, SavedFilterStore } from "./types";

export const MAX_SAVED_NAME = 40;

type StorageLike = Pick<Storage, "getItem" | "setItem">;

function isSaved(x: unknown): x is SavedFilter {
  if (typeof x !== "object" || x === null) return false;
  const o = x as Record<string, unknown>;
  return typeof o["name"] === "string" && typeof o["value"] === "object" && o["value"] !== null;
}

/**
 * 즐겨찾는 필터 저장소(브라우저 localStorage 기본 구현). `storage`·`key`는 주입한다.
 * 저장소가 없거나 실패해도 던지지 않고 메모리에만 둔다. 같은 이름은 덮어쓴다. 이름은 40자까지.
 */
export function createLocalStorageSavedFilters(key: string, storage?: StorageLike): SavedFilterStore {
  const target = (): StorageLike | undefined => {
    if (storage) return storage;
    try {
      return typeof localStorage === "undefined" ? undefined : localStorage;
    } catch {
      return undefined;
    }
  };
  let memory: SavedFilter[] = [];
  const read = (): SavedFilter[] => {
    try {
      const raw = target()?.getItem(key);
      if (raw == null) return memory;
      const parsed: unknown = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.filter(isSaved) : memory;
    } catch {
      return memory;
    }
  };
  const write = (list: SavedFilter[]) => {
    memory = list;
    try {
      target()?.setItem(key, JSON.stringify(list));
    } catch {
      /* 저장 실패는 메모리에만 남긴다 */
    }
  };
  return {
    list: read,
    save(filter) {
      const name = filter.name.trim().slice(0, MAX_SAVED_NAME);
      if (!name) return;
      write([...read().filter((f) => f.name !== name), { ...filter, name }]);
    },
    remove(name) {
      write(read().filter((f) => f.name !== name));
    },
  };
}
