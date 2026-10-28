import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { MEMORY_ENTRY_SORTS } from "@agent-console/contracts/constants";
import { EMPTY_VIEW, hasFilters, parseScopeParam, parseView, scopeParam, sortParams, writeView } from "./memoryUrl";

describe("주소 상태", () => {
  it("범위는 <종류>:<id>이고 id가 비어도(콜론 뒤가 빔) 콜론이 id 안에 있어도 된다", () => {
    expect(parseScopeParam("k:")).toEqual({ kind: "k", id: "" });
    expect(parseScopeParam("k:a:b/c")).toEqual({ kind: "k", id: "a:b/c" });
    expect(parseScopeParam("k")).toBeNull();
    expect(parseScopeParam(":x")).toBeNull();
    expect(parseScopeParam(null)).toBeNull();
    expect(scopeParam({ kind: "k", id: "" })).toBe("k:");
    expect(scopeParam({ kind: "k" })).toBe("k:");
  });

  it("읽고 쓰면 같고, 기본값은 주소에 쓰지 않으며, 모르는 인자(prj 등)는 보존한다", () => {
    const params = new URLSearchParams("prj=a&scope=k%3Ax&entry=e1&q=가나&tag=t&author_run=r&author_kind=u&archived=1&deleted=1&sort=key&order=asc");
    const view = parseView(params);
    expect(view).toEqual({ scope: { kind: "k", id: "x" }, entry: "e1", q: "가나", tag: "t", authorRun: "r", authorKind: "u", includeArchived: true, includeDeleted: true, sort: { key: "key", order: "asc" } });
    expect(writeView(new URLSearchParams("prj=a"), view).toString().split("&").sort()).toEqual(params.toString().split("&").sort());
    const cleared = writeView(params, { ...EMPTY_VIEW });
    expect(cleared.toString()).toBe("prj=a");
  });

  it("모르는 정렬 값은 무시하고(서버가 422로 거절한다) 방향 기본은 desc", () => {
    expect(parseView(new URLSearchParams("sort=nonsense")).sort).toBeNull();
    for (const key of MEMORY_ENTRY_SORTS) expect(parseView(new URLSearchParams(`sort=${key}`)).sort).toEqual({ key, order: "desc" });
    expect(sortParams(null)).toEqual({});
    expect(sortParams({ key: "bytes", order: "asc" })).toEqual({ sort: "bytes", order: "asc" });
  });

  it("필터 판정: 범위·선택 항목·정렬은 필터가 아니다", () => {
    expect(hasFilters(parseView(new URLSearchParams("scope=k%3A&entry=e&sort=key")))).toBe(false);
    for (const q of ["q=x", "tag=t", "author_run=r", "author_kind=a", "archived=1", "deleted=1"]) expect(hasFilters(parseView(new URLSearchParams(q)))).toBe(true);
  });
});

describe("하드코딩 점검: 범위 종류·도구 이름이 메모리 화면 코드에 없다", () => {
  const files = readdirSync(__dirname).filter((f) => /\.(ts|tsx|css|json)$/.test(f) && !/\.test\./.test(f));
  // 패키지 기본 범위 종류 이름과 에이전트 도구 이름(예시일 뿐 사용자가 바꿀 수 있는 데이터)
  const forbidden = ["shared", "project", "team", "memory_read", "memory_write", "memory_search", "memory_delete"];
  it("검사 대상이 있다", () => expect(files.length).toBeGreaterThan(15));
  it.each(files)("%s", (f) => {
    const text = readFileSync(join(__dirname, f), "utf8");
    const hits = forbidden.filter((name) => new RegExp(`(["'\`])${name}\\1`).test(text));
    expect(hits).toEqual([]);
  });
});
