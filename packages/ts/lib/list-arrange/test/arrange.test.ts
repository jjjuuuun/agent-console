import { describe, expect, test } from "vitest";

import {
  NONE_KEY, availableSorts, buildFolderTree, byNumber, byText, flattenFolderTree, folderOf, groupItems, hasNamedGroups,
  loadCollapsed, loadViewState, resolveGroupBy, resolveSort, revealGroup, saveCollapsed, saveViewState, sortItems,
  uniqueCount, usableUnlessAllDistinct, visibleGroups, withFolder, type GroupByDef, type KeyValueStorage, type SortDef,
} from "../src";

interface Row { id: string; tags: string[]; path?: string; n?: number }
const rows: Row[] = [
  { id: "a", tags: ["x", "y"], path: "개발팀" },
  { id: "b", tags: ["y"], path: "개발팀/백엔드" },
  { id: "c", tags: [] },
];
const tags: GroupByDef<Row> = { id: "tags", titleKey: "t", multi: true, read: (r) => r.tags };
const path: GroupByDef<Row> = { id: "path", titleKey: "p", tree: true, read: (r) => (r.path === undefined ? [] : [r.path]) };

describe("groupItems", () => {
  test("임의 필드·multi: 여러 묶음에 보이고 없음은 맨 아래", () => {
    const g = groupItems(rows, tags);
    expect(g.map((n) => [n.key, n.items.map((r) => r.id)])).toEqual([["x", ["a"]], ["y", ["a", "b"]], [NONE_KEY, ["c"]]]);
    expect(uniqueCount(g)).toBe(3);
  });
  test("multi가 아니면 첫 값만", () => {
    const g = groupItems(rows, { ...tags, multi: false });
    expect(g.map((n) => n.key)).toEqual(["x", "y", NONE_KEY]);
    expect(g.find((n) => n.key === "x")?.items).toHaveLength(1);
  });
  test("tree: 깊이·직접 개수·중간 단계", () => {
    const g = groupItems(rows, path);
    expect(g.map((n) => [n.key, n.name, n.depth, n.count])).toEqual([["개발팀", "개발팀", 0, 1], ["개발팀/백엔드", "백엔드", 1, 1], [NONE_KEY, "", 0, 1]]);
    const only = groupItems([{ id: "z", tags: [], path: "a/b" }], path);
    expect(only.map((n) => [n.key, n.count])).toEqual([["a", 0], ["a/b", 1]]);
  });
  test("깊이 상한을 넘으면 남은 조각을 한 이름으로", () => {
    const g = groupItems([{ id: "z", tags: [], path: "a/b/c/d/e" }], path, { maxDepth: 2 });
    expect(g.map((n) => n.name)).toEqual(["a", "b", "c/d/e"]);
  });
  test("값이 공백·중복이면 정리, 전부 비면 없음", () => {
    const g = groupItems([{ id: "q", tags: [" ", "x", "x"] }, { id: "r", tags: [" "] }], tags);
    expect(g.map((n) => [n.key, n.count])).toEqual([["x", 1], [NONE_KEY, 1]]);
    expect(hasNamedGroups(groupItems([{ id: "r", tags: [] }], tags))).toBe(false);
    expect(groupItems([], tags)).toEqual([]);
  });
  test("묶음 이름은 한국어 로케일 순, 묶음 안 정렬은 compare", () => {
    const items = [{ id: "2", tags: ["나"] }, { id: "1", tags: ["가"] }, { id: "3", tags: ["나"] }];
    const g = groupItems(items, tags, { compare: (a, b) => b.id.localeCompare(a.id) });
    expect(g.map((n) => n.key)).toEqual(["가", "나"]);
    expect(g[1]!.items.map((r) => r.id)).toEqual(["3", "2"]);
  });
});

describe("접힘 도우미", () => {
  const g = groupItems(rows, path);
  test("접힌 묶음의 하위는 숨기고 자신은 남긴다", () => {
    expect(visibleGroups(g, new Set(["개발팀"])).map((n) => n.key)).toEqual(["개발팀", NONE_KEY]);
    expect(visibleGroups(g, new Set()).length).toBe(3);
  });
  test("revealGroup은 조상까지 펼친다", () => {
    const next = revealGroup(new Set(["개발팀", "개발팀/백엔드", "other"]), "개발팀/백엔드");
    expect([...next]).toEqual(["other"]);
  });
});

