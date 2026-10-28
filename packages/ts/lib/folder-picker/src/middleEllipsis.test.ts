import { describe, expect, it } from "vitest";

import { cells, cellsForWidth, middleEllipsis } from "./middleEllipsis";
import { collapseCrumbs, splitPath } from "./pathSegments";

describe("cells", () => {
  it("ASCII 1칸, 한글·전각·이모지 2칸, 결합 문자 0칸", () => {
    expect(cells("abc")).toBe(3);
    expect(cells("한글")).toBe(4);
    expect(cells("ＡＢ")).toBe(4);
    expect(cells("😀")).toBe(2);
    expect(cells("e\u0301")).toBe(1);
  });
  it("NFC 정규화 뒤 센다(분해된 한글도 같은 칸 수)", () => {
    expect(cells("한".normalize("NFD"))).toBe(2);
  });
});

describe("cellsForWidth", () => {
  it("1칸 7.5px, floor(폭/7.5)-1", () => {
    expect(cellsForWidth(180)).toBe(23);
    expect(cellsForWidth(280)).toBe(36);
    expect(cellsForWidth(0)).toBe(0);
  });
});

describe("middleEllipsis", () => {
  it("들어가면 그대로", () => {
    expect(middleEllipsis("/a/b", 10)).toBe("/a/b");
  });
  it("명세 검증 예(27칸)", () => {
    const out = middleEllipsis("/home/me/work/payments/services/api", 27);
    expect(out).toBe("/home/me/work…/services/api");
    expect(cells(out)).toBe(27);
  });
  it("마지막 폴더 이름은 항상 남는다", () => {
    expect(middleEllipsis("/home/me/work/payments/services/api", 12).endsWith("api")).toBe(true);
  });
  it("마지막 조각이 예산을 넘으면 조각의 끝쪽을 꼬리로 쓴다", () => {
    const out = middleEllipsis("/a/" + "x".repeat(60), 20);
    expect(out.startsWith("/a")).toBe(true);
    expect(out).toContain("…");
    expect(cells(out)).toBeLessThanOrEqual(20);
  });
  it("한글 경로는 2칸으로 세어 넘치지 않는다", () => {
    const p = "/홈/사용자/작업/결제서비스/서비스/에이피아이";
    for (const n of [10, 16, 24, 30]) expect(cells(middleEllipsis(p, n))).toBeLessThanOrEqual(n);
  });
  it("윈도 경로는 \\ 구분자를 따른다", () => {
    const out = middleEllipsis("C:\\Users\\me\\work\\payments\\services\\api", 24);
    expect(out).toContain("…");
    expect(out.endsWith("\\services\\api") || out.endsWith("\\api")).toBe(true);
    expect(cells(out)).toBeLessThanOrEqual(24);
  });
  it("서로게이트 쌍·결합 문자 중간에서 자르지 않는다", () => {
    const p = "/a/" + "😀".repeat(20);
    const out = middleEllipsis(p, 15);
    expect(out).not.toMatch(/[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/);
    expect(cells(out)).toBeLessThanOrEqual(15);
  });
  it("아주 작은 예산", () => {
    expect(middleEllipsis("/abc/def", 1)).toBe("…");
    expect(middleEllipsis("/abc/def", 0)).toBe("");
  });
  it("끝 구분자가 있어도 폴더 이름이 남는다", () => {
    expect(middleEllipsis("/home/me/work/payments/", 14)).toContain("payments/");
  });
  it("어떤 입력도 예산을 넘지 않는다", () => {
    const p = "/home/me/projects/에이전트-도구/packages/ts/lib/folder-picker/src";
    for (let n = 2; n < cells(p); n += 1) expect(cells(middleEllipsis(p, n))).toBeLessThanOrEqual(n);
  });
});

describe("splitPath / collapseCrumbs", () => {
  it("posix·windows 조각", () => {
    expect(splitPath("/home/me")).toEqual([{ label: "/", path: "/" }, { label: "home", path: "/home" }, { label: "me", path: "/home/me" }]);
    expect(splitPath("C:\\Users\\me")).toEqual([{ label: "C:", path: "C:\\" }, { label: "Users", path: "C:\\Users" }, { label: "me", path: "C:\\Users\\me" }]);
  });
  it("넘치면 가운데를 접고 처음 1개·마지막 2개를 남긴다", () => {
    const items = ["a", "b", "c", "d", "e", "f"].map((label) => ({ label }));
    const r = collapseCrumbs(items, 5, (l) => l.length);
    expect(r.head.map((i) => i.label)).toEqual(["a"]);
    expect(r.tail.map((i) => i.label)).toEqual(["e", "f"]);
    expect(r.hidden.map((i) => i.label)).toEqual(["b", "c", "d"]);
    expect(collapseCrumbs(items, 100, (l) => l.length).hidden).toEqual([]);
  });
});
