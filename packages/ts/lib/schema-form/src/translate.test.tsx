import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SchemaForm, translateSchema, translateUiSchema } from "./index";

afterEach(cleanup);

const table: Record<string, string> = {
  이름: "Name",
  "이름을 입력합니다": "Enter a name",
  모드: "Mode",
  빠름: "Fast",
  "다음 세션부터": "From the next session",
  단위: "seconds",
};
const t = (text: string) => table[text] ?? text;

const schema = {
  type: "object",
  properties: {
    name: { type: "string", title: "이름", description: "이름을 입력합니다", default: "이름", "x-ui": { when: "다음 세션부터", unit: "단위" } },
    mode: { type: "string", title: "모드", enum: ["fast"], "x-ui": { enum_labels: { fast: "빠름" } } },
    title: { type: "string", title: "모드" },
    pick: { oneOf: [{ const: "a", title: "빠름" }] },
  },
};

describe("translateSchema", () => {
  it("제목·설명·x-ui 문구·가지 이름만 바꾸고 기본값·enum·속성 이름은 그대로 둔다", () => {
    const out = translateSchema(schema, t) as typeof schema;
    expect(out.properties.name.title).toBe("Name");
    expect(out.properties.name.description).toBe("Enter a name");
    expect(out.properties.name.default).toBe("이름");
    expect(out.properties.name["x-ui"]).toEqual({ when: "From the next session", unit: "seconds" });
    expect(out.properties.mode["x-ui"]).toEqual({ enum_labels: { fast: "Fast" } });
    expect(out.properties.mode.enum).toEqual(["fast"]);
    expect(Object.keys(out.properties)).toEqual(["name", "mode", "title", "pick"]);
    expect(out.properties.title.title).toBe("Mode");
    expect(out.properties.pick.oneOf[0]?.title).toBe("Fast");
  });
  it("원본을 바꾸지 않는다", () => {
    translateSchema(schema, t);
    expect(schema.properties.name.title).toBe("이름");
  });
  it("uiSchema의 ui:title·ui:description·ui:placeholder·ui:help를 바꾼다", () => {
    const out = translateUiSchema({ name: { "ui:title": "이름", "ui:options": { rows: 3 }, "ui:placeholder": "모드" } }, t);
    expect(out).toEqual({ name: { "ui:title": "Name", "ui:options": { rows: 3 }, "ui:placeholder": "Mode" } });
  });
});

describe("SchemaForm translate", () => {
  it("translate가 없으면 문구 그대로, 있으면 라벨과 설명이 바뀐다", () => {
    const { rerender } = render(<SchemaForm schema={schema} value={{}} onChange={() => undefined} xui={false} />);
    expect(screen.getAllByText("이름").length).toBeGreaterThan(0);
    rerender(<SchemaForm schema={schema} value={{}} onChange={() => undefined} xui={false} translate={t} />);
    expect(screen.getAllByText("Name").length).toBeGreaterThan(0);
    expect(screen.queryAllByText("이름")).toEqual([]);
  });
});