describe("정렬·기준 선택", () => {
  test("sortItems는 안정·비파괴", () => {
    const list = [{ s: "나", n: 1 }, { s: "가", n: 1 }, { s: "다", n: 0 }];
    const out = sortItems(list, byNumber((x) => x.n));
    expect(out.map((x) => x.s)).toEqual(["다", "나", "가"]);
    expect(list[0]!.s).toBe("나");
    expect(sortItems(list, byText((x) => x.s)).map((x) => x.s)).toEqual(["가", "나", "다"]);
  });
  test("byNumber는 없는 값을 뒤로, 내림차순 지원", () => {
    expect(sortItems([{ n: undefined }, { n: 1 }, { n: 3 }], byNumber((x: { n?: number }) => x.n, true)).map((x) => x.n)).toEqual([3, 1, undefined]);
  });
  test("resolveSort는 쓸 수 없는 정렬을 건너뛴다", () => {
    const defs: SortDef<Row>[] = [
      { id: "updated", titleKey: "u", compare: () => 0, available: (items) => items.some((r) => r.n !== undefined) },
      { id: "name", titleKey: "n", compare: byText((r) => r.id) },
    ];
    expect(availableSorts(defs, rows).map((d) => d.id)).toEqual(["name"]);
    expect(resolveSort(defs, "updated", rows)?.id).toBe("name");
    expect(resolveSort(defs, "updated", [{ id: "q", tags: [], n: 1 }])?.id).toBe("updated");
    expect(resolveSort([], "x", rows)).toBeUndefined();
  });
  test("값이 모두 다르면 기준을 쓸 수 없다", () => {
    const role: GroupByDef<Row> = { id: "role", titleKey: "r", read: (r) => [r.id], usable: usableUnlessAllDistinct((r) => [r.id], "다 다름") };
    expect(role.usable?.(rows)).toEqual({ ok: false, reason: "다 다름" });
    expect(resolveGroupBy([role, tags], "role", rows)).toBeUndefined();
    expect(resolveGroupBy([role, tags], "tags", rows)?.id).toBe("tags");
    expect(role.usable?.([rows[0]!])).toEqual({ ok: true });
  });
});

describe("폴더", () => {
  test("folderOf/withFolder는 다른 속성을 보존하고 입력을 바꾸지 않는다", () => {
    const attrs = { team_tag: "q", ui: { icon: "bot" } };
    const moved = withFolder(attrs, " 개발팀 / 백엔드 ");
    expect(moved).toEqual({ team_tag: "q", ui: { icon: "bot", folder: "개발팀/백엔드" } });
    expect(attrs).toEqual({ team_tag: "q", ui: { icon: "bot" } });
    expect(folderOf(moved)).toBe("개발팀/백엔드");
    expect(withFolder(moved, null)).toEqual(attrs);
    expect(withFolder({ ui: { folder: "a" } }, undefined)).toEqual({});
    expect(withFolder(undefined, "a")).toEqual({ ui: { folder: "a" } });
  });
  test("folderOf는 잘못된 모양에 안전", () => {
    expect(folderOf(undefined)).toBeUndefined();
    expect(folderOf({ ui: "x" })).toBeUndefined();
    expect(folderOf({ ui: { folder: 3 } })).toBeUndefined();
    expect(folderOf({ ui: { folder: "//" } })).toBeUndefined();
  });
  test("buildFolderTree·flatten", () => {
    const tree = buildFolderTree(["b/z", "a", undefined, "b/y", "a"]);
    expect(tree.map((n) => n.name)).toEqual(["a", "b"]);
    expect(flattenFolderTree(tree)).toEqual(["a", "b", "b/y", "b/z"]);
  });
});

describe("보기 상태 저장", () => {
  const mem = (): KeyValueStorage & { data: Map<string, string> } => {
    const data = new Map<string, string>();
    return { data, getItem: (k) => data.get(k) ?? null, setItem: (k, v) => void data.set(k, v) };
  };
  test("왕복", () => {
    const s = mem();
    expect(saveViewState(s, "agents", { groupBy: "folder", sort: "name" })).toBe(true);
    expect(loadViewState(s, "agents")).toEqual({ groupBy: "folder", sort: "name" });
    saveCollapsed(s, "agents", "folder", new Set(["a", "b"]));
    expect([...loadCollapsed(s, "agents", "folder")]).toEqual(["a", "b"]);
  });
  test("깨진 값·저장소 없음·쓰기 실패는 기본값", () => {
    const s = mem();
    s.data.set("ac.list.view.x", "{oops");
    s.data.set("ac.list.collapsed.x.g", "5");
    expect(loadViewState(s, "x", { sort: "name" })).toEqual({ sort: "name" });
    expect(loadCollapsed(s, "x", "g").size).toBe(0);
    expect(loadViewState(undefined, "x")).toEqual({});
    const bad: KeyValueStorage = { getItem: () => { throw new Error("no"); }, setItem: () => { throw new Error("no"); } };
    expect(loadViewState(bad, "x")).toEqual({});
    expect(saveViewState(bad, "x", {})).toBe(false);
    expect(saveCollapsed(undefined, "x", "g", new Set())).toBe(false);
  });
});
