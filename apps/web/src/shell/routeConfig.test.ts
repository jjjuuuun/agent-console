import { describe, expect, it } from "vitest";
import { activeRoute, DEFAULT_ROUTES, DEFAULT_ROUTE_GROUPS, gotoKeyProblems, gotoShortcuts, homeRoute, redirectTarget, routeIdOfGoto, routeServing, type RouteDef } from "./routeConfig";

const custom: RouteDef[] = [
  { id: "r-one", path: "/one", titleKey: "nav.chat", icon: "x", badgeSource: null, gotoKey: "o", position: "main", redirects: ["/old"] },
  { id: "r-two", path: "/one/two", titleKey: "nav.teams", icon: "x", badgeSource: null, gotoKey: "o", position: "bottom" },
];

describe("라우트 설정 데이터", () => {
  it("기본 8개 항목, 첫 화면은 첫 main 항목", () => {
    expect(DEFAULT_ROUTES).toHaveLength(9);
    expect(homeRoute(DEFAULT_ROUTES)?.path).toBe("/chat");
  });
  it("첫 화면은 home 표시가 우선이고, 없으면 첫 main 항목", () => {
    const routes = DEFAULT_ROUTES.map((r) => ({ ...r, home: r.id === "agents" }));
    expect(homeRoute(routes)?.id).toBe("agents");
    expect(homeRoute(DEFAULT_ROUTES.map((r) => ({ ...r, home: false })))?.id).toBe("chat");
    expect(homeRoute(DEFAULT_ROUTES)?.home).toBe(true);
  });
  it("묶음은 데이터: 모든 main 항목의 group이 묶음 표에 있고, 묶음마다 항목이 있으며, 하단 항목은 묶음이 없다", () => {
    const ids = DEFAULT_ROUTE_GROUPS.map((g) => g.id);
    for (const r of DEFAULT_ROUTES.filter((r) => r.position === "main")) expect(ids).toContain(r.group);
    for (const g of DEFAULT_ROUTE_GROUPS) expect(DEFAULT_ROUTES.some((r) => r.group === g.id)).toBe(true);
    expect(DEFAULT_ROUTES.filter((r) => r.position === "bottom").every((r) => r.group === undefined)).toBe(true);
  });
  it("활성 라우트는 가장 긴 접두 일치(경계 확인)", () => {
    expect(activeRoute("/one/two/3", custom)?.id).toBe("r-two");
    expect(activeRoute("/one", custom)?.id).toBe("r-one");
    expect(activeRoute("/onex", custom)).toBeUndefined();
  });
  it("gotoKey 중복·잘못된 값을 설정 시점에 알 수 있다", () => {
    expect(gotoKeyProblems(custom).duplicates).toEqual([["r-one", "r-two"]]);
    expect(gotoKeyProblems([{ ...custom[0]!, gotoKey: "ab" }]).invalid).toEqual(["r-one"]);
  });
  it("이동 단축키는 `g 글자`이고 명령 id에서 라우트를 되찾는다", () => {
    const defs = gotoShortcuts(custom, () => {});
    expect(defs.map((d) => d.keys)).toEqual(["g o", "g o"]);
    expect(routeIdOfGoto(defs[0]!.id)).toBe("r-one");
  });
  it("역할(serves)로 라우트를 찾는다: id를 바꿔도 같은 역할이면 같은 화면이다", () => {
    const renamed = DEFAULT_ROUTES.map((r) => ({ ...r, id: `x-${r.id}` }));
    for (const r of DEFAULT_ROUTES) expect(routeServing(renamed, r.serves!)?.path).toBe(r.path);
    expect(routeServing(DEFAULT_ROUTES, "없는 역할")).toBeUndefined();
  });
  it("이전 경로는 하위 경로를 이어 새 경로로 옮긴다", () => {
    expect(redirectTarget("/old/abc", custom)).toBe("/one/abc");
    expect(redirectTarget("/graphs/g1", DEFAULT_ROUTES)).toBe("/teams/g1");
    expect(redirectTarget("/oldx", custom)).toBeUndefined();
  });
});
