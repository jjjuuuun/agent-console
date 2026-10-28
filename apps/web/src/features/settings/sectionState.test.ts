import { describe, expect, it } from "vitest";
import { countSectionChanges, groupSections, sectionIdFromHash } from "./sectionState";

describe("sectionState", () => {
  it("객체 키는 한 단계 아래 항목마다 변경 1개로 센다", () => {
    const base = { a: { x: 1, y: 2 }, ui: { k: { p: 1 } } };
    expect(countSectionChanges(["a"], base, base)).toBe(0);
    expect(countSectionChanges(["a"], base, { ...base, a: { x: 9, y: 8 } })).toBe(2);
    expect(countSectionChanges(["a"], base, { ...base, a: { x: 1 } })).toBe(1);
    expect(countSectionChanges(["ui/k"], base, { ...base, ui: { k: { p: 2 } } })).toBe(1);
    expect(countSectionChanges(["b"], base, { ...base, b: 3 })).toBe(1);
    expect(countSectionChanges([], base, { a: 1 })).toBe(0);
  });

  it("해시에서 섹션 id만 뽑는다(뒤 조각 무시)", () => {
    expect(sectionIdFromHash("#logs?source=x")).toBe("logs");
    expect(sectionIdFromHash("#logs/taxonomy")).toBe("log-taxonomy");
    expect(sectionIdFromHash("#log-taxonomy")).toBe("log-taxonomy");
    expect(sectionIdFromHash("")).toBe("");
  });

  it("묶음은 첫 등장 순서를 지킨다", () => {
    const g = groupSections([{ group: "b", n: 1 }, { group: "a", n: 2 }, { group: "b", n: 3 }]);
    expect(g.map((x) => x.group)).toEqual(["b", "a"]);
    expect(g[0]?.items.map((i) => i.n)).toEqual([1, 3]);
  });
});
