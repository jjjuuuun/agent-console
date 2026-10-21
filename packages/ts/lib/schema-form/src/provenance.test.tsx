import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SchemaForm } from "./index";
import { extractLayerValue } from "./provenance";
import type { JsonSchema, SchemaFormProps } from "./index";

afterEach(cleanup);

// 도메인과 무관한 임의 스키마·임의 층 id.
const schema: JsonSchema = {
  type: "object",
  properties: {
    name: { type: "string", title: "이름", default: "기본", "x-ui": { tier: "basic" } },
    kind: { type: "string", title: "종류", enum: ["a", "b"] },
    tags: { type: "array", title: "태그", items: { type: "string" } },
    box: {
      type: "object",
      title: "상자",
      properties: { width: { type: "string", title: "너비" }, height: { type: "string", title: "높이" } },
    },
    extra: { type: "string", title: "추가" },
  },
};
const layers = [
  { id: "L1", label: "첫째" },
  { id: "L2", label: "둘째" },
  { id: "L3", label: "셋째" },
];
const base: Partial<SchemaFormProps> = {
  layers,
  editLayerId: "L3",
  provenance: { "/name": "L3", "/kind": "L1", "/tags": "L2", "/box/width": "L1", "/box/height": "L3" },
  effectiveValue: { name: "내 이름", kind: "a", tags: ["x"], box: { width: "10", height: "20" } },
};
const layerValue = { name: "내 이름", box: { height: "20" } };

// 비활성은 필드 행의 <fieldset disabled>로 표현한다(브라우저가 하위 컨트롤 전체를 비활성 처리).
const isLocked = (el: HTMLElement) => (el.closest("fieldset.ac-sf-prov-body") as HTMLFieldSetElement).disabled;

function row(label: string): HTMLElement {
  return screen.getAllByText(label)[0]!.closest(".ac-sf-prov-row") as HTMLElement;
}

