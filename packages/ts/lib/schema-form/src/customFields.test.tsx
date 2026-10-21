import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SchemaForm } from "./index";
import type { SchemaFormFieldProps } from "./index";

afterEach(cleanup);

// 도메인과 무관한 임의 스키마·임의 필드 이름.
const schema = {
  type: "object",
  properties: {
    pairs: { type: "object", title: "쌍", additionalProperties: { type: "string" } },
    other: { type: "string", title: "다른 값" },
  },
};

function PairsField({ value, onChange, options, label }: SchemaFormFieldProps) {
  const entries = Object.entries((value ?? {}) as Record<string, string>);
  return (
    <div aria-label={label}>
      <span>{String(options["hint"])}</span>
      <span data-testid="count">{entries.length}</span>
      <button type="button" onClick={() => onChange({ ...(value as object), k: "v" })}>
        추가
      </button>
    </div>
  );
}

describe("customFields", () => {
  it("ui:field 이름으로 값 전체를 한 컴포넌트가 그리고 옵션·값·변경을 주고받는다", () => {
    const onChange = vi.fn();
    render(
      <SchemaForm
        schema={schema}
        uiSchema={{ pairs: { "ui:field": "pairs-field", "ui:options": { hint: "힌트" } } }}
        value={{ pairs: { a: "1" } }}
        onChange={onChange}
        customFields={{ "pairs-field": PairsField }}
      />,
    );
    expect(screen.getByText("힌트")).toBeTruthy();
    expect(screen.getByTestId("count").textContent).toBe("1");
    fireEvent.click(screen.getByRole("button", { name: "추가" }));
    expect(onChange).toHaveBeenLastCalledWith({ pairs: { a: "1", k: "v" } });
  });

  it("출처 표시 모드에서도 행에 배지가 붙고 상속된 값은 잠긴다", () => {
    render(
      <SchemaForm
        schema={schema}
        uiSchema={{ pairs: { "ui:field": "pairs-field", "ui:options": { hint: "힌트" } } }}
        value={{}}
        layers={[{ id: "L1", label: "첫째" }]}
        editLayerId="L1"
        provenance={{ "/pairs": "L0" }}
        effectiveValue={{ pairs: { a: "1" } }}
        customFields={{ "pairs-field": PairsField }}
      />,
    );
    const row = screen.getByText("힌트").closest(".ac-sf-prov-row") as HTMLElement;
    expect(row.dataset.state).toBe("inherited");
    expect((row.querySelector("fieldset.ac-sf-prov-body") as HTMLFieldSetElement).disabled).toBe(true);
  });
});
