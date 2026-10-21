import { describe, expect, test } from "vitest";

import {
  applyLogFilter,
  badgeLabel,
  defaultScopeFor,
  filterByScope,
  groupByScope,
  isVisible,
  logFilterFor,
  normalizeScope,
  scopeBadge,
  withScope,
} from "@agent-console/projects";

describe("isVisible / filterByScope", () => {
  const items = [
    { id: "s", project: null },
    { id: "u" },
    { id: "a", project: "app" },
    { id: "o", project: "other" },
    { id: "gone", project: "deleted" },
  ];
  const ids = (xs: { id: string }[]) => xs.map((x) => x.id);

  test("모든 프로젝트(null)는 거르지 않는다", () => {
    expect(ids(filterByScope(items, null))).toEqual(["s", "u", "a", "o", "gone"]);
  });
  test("기본 = 공용 + 이 프로젝트", () => {
    expect(ids(filterByScope(items, "app"))).toEqual(["s", "u", "a"]);
  });
  test("이 프로젝트만 / 공용만", () => {
    expect(ids(filterByScope(items, "app", { mode: "project_only" }))).toEqual(["a"]);
    expect(ids(filterByScope(items, "app", { mode: "shared_only" }))).toEqual(["s", "u"]);
  });
  test("목록에 없는 프로젝트를 가리키는 항목은 공용으로 본다", () => {
    const known = ["app", "other"];
    expect(ids(filterByScope(items, "app", { knownProjects: known }))).toEqual(["s", "u", "a", "gone"]);
    expect(isVisible("deleted", "app", { knownProjects: known, mode: "shared_only" })).toBe(true);
  });
  test("빈 문자열·공백은 공용", () => {
    expect(normalizeScope("  ")).toBeNull();
    expect(isVisible("", "app")).toBe(true);
  });
  test("scopeOf로 다른 필드를 쓴다(대화·실행의 project_id)", () => {
    const convs = [{ id: "1", project_id: "app" }, { id: "2", project_id: null }];
    expect(filterByScope(convs, "app", { mode: "project_only", scopeOf: (c) => c.project_id }).map((c) => c.id)).toEqual(["1"]);
  });
  test("입력 배열을 바꾸지 않는다", () => {
    const copy = [...items];
    filterByScope(items, "app");
    expect(items).toEqual(copy);
  });
});

describe("groupByScope", () => {
  test("이 프로젝트 / 공용 / 다른 프로젝트 순, 빈 그룹 생략", () => {
    const items = [{ id: "o", project: "x" }, { id: "s" }, { id: "a", project: "app" }];
    const groups = groupByScope(items, "app");
    expect(groups.map((g) => [g.group, g.items.map((i) => i.id)])).toEqual([
      ["current", ["a"]],
      ["shared", ["s"]],
      ["other", ["o"]],
    ]);
    expect(groupByScope([{ id: "s" }], "app").map((g) => g.group)).toEqual(["shared"]);
  });
});

describe("defaultScopeFor", () => {
  test("모든 프로젝트 보기에서는 공용", () => {
    expect(defaultScopeFor("resource", null)).toBeNull();
  });
  test("설정이 없으면 프로젝트 전용", () => {
    expect(defaultScopeFor("agent", "app")).toBe("app");
    expect(defaultScopeFor("agent", "app", null)).toBe("app");
  });
  test("종류별 설정과 fallback은 데이터에서 읽는다(종류 이름 고정 없음)", () => {
    const prefs = { new_definition_scope: { zzz: "shared" as const }, fallback: "project" as const };
    expect(defaultScopeFor("zzz", "app", prefs)).toBeNull();
    expect(defaultScopeFor("agent", "app", prefs)).toBe("app");
    expect(defaultScopeFor("agent", "app", { fallback: "shared" })).toBeNull();
  });
  test("withScope는 공용이면 필드를 넣지 않는다", () => {
    expect(withScope({ id: "x" }, null)).toEqual({ id: "x" });
    expect("project" in withScope({ id: "x", project: "old" }, null)).toBe(false);
    expect(withScope({ id: "x" }, "app")).toEqual({ id: "x", project: "app" });
  });
});

describe("scopeBadge", () => {
  const names = new Map([["app", "앱 개편"], ["other", "다른 앱"]]);
  test("모든 프로젝트 보기: 공용·프로젝트 이름 태그", () => {
    expect(scopeBadge(null, null, { projectNames: names })?.kind).toBe("shared");
    const b = scopeBadge("app", null, { projectNames: names });
    expect(b).toMatchObject({ kind: "project", key: "scope.project", params: { project: "앱 개편" } });
    expect(b && badgeLabel(b)).toBe("앱 개편");
  });
  test("특정 프로젝트 보기: 자기 태그는 숨기고, 공용은 보이고, 다른 프로젝트는 경고", () => {
    expect(scopeBadge("app", "app", { projectNames: names })).toBeNull();
    expect(scopeBadge("app", "app", { projectNames: names, showOwn: true })?.kind).toBe("project");
    expect(scopeBadge(null, "app")?.kind).toBe("shared");
    expect(scopeBadge(null, "app", { showShared: false })).toBeNull();
    const o = scopeBadge("other", "app", { projectNames: names });
    expect(o).toMatchObject({ kind: "other_project", tone: "warning" });
    expect(o && badgeLabel(o)).toBe("다른 프로젝트: 다른 앱");
  });
  test("목록에 없는 id는 삭제된 프로젝트", () => {
    const b = scopeBadge("gone", null, { projectNames: names });
    expect(b).toMatchObject({ kind: "deleted_project", params: { project: "gone" } });
    expect(b && badgeLabel(b)).toBe("삭제된 프로젝트: gone");
  });
  test("이름 표를 안 주면 id를 이름으로 쓴다, 메시지 표 교체 가능", () => {
    const b = scopeBadge("app", null);
    expect(b?.params.project).toBe("app");
    expect(b && badgeLabel(b, { "scope.project": "[${project}]" })).toBe("[app]");
    expect(scopeBadge("toString", null, { projectNames: { app: "x" } })?.kind).toBe("deleted_project");
  });
});

describe("logFilterFor", () => {
  test("연결된 묶음을 쉼표 목록으로", () => {
    expect(logFilterFor({ log_projects: ["a", " b ", "a", ""] })).toEqual({ filter: { project: "a,b" }, groups: ["a", "b"], linked: true });
  });
  test("연결 없음 = 거르지 않음 + 안내", () => {
    expect(logFilterFor({ log_projects: [] })).toEqual({ filter: undefined, groups: [], linked: false });
    expect(logFilterFor({})).toMatchObject({ linked: false });
  });
  test("모든 프로젝트 = 거르지 않음, 안내 없음", () => {
    expect(logFilterFor(null)).toEqual({ filter: undefined, groups: [], linked: true });
  });
  test("applyLogFilter는 project 키를 대체하고 나머지를 보존", () => {
    expect(applyLogFilter({ project: "x", model: "m" }, { log_projects: ["p"] })).toEqual({ project: "p", model: "m" });
    const base = { model: "m" };
    expect(applyLogFilter(base, null)).toBe(base);
  });
});
