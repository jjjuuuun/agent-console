import { describe, expect, test, vi } from "vitest";

import {
  createCurrentProjectStore,
  readProjectParam,
  resolveCurrentProject,
  writeProjectParam,
  type ProjectLocation,
  type ProjectStorage,
} from "@agent-console/projects";

function memStorage(initial: Record<string, string> = {}): ProjectStorage & { data: Record<string, string> } {
  const data = { ...initial };
  return {
    data,
    getItem: (k) => data[k] ?? null,
    setItem: (k, v) => void (data[k] = v),
    removeItem: (k) => void delete data[k],
  };
}
function memLocation(search = ""): ProjectLocation & { search: string } {
  const loc = { search, getSearch: () => loc.search, setSearch: (s: string) => void (loc.search = s) };
  return loc;
}

describe("주소 쿼리", () => {
  test("읽기: 없음 / 빈 값 / 값", () => {
    expect(readProjectParam("")).toBeUndefined();
    expect(readProjectParam("?project=")).toBeNull();
    expect(readProjectParam("?x=1&project=app")).toBe("app");
    expect(readProjectParam("?p=app", "p")).toBe("app");
  });
  test("쓰기: 다른 쿼리 보존, null이면 제거", () => {
    expect(writeProjectParam("?x=1", "app")).toBe("?x=1&project=app");
    expect(writeProjectParam("?x=1&project=app", null)).toBe("?x=1");
    expect(writeProjectParam("?project=app", null)).toBe("");
    expect(writeProjectParam("", "한글 id")).toBe("?project=%ED%95%9C%EA%B8%80+id");
  });
});

describe("resolveCurrentProject", () => {
  test("주소 > 저장 > 모든 프로젝트", () => {
    expect(resolveCurrentProject({ fromUrl: "a", fromStorage: "b" })).toBe("a");
    expect(resolveCurrentProject({ fromUrl: null, fromStorage: "b" })).toBeNull();
    expect(resolveCurrentProject({ fromStorage: "b" })).toBe("b");
    expect(resolveCurrentProject({})).toBeNull();
  });
  test("모르는 id는 버린다", () => {
    expect(resolveCurrentProject({ fromUrl: "x", known: ["a"] })).toBeNull();
    expect(resolveCurrentProject({ fromUrl: "a", known: ["a"] })).toBe("a");
  });
});

describe("createCurrentProjectStore", () => {
  test("저장소·주소 없이도 메모리로 동작하고 구독자에게 알린다", () => {
    const store = createCurrentProjectStore();
    const fn = vi.fn();
    const off = store.subscribe(fn);
    expect(store.get()).toBeNull();
    store.set("a");
    store.set("a");
    expect(fn).toHaveBeenCalledTimes(1);
    off();
    store.set(null);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(store.get()).toBeNull();
  });
  test("저장값으로 시작하고 주소에도 맞춘다", () => {
    const storage = memStorage({ "ac.project": "app" });
    const location = memLocation("?tab=1");
    const store = createCurrentProjectStore({ storage, location });
    expect(store.get()).toBe("app");
    expect(location.search).toBe("?tab=1&project=app");
  });
  test("주소가 저장값보다 우선하고 저장값을 갱신한다", () => {
    const storage = memStorage({ "ac.project": "app" });
    const store = createCurrentProjectStore({ storage, location: memLocation("?project=other") });
    expect(store.get()).toBe("other");
    expect(storage.data["ac.project"]).toBe("other");
  });
  test("set은 저장소와 주소에 반영, null이면 둘 다 지운다", () => {
    const storage = memStorage();
    const location = memLocation();
    const store = createCurrentProjectStore({ storage, location, storageKey: "k", param: "p" });
    store.set("a");
    expect(storage.data["k"]).toBe("a");
    expect(location.search).toBe("?p=a");
    store.set(null);
    expect(storage.data["k"]).toBeUndefined();
    expect(location.search).toBe("");
  });
  test("reconcile: 목록에 없으면 모든 프로젝트로 돌린다", () => {
    const store = createCurrentProjectStore({ storage: memStorage({ "ac.project": "gone" }) });
    const fn = vi.fn();
    store.subscribe(fn);
    store.reconcile(["a"]);
    expect(store.get()).toBeNull();
    expect(fn).toHaveBeenCalledTimes(1);
    store.set("a");
    store.reconcile(["a"]);
    expect(store.get()).toBe("a");
  });
  test("저장소가 던져도 죽지 않는다", () => {
    const bad: ProjectStorage = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("denied");
      },
      removeItem: () => {
        throw new Error("denied");
      },
    };
    const store = createCurrentProjectStore({ storage: bad });
    store.set("a");
    expect(store.get()).toBe("a");
  });
});