describe("출처 표시 모드", () => {
  it("prop이 없으면 출처 UI가 없다(기존 동작)", () => {
    const { container } = render(<SchemaForm schema={schema} value={layerValue} />);
    expect(container.querySelector(".ac-sf-prov-row, .ac-sf-badge")).toBeNull();
  });

  it("필드 상태 3가지와 mixed 배지를 그린다", () => {
    render(<SchemaForm schema={schema} value={layerValue} {...base} />);
    expect(row("이름").dataset.state).toBe("set");
    expect(within(row("이름")).getByRole("button", { name: /첫째|셋째/ }).textContent).toContain("셋째");
    expect(row("종류").dataset.state).toBe("inherited");
    expect(within(row("종류")).getByText("첫째")).toBeTruthy();
    expect(row("태그").dataset.state).toBe("inherited");
    expect(row("추가").dataset.state).toBe("default");
    expect(within(row("추가")).getByText("기본값")).toBeTruthy();
    // 객체: 잎 출처가 L1·L3 두 층
    expect(screen.getByText("혼합 2층")).toBeTruthy();
    expect(row("너비").dataset.state).toBe("inherited");
    expect(row("높이").dataset.state).toBe("set");
  });

  it("상속·기본값 필드는 입력이 비활성이고 덮어쓰기/지정 버튼이 path와 함께 호출된다", () => {
    const onOverride = vi.fn();
    render(<SchemaForm schema={schema} value={layerValue} {...base} onOverride={onOverride} />);
    expect(isLocked(within(row("종류")).getByRole("combobox"))).toBe(true);
    expect(isLocked(within(row("이름")).getByRole("textbox"))).toBe(false);
    fireEvent.click(within(row("종류")).getByRole("button", { name: "이 층에서 덮어쓰기" }));
    expect(onOverride).toHaveBeenCalledWith("/kind");
    fireEvent.click(within(row("추가")).getByRole("button", { name: "이 층에서 지정" }));
    expect(onOverride).toHaveBeenCalledWith("/extra");
    fireEvent.click(within(row("너비")).getByRole("button", { name: "이 층에서 덮어쓰기" }));
    expect(onOverride).toHaveBeenCalledWith("/box/width");
  });

  it("되돌리기 버튼은 지정된 필드에만 있고 onInherit을 호출한다", () => {
    const onInherit = vi.fn();
    render(<SchemaForm schema={schema} value={layerValue} {...base} onInherit={onInherit} />);
    expect(within(row("종류")).queryByRole("button", { name: /상속으로 되돌리기/ })).toBeNull();
    fireEvent.click(within(row("높이")).getByRole("button", { name: /상속으로 되돌리기/ }));
    expect(onInherit).toHaveBeenCalledWith("/box/height");
  });

  it("입력을 비워도 onInherit을 호출하지 않고 이 층 값만 돌려준다", () => {
    const onInherit = vi.fn();
    const onChange = vi.fn();
    render(<SchemaForm schema={schema} value={layerValue} {...base} onInherit={onInherit} onChange={onChange} />);
    const input = within(row("이름")).getByRole("textbox");
    fireEvent.change(input, { target: { value: "" } });
    expect(onInherit).not.toHaveBeenCalled();
    expect(onChange).toHaveBeenLastCalledWith({ name: "", box: { height: "20" } });
    fireEvent.change(input, { target: { value: "바뀜" } });
    const last = onChange.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(last).toEqual({ name: "바뀜", box: { height: "20" } }); // 상속 값(kind, tags, width) 미포함
  });

  it("Alt+Enter로 덮어쓰기/되돌리기를 토글한다", () => {
    const onOverride = vi.fn();
    const onInherit = vi.fn();
    render(<SchemaForm schema={schema} value={layerValue} {...base} onOverride={onOverride} onInherit={onInherit} />);
    fireEvent.keyDown(within(row("종류")).getByRole("combobox"), { key: "Enter", altKey: true });
    expect(onOverride).toHaveBeenCalledWith("/kind");
    fireEvent.keyDown(within(row("이름")).getByRole("textbox"), { key: "Enter", altKey: true });
    expect(onInherit).toHaveBeenCalledWith("/name");
  });

  it("덮어쓰기 후 편집 가능해지면 입력으로 포커스를 옮긴다", () => {
    function Host() {
      const [v, setV] = useState<Record<string, unknown>>(layerValue);
      return (
        <SchemaForm
          schema={schema}
          {...base}
          provenance={{ ...base.provenance, ...("kind" in v ? { "/kind": "L3" } : {}) }}
          value={v}
          onChange={(n) => setV(n as Record<string, unknown>)}
          onOverride={(p) => p === "/kind" && setV({ ...v, kind: "a" })}
        />
      );
    }
    render(<Host />);
    fireEvent.click(within(row("종류")).getByRole("button", { name: "이 층에서 덮어쓰기" }));
    expect(row("종류").dataset.state).toBe("set");
    expect(document.activeElement).toBe(within(row("종류")).getByRole("combobox"));
  });

  it("배지를 누르면 층 순서대로 값이 정해지는 과정을 보여 주고 층 줄 이동 콜백을 부른다", () => {
    const onOpenLayer = vi.fn();
    render(
      <SchemaForm
        schema={schema}
        value={layerValue}
        {...base}
        layerValues={{ L1: { kind: "a" }, L3: { kind: "b" } }}
        onOpenLayer={onOpenLayer}
      />,
    );
    fireEvent.click(within(row("종류")).getByRole("button", { name: /첫째/ }));
    const pop = screen.getByRole("group", { name: "도움말" });
    const items = within(pop).getAllByRole("listitem").map((li) => li.textContent);
    expect(items).toEqual(["첫째: a ← 적용", "둘째: 비어 있음", "셋째: b"]);
    fireEvent.click(within(pop).getAllByRole("button")[1]!);
    expect(onOpenLayer).toHaveBeenCalledWith("L2");
  });

  it("disabledPaths: 사유와 자물쇠를 보이고 입력·버튼을 막는다(하위 경로 포함)", () => {
    const onOverride = vi.fn();
    render(
      <SchemaForm
        schema={schema}
        value={layerValue}
        {...base}
        onOverride={onOverride}
        disabledPaths={{ "/box": "이 방식에서는 적용되지 않음", "/kind": "사유 B" }}
      />,
    );
    expect(screen.getByText("사유 B")).toBeTruthy();
    expect(screen.getAllByText("이 방식에서는 적용되지 않음")).toHaveLength(1); // 사유는 막힌 가장 상위 행에만
    const kind = row("종류");
    expect(kind.getAttribute("aria-disabled")).toBe("true");
    const btn = within(kind).getByRole("button", { name: "이 층에서 덮어쓰기" }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.click(btn);
    expect(onOverride).not.toHaveBeenCalled();
    expect(isLocked(within(row("높이")).getByRole("textbox"))).toBe(true);
    expect(row("높이").getAttribute("aria-disabled")).toBe("true");
  });

  it("disabledPaths만 줘도 동작하고 값 변경은 그대로 통지한다", () => {
    const onChange = vi.fn();
    render(<SchemaForm schema={schema} value={{ name: "a" }} disabledPaths={{ "/kind": "막힘" }} onChange={onChange} />);
    expect(screen.getByText("막힘")).toBeTruthy();
    fireEvent.change(within(row("이름")).getByRole("textbox"), { target: { value: "b" } });
    expect(onChange).toHaveBeenLastCalledWith({ name: "b" });
  });

  it("fieldWarnings·mergeNotes를 표시하고 renderProvenanceBadge로 배지를 바꿀 수 있다", () => {
    render(
      <SchemaForm
        schema={schema}
        value={layerValue}
        {...base}
        fieldWarnings={{ "/kind": "넓게 허용" }}
        mergeNotes={{ "/tags": "병합: 교집합" }}
        renderProvenanceBadge={(i) => <b data-testid="custom">{i.variant}:{i.layer?.index ?? "-"}</b>}
      />,
    );
    expect(screen.getByText(/넓게 허용/)).toBeTruthy();
    expect(screen.getByText("병합: 교집합")).toBeTruthy();
    expect(within(row("이름")).getByTestId("custom").textContent).toBe("set:2");
    expect(within(row("추가")).getByTestId("custom").textContent).toBe("default:-");
  });

  it("층 id를 코드가 알지 못해도 배열 원소 출처(/tags/0)를 모아 보여 준다", () => {
    render(<SchemaForm schema={schema} value={{}} layers={layers} editLayerId="L3" provenance={{ "/tags/0": "L1", "/tags/1": "L2" }} effectiveValue={{ tags: ["p", "q"] }} />);
    expect(row("태그").dataset.state).toBe("inherited");
    expect(within(row("태그")).getByText("둘째")).toBeTruthy();
  });
});

describe("extractLayerValue", () => {
  it("이 층이 지정한 경로만 새 값을 반영한다", () => {
    const out = extractLayerValue({ a: 1, b: { c: 2, d: 3 }, l: [1, 2] }, { b: { c: 0 }, l: [9] }, { "/a": "me" }, "me");
    expect(out).toEqual({ a: 1, b: { c: 2 }, l: [1, 2] });
  });
});
