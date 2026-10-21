import { describe, expect, it } from "vitest";
import { checkKeybinding, comboFromEvent, detectPlatform } from "./keybindings";
import { formatPointer, getAt, jsonEqual, parsePointer, setAt, unsetAt } from "./jsonPointer";
import { inheritAt, overrideAt } from "./layerEdit";
import { enumValues, isNullableNumber, keywordAt, parseEnumDescriptions, pickProperties, schemaPointers } from "./schemaTools";

// 도메인과 무관한 임의 스키마.
const root = {
  type: "object",
  properties: {
    mode: { $ref: "#/$defs/Mode", description: "alpha: 첫째 설명, beta: 둘째 설명." },
    depth: { anyOf: [{ type: "integer", minimum: 1 }, { type: "null" }] },
    box: { type: "object", properties: { w: { type: "string" } }, "x-merge": "union" },
  },
  $defs: { Mode: { type: "string", enum: ["alpha", "beta"] } },
};

describe("jsonPointer", () => {
  it("파싱·형식화·읽기·쓰기·지우기(빈 부모 정리)", () => {
    expect(parsePointer("/a/b~1c")).toEqual(["a", "b/c"]);
    expect(formatPointer(["a", "b/c"])).toBe("/a/b~1c");
    const v = setAt({}, "/x/y", 1) as Record<string, unknown>;
    expect(getAt(v, "/x/y")).toBe(1);
    expect(unsetAt(v, "/x/y")).toEqual({});
    expect(unsetAt({ x: { y: 1, z: 2 } }, "/x/y")).toEqual({ x: { z: 2 } });
    expect(jsonEqual({ a: [1, { b: 2 }] }, { a: [1, { b: 2 }] })).toBe(true);
    expect(jsonEqual({ a: 1 }, { a: 2 })).toBe(false);
  });
  it("층 편집: 덮어쓰기는 유효 값을 복사하고 되돌리기는 키를 지운다", () => {
    const layer = overrideAt({}, { box: { w: "10" } }, "/box/w");
    expect(layer).toEqual({ box: { w: "10" } });
    expect(overrideAt({}, {}, "/none")).toEqual({ none: null });
    expect(inheritAt(layer, "/box/w")).toEqual({});
  });
});

describe("schemaTools", () => {
  it("enum·널 허용 숫자·값별 설명·확장 키워드·경로 목록", () => {
    expect(enumValues(root.properties.mode, root)).toEqual(["alpha", "beta"]);
    expect(isNullableNumber(root.properties.depth, root)).toBe(true);
    expect(isNullableNumber(root.properties.box, root)).toBe(false);
    expect(parseEnumDescriptions("alpha: 첫째 설명, beta: 둘째 설명.", ["alpha", "beta"])).toEqual({ alpha: "첫째 설명", beta: "둘째 설명" });
    expect(parseEnumDescriptions(undefined, ["alpha"])).toEqual({});
    expect(keywordAt(root, "/box", "x-merge")).toBe("union");
    expect(schemaPointers(root)).toEqual(["/mode", "/depth", "/box", "/box/w"]);
    expect(Object.keys((pickProperties(root, ["mode", "zzz"]).properties as object))).toEqual(["mode"]);
  });
});

describe("keybindings", () => {
  it("이벤트를 Mod 기반 조합으로 바꾼다(수식키만이면 undefined, 기호 키는 Shift 생략)", () => {
    const ev = { ctrlKey: false, metaKey: false, altKey: false, shiftKey: false };
    expect(comboFromEvent({ ...ev, key: "k", ctrlKey: true }, "other")).toBe("Mod+K");
    expect(comboFromEvent({ ...ev, key: "k", metaKey: true }, "mac")).toBe("Mod+K");
    expect(comboFromEvent({ ...ev, key: "B", ctrlKey: true, shiftKey: true }, "other")).toBe("Mod+Shift+B");
    expect(comboFromEvent({ ...ev, key: "?", shiftKey: true }, "other")).toBe("?");
    expect(comboFromEvent({ ...ev, key: "Shift", shiftKey: true }, "other")).toBeUndefined();
    expect(detectPlatform("MacIntel")).toBe("mac");
    expect(detectPlatform("Win32")).toBe("other");
  });
  it("충돌·예약 키·수식키 필요를 경고하되 막지 않는다", () => {
    expect(checkKeybinding({ keys: "Mod+T" }, "other")).toEqual(["reserved"]);
    expect(checkKeybinding({ keys: "g", modifierRequired: true }, "other")).toEqual(["modifier_required"]);
    expect(checkKeybinding({ keys: "Mod+K", conflict: "x" }, "other")).toEqual(["conflict"]);
    expect(checkKeybinding({ keys: "a b c" }, "other")).toEqual(["invalid"]);
    expect(checkKeybinding({ keys: "" }, "other")).toEqual([]);
  });
});
