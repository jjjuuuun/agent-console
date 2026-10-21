import { describe, expect, it } from "vitest";

import { applyOverlay, mergeJson, renderString, renderTree } from "./template.mjs";

describe("renderString", () => {
  it("중첩 키를 바꾼다", () => {
    expect(renderString("{{a}}-{{ b.c }}", { a: 1, b: { c: "x" } })).toBe("1-x");
  });
  it("없는 키는 오류", () => {
    expect(() => renderString("{{zz}}", {})).toThrow("zz");
  });
});

describe("renderTree", () => {
  it(".tmpl를 떼고 내용을 렌더링한다", () => {
    expect(renderTree({ "a/package.json.tmpl": '{"n":"{{n}}"}', "b.txt": "plain" }, { n: "x" })).toEqual({ "a/package.json": '{"n":"x"}', "b.txt": "plain" });
  });
});

describe("mergeJson / applyOverlay", () => {
  it("객체는 깊게 합치고 배열은 바꾸고 null은 지운다", () => {
    expect(mergeJson({ a: { b: 1, c: 2 }, l: [1], d: 1 }, { a: { c: 3 }, l: [2], d: null })).toEqual({ a: { b: 1, c: 3 }, l: [2] });
  });
  it("package.patch.json은 package.json에 합쳐지고 파일로 남지 않는다", () => {
    const out = applyOverlay({ "package.json": '{"name":"x","files":["a"]}', "k.txt": "1" }, { "package.patch.json": '{"files":["b"]}', "k.txt": "2" });
    expect(JSON.parse(out["package.json"])).toEqual({ name: "x", files: ["b"] });
    expect(out["k.txt"]).toBe("2");
    expect(out).not.toHaveProperty("package.patch.json");
  });
});
