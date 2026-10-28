import { describe, expect, it } from "vitest";
import { buildConfigUi, namedWidgetUi, withEnumArraysUnique } from "./configUi";

describe("namedWidgetUi(리소스 폼 위젯 이음)", () => {
  const schema = {
    type: "object",
    properties: {
      scopes: { type: "array", items: { $ref: "#/$defs/Row" } },
      pick: { anyOf: [{ type: "string" }, { type: "null" }], "x-ui": { widget: "w-any" } },
      plain: { type: "string" },
    },
    $defs: { Row: { type: "object", properties: { kind: { type: "string", "x-ui": { widget: "w-any" } }, other: { type: "string", "x-ui": { widget: "w-unknown" } } } } },
  };
  it("중첩(배열 항목)·널 허용 필드까지 이름이 등록된 위젯만 잇는다", () => {
    expect(namedWidgetUi(schema.properties.scopes, schema, new Set(["w-any"]))).toEqual({ items: { kind: { "ui:widget": "w-any" } } });
    expect(namedWidgetUi(schema.properties.pick, schema, new Set(["w-any"]))).toEqual({ "ui:widget": "w-any" });
    expect(namedWidgetUi(schema.properties.plain, schema, new Set(["w-any"]))).toBeUndefined();
    expect(namedWidgetUi(schema.properties.pick, schema, new Set())).toBeUndefined();
  });
});

describe("enum 배열 체크박스", () => {
  const schema = { type: "object", properties: { rows: { type: "array", items: { $ref: "#/$defs/R" } } }, $defs: { R: { type: "object", properties: { pick: { type: "array", items: { type: "string", enum: ["a", "b"] } } } } } };
  it("항목이 enum인 배열은 uniqueItems를 켠 사본과 체크박스 위젯으로 이어진다(이름을 보지 않는다)", () => {
    const next = withEnumArraysUnique(schema);
    expect(next.$defs.R.properties.pick).toMatchObject({ uniqueItems: true });
    expect(schema.$defs.R.properties.pick).not.toHaveProperty("uniqueItems");
    expect(buildConfigUi(next, undefined)).toEqual({ rows: { items: { pick: { "ui:widget": "checkboxes" } } } });
  });
});
