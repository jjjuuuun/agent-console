import { describe, expect, it } from "vitest";
import { applyFormEdit } from "./formEdit";

// 도메인과 무관한 임의 스키마
const schema = {
  type: "object",
  properties: {
    a: { type: "string", default: "x" },
    n: { type: "number" },
    group: { type: "object", properties: { one: { type: "number", default: 1 }, two: { type: "string", default: "z" } }, default: {} },
    list: { type: "array", items: { type: "string" }, default: [] },
  },
};

describe("applyFormEdit", () => {
  it("바꾸지 않은 키는 생략한 채 두고 바꾼 키만 넣는다", () => {
    const shown = { a: "x", group: { one: 1, two: "z" }, list: [] };
    expect(applyFormEdit(schema, {}, { ...shown, n: 3 })).toEqual({ n: 3 });
    expect(applyFormEdit(schema, {}, { ...shown, group: { one: 1, two: "q" } })).toEqual({ group: { two: "q" } });
  });
  it("변화가 없으면 원문을 그대로 돌려준다(명시한 기본값도 유지)", () => {
    const prev = { a: "x", n: 1 };
    expect(applyFormEdit(schema, prev, { a: "x", n: 1, group: { one: 1, two: "z" }, list: [] })).toEqual(prev);
  });
  it("키를 지우면 원문에서도 빠진다", () => {
    expect(applyFormEdit(schema, { a: "y", n: 2 }, { a: "y", group: { one: 1, two: "z" }, list: [] })).toEqual({ a: "y" });
  });
  it("배열은 바뀌면 통째로 교체하고 입력은 바꾸지 않는다", () => {
    const prev = { list: ["p"] };
    expect(applyFormEdit(schema, prev, { a: "x", group: { one: 1, two: "z" }, list: ["p", "q"] })).toEqual({ list: ["p", "q"] });
    expect(prev).toEqual({ list: ["p"] });
  });
  it("unsetOnDefault: 기본값으로 되돌리면 키를 지운다", () => {
    const shown = { a: "y", group: { one: 1, two: "z" }, list: [] };
    expect(applyFormEdit(schema, { a: "y" }, { ...shown, a: "x" }, { unsetOnDefault: true })).toEqual({});
    expect(applyFormEdit(schema, { a: "y" }, { ...shown, a: "x" })).toEqual({ a: "x" });
  });
  it("원문이 없어도 동작한다", () => {
    expect(applyFormEdit(schema, undefined, { a: "w", group: { one: 1, two: "z" }, list: [] })).toEqual({ a: "w" });
  });
});
