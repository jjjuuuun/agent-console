import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ArchitectureView } from "@agent-console/contracts/architecture";
import type { LogWidget } from "@agent-console/contracts/logs";
import { ArchitectureDiagram } from "@agent-console/arch-view";
import { sampleCell } from "@agent-console/arch-view/testing";
import { builtinWidgets, createWidgetRegistry, DashboardGrid } from "@agent-console/log-view";
import { SchemaForm } from "@agent-console/schema-form";
import { cellRenderers, configWidgets, gaugeWidget, toTags } from "./index";

afterEach(cleanup);

async function violations(el: HTMLElement): Promise<string[]> {
  const r = await axe.run(el, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
  return r.violations.map((v) => v.id);
}

const widget = (id: string, kind: string, options: Record<string, unknown> = {}): LogWidget => ({ id, kind, query: { metric: "m", group_by: [] }, options });

describe("X21 대시보드 위젯", () => {
  const registry = createWidgetRegistry(builtinWidgets, [gaugeWidget]);
  const draw = (w: LogWidget, value: number | null) =>
    render(<DashboardGrid widgets={[w]} registry={registry} results={{ [w.id]: { loading: false, rows: [{ keys: {}, value }] } }} slotFor={() => 0} />);

  it("레지스트리에 한 줄 더하면 격자가 그리고 옵션 max를 쓴다", () => {
    const { container } = draw(widget("g", "example.gauge", { max: 50 }), 20);
    const meter = container.querySelector("meter")!;
    expect(meter.getAttribute("max")).toBe("50");
    expect(meter.getAttribute("value")).toBe("20");
    expect(screen.getByTestId("gauge-value").textContent).toBe("20");
  });
  it("값이 null이면 0이 아니라 –, 모르는 max 옵션은 기본 100", () => {
    draw(widget("g", "example.gauge"), null);
    expect(screen.getByTestId("gauge-empty").textContent).toBe("–");
    cleanup();
    const { container } = draw(widget("g", "example.gauge", { max: "많이" }), 5);
    expect(container.querySelector("meter")!.getAttribute("max")).toBe("100");
  });
  it("등록하지 않으면 알 수 없는 위젯 자리 표시", () => {
    render(<DashboardGrid widgets={[widget("g", "example.gauge")]} registry={createWidgetRegistry(builtinWidgets)} results={{}} slotFor={() => 0} />);
    expect(screen.getByText(/알 수 없는 위젯/)).toBeTruthy();
  });
  it("axe 0건", async () => {
    const { container } = draw(widget("g", "example.gauge"), 30);
    expect(await violations(container)).toEqual([]);
  });
});

describe("X24 구조도 칸 그리기", () => {
  const view = (count: number | null): ArchitectureView => ({
    profile: "p",
    canvas: { width: 600, height: 300 },
    cells: [
      sampleCell("a", { label: "첫째", x: 100, y: 100, view: "example-badge", metrics: { count: { status: count == null ? "not_collected" : "observed", value: count } } }),
      sampleCell("b", { label: "둘째", x: 400, y: 100, view: "view-nobody-knows" }),
    ],
    edges: [],
    event_total: 0,
  });
  const draw = (count: number | null) => render(<ArchitectureDiagram view={view(count)} containerSize={{ width: 1000, height: 600 }} cellRenderers={cellRenderers} />);

  it("view 키가 맞는 칸만 배지를 더하고 기본 본문은 남긴다", () => {
    const { container } = draw(7);
    const a = container.querySelector<HTMLElement>('button.ac-arch-cell[data-cell-id="a"]')!;
    expect(a.textContent).toContain("첫째");
    expect(a.querySelector('[data-testid="badge-cell"]')!.textContent).toBe("7회");
    expect(container.querySelector('button.ac-arch-cell[data-cell-id="b"] [data-testid="badge-cell"]')).toBeNull();
  });
  it("수집 안 됨(null)이면 배지 없음 - 0회로 보이지 않는다", () => {
    const { container } = draw(null);
    expect(container.querySelector('[data-testid="badge-cell"]')).toBeNull();
    expect(container.textContent).not.toContain("0회");
  });
  it("axe 0건", async () => {
    const { container } = draw(3);
    expect(await violations(container)).toEqual([]);
  });
});

describe("X51 설정 폼 위젯", () => {
  const schema = { type: "object", properties: { tags: { type: "array", items: { type: "string" }, title: "태그" } } };
  const draw = (formData: unknown, onChange = vi.fn()) => {
    const customFields = Object.fromEntries(Object.entries(configWidgets).map(([name, w]) => [name, w.Component]));
    return render(<SchemaForm schema={schema} uiSchema={{ tags: { "ui:field": "example.tags" } }} value={formData} onChange={onChange} customFields={customFields} />);
  };

  it("ui:widget 이름으로 입력 칸을 그리고 쉼표로 나눠 배열로 바꾼다", () => {
    const onChange = vi.fn();
    draw({ tags: ["a", "b"] }, onChange);
    const input = screen.getByLabelText("태그") as HTMLInputElement;
    expect(input.value).toBe("a, b");
    fireEvent.change(input, { target: { value: "x, y ,, z" } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ tags: ["x", "y", "z"] }));
  });
  it("모르는 모양의 값은 빈 칸으로 보고 지우지 않는다", () => {
    expect(toTags("문자열")).toEqual([]);
    expect(toTags([1, "a", null])).toEqual(["a"]);
    const onChange = vi.fn();
    draw({ tags: "문자열" }, onChange);
    expect((screen.getByLabelText("태그") as HTMLInputElement).value).toBe("");
    expect(onChange).not.toHaveBeenCalled();
  });
  it("axe 0건", async () => {
    const { container } = draw({ tags: ["a"] });
    expect(await violations(container)).toEqual([]);
  });
});
