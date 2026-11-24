import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SchemaForm } from "./index";
import type { JsonSchema } from "./index";
import { titleUntitledBranches } from "./branchTitles";
import { DEFAULT_MESSAGES } from "./messages";

afterEach(cleanup);

// 도메인과 무관한 임의 스키마: 목록 항목은 `$ref` 클래스 이름(`ThingSpec`)을 제목으로 가진다.
const schema: JsonSchema = {
  type: "object",
  properties: {
    things: {
      type: "array",
      title: "물건들",
      items: { $ref: "#/$defs/ThingSpec" },
      "x-ui": { itemTitle: "/label /id" },
    },
    plain: { type: "array", title: "그냥 목록", items: { $ref: "#/$defs/ThingSpec" } },
  },
  $defs: {
    ThingSpec: {
      type: "object",
      title: "ThingSpec",
      required: ["id"],
      properties: {
        id: { type: "string", title: "이름표" },
        label: { type: "string", title: "표시 이름" },
        mark: { anyOf: [{ type: "string" }, { type: "array", items: { type: "string" } }], title: "표시 글자" },
      },
    },
  },
};

const value = { things: [{ id: "a1", label: "첫째" }, { id: "b2" }, { label: "" }], plain: [{ id: "z" }] };

describe("목록 항목 카드 제목", () => {
  it("itemTitle 값(공백으로 이은 차례), 없으면 목록 제목 + 순번을 쓰고 스키마 클래스 이름·필수 별표는 보이지 않는다", () => {
    const { container } = render(<SchemaForm schema={schema} value={value} onChange={() => {}} />);
    const legends = [...container.querySelectorAll("legend")].map((l) => l.textContent ?? "");
    expect(legends.some((t) => t.includes("ThingSpec"))).toBe(false);
    expect(legends).toContain("첫째");
    expect(legends).toContain("b2");
    expect(legends).toContain("물건들 3");
    expect(legends).toContain("그냥 목록 1");
    expect(container.querySelector("legend .required")).toBeNull();
  });
});

describe("제목 없는 선택지 이름", () => {
  it("anyOf 가지에 값 종류 이름을 달고 `option N`을 보이지 않는다", () => {
    render(<SchemaForm schema={schema} value={value} onChange={() => {}} />);
    const options = screen.getAllByRole("option").map((o) => o.textContent ?? "");
    expect(options.length).toBeGreaterThan(0);
    expect(options.every((t) => !/option \d/i.test(t))).toBe(true);
    expect(options).toEqual(expect.arrayContaining(["글자", "목록"]));
  });

  it("스키마의 title·$ref 가지는 그대로 두고, 같은 종류가 둘이면 순번을 붙인다", () => {
    const out = titleUntitledBranches(
      { anyOf: [{ type: "string", title: "내 이름" }, { type: "string" }, { type: "string" }, { $ref: "#/x" }, { type: "null" }] },
      DEFAULT_MESSAGES,
    ) as { anyOf: { title?: string }[] };
    expect(out.anyOf.map((b) => b.title)).toEqual(["내 이름", "글자 1", "글자 2", undefined, undefined]);
  });
});
