import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SchemaForm } from "./index";
import type { JsonSchema } from "./index";

afterEach(cleanup);

const schema: JsonSchema = {
  type: "object",
  properties: {
    name: { type: "string", title: "이름", default: "기본" },
    count: { type: "number", title: "개수", default: 3 },
    box: {
      type: "object",
      title: "상자",
      default: {},
      properties: { w: { type: "string", title: "너비", default: "1" }, h: { type: "string", title: "높이" } },
    },
  },
};
const layers = [
  { id: "x", label: "엑스" },
  { id: "y", label: "와이" },
];
const row = (label: string) => screen.getAllByText(label)[0]!.closest(".ac-sf-prov-row") as HTMLElement;

describe("QA: 이 층 값 격리", () => {
  it("스키마 default와 상속 값이 편집 후 onChange에 새지 않는다", () => {
    const onChange = vi.fn();
    render(
      <SchemaForm
        schema={schema}
        layers={layers}
        editLayerId="y"
        provenance={{ "/name": "x", "/box/h": "y" }}
        effectiveValue={{ name: "상속", box: { h: "H" } }}
        value={{ box: { h: "H" } }}
        onChange={onChange}
      />,
    );
    fireEvent.change(within(row("높이")).getByRole("textbox"), { target: { value: "H2" } });
    expect(onChange).toHaveBeenLastCalledWith({ box: { h: "H2" } });
  });

  it("층 값이 비어 있고 provenance가 {}여도 기본값이 채워지지 않는다(모두 읽기 전용)", () => {
    const onChange = vi.fn();
    render(<SchemaForm schema={schema} layers={layers} editLayerId="y" provenance={{}} value={{}} onChange={onChange} />);
    expect(onChange).not.toHaveBeenCalled();
    for (const l of ["이름", "개수"]) {
      expect((row(l).querySelector("input") as HTMLInputElement).closest("fieldset")!.disabled).toBe(true);
    }
  });
});
