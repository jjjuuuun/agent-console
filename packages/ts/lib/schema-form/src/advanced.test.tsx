import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { SchemaForm } from "./index";
import type { JsonSchema, SchemaFormProps } from "./index";

afterEach(cleanup);
beforeEach(() => localStorage.clear());

// 도메인과 무관한 임의 스키마: 기본 필드 1개(a), 고급 필드 2개(b, c)
const schema: JsonSchema = {
  type: "object",
  properties: {
    a: { type: "string", title: "에이", "x-ui": { tier: "basic" } },
    b: { type: "string", title: "비", default: "d" },
    c: { type: "integer", title: "씨", default: 3 },
  },
};
const allAdvanced: JsonSchema = { type: "object", properties: { b: { type: "string", title: "비", default: "d" } } };

function Host(p: Partial<SchemaFormProps> & { initial?: unknown }) {
  const [v, setV] = useState<unknown>(p.initial ?? {});
  const { initial: _i, ...rest } = p;
  void _i;
  return <SchemaForm schema={schema} value={v} onChange={setV} {...rest} />;
}
const toggle = () => screen.getByRole("button", { name: /고급 설정/ });
const expanded = () => toggle().getAttribute("aria-expanded");

describe("고급 접기 (A1~A8)", () => {
  it("A1: 오류가 있어도 토글이 닫힘·열림을 번갈아 하고 저장값도 그대로 따른다", () => {
    render(<Host advancedStorageKey="k" errors={[{ path: "/b", message: "문제" }]} />);
    expect(expanded()).toBe("true");
    fireEvent.click(toggle());
    expect(expanded()).toBe("false");
    expect(localStorage.getItem("ac.form.advanced.k")).toBe("0");
    fireEvent.click(toggle());
    expect(expanded()).toBe("true");
    expect(localStorage.getItem("ac.form.advanced.k")).toBe("1");
  });

  it("A2: 오류를 고쳐도 영역이 접히지 않는다", () => {
    const { rerender } = render(<SchemaForm schema={schema} value={{}} errors={[{ path: "/b", message: "문제" }]} />);
    expect(expanded()).toBe("true");
    rerender(<SchemaForm schema={schema} value={{ b: "x" }} errors={[]} />);
    expect(expanded()).toBe("true");
    expect(screen.getByLabelText("비")).toBeTruthy();
  });

  it("A3: focusPath를 유지해도 닫을 수 있고, 같은 값 재전달은 다시 열지 않는다", () => {
    const { rerender } = render(<SchemaForm schema={schema} value={{}} focusPath="/b" />);
    expect(expanded()).toBe("true");
    fireEvent.click(toggle());
    expect(expanded()).toBe("false");
    rerender(<SchemaForm schema={schema} value={{ b: "x" }} focusPath="/b" />);
    expect(expanded()).toBe("false");
    rerender(<SchemaForm schema={schema} value={{ b: "x" }} focusPath="/c" />);
    expect(expanded()).toBe("true");
  });

  it("A4: 저장 키가 바뀌면 새 키의 저장값으로 다시 맞추고 토글 전에는 쓰지 않는다", () => {
    localStorage.setItem("ac.form.advanced.one", "1");
    localStorage.setItem("ac.form.advanced.two", "0");
    const { rerender } = render(<SchemaForm schema={schema} value={{}} advancedStorageKey="one" />);
    expect(expanded()).toBe("true");
    rerender(<SchemaForm schema={schema} value={{}} advancedStorageKey="two" />);
    expect(expanded()).toBe("false");
    expect(localStorage.getItem("ac.form.advanced.one")).toBe("1");
    fireEvent.click(toggle());
    expect(localStorage.getItem("ac.form.advanced.two")).toBe("1");
    expect(localStorage.getItem("ac.form.advanced.one")).toBe("1");
  });

  it("A5: 같은 키를 쓰는 두 폼은 열림을 공유하고 키에는 인스턴스 id가 없다", () => {
    const { unmount } = render(<SchemaForm schema={schema} value={{}} advancedStorageKey="kind-x" idPrefix="node-7" />);
    fireEvent.click(toggle());
    unmount();
    render(<SchemaForm schema={schema} value={{}} advancedStorageKey="kind-x" idPrefix="node-8" />);
    expect(expanded()).toBe("true");
    expect(Object.keys(localStorage).filter((k) => k.includes("node-"))).toEqual([]);
  });

  it("A6: 기본 필드가 0개면 접기 줄 없이 모두 펼치고 안내 한 줄을 둔다", () => {
    render(<SchemaForm schema={allAdvanced} value={{}} />);
    expect(screen.queryByRole("button", { name: /고급 설정/ })).toBeNull();
    expect(screen.getByText("이 폼의 항목은 모두 고급 설정입니다")).toBeTruthy();
    expect(screen.getByLabelText("비")).toBeTruthy();
  });

  it("A7: 지정 N은 명시적 null과 기본값 그대로를 세지 않고, 출처 표시 모드에서는 행 칩과 같은 판정이다", () => {
    const { rerender } = render(<SchemaForm schema={schema} value={{ b: null, c: 3 }} />);
    expect(screen.queryByText(/지정 \d/)).toBeNull();
    rerender(<SchemaForm schema={schema} value={{ b: "바뀜", c: 3 }} />);
    expect(screen.getByText("지정 1")).toBeTruthy();
    // 출처 표시: 이 층(L1)이 지정한 것만 센다. 상속(L0)은 센다 않는다.
    const layers = [
      { id: "L0", label: "공통" },
      { id: "L1", label: "팀" },
    ];
    rerender(<SchemaForm schema={schema} value={{ b: "바뀜" }} layers={layers} editLayerId="L1" provenance={{ "/b": "L1", "/c": "L0" }} effectiveValue={{ c: 9 }} />);
    expect(screen.getByText("지정 1")).toBeTruthy();
    rerender(<SchemaForm schema={schema} value={{}} layers={layers} editLayerId="L1" provenance={{ "/b": "L0", "/c": "L0" }} effectiveValue={{ b: "q", c: 9 }} />);
    expect(screen.queryByText(/지정 \d/)).toBeNull();
  });

  it("A8: 토글 줄은 sticky 막대 안에 있고 접어도 포커스가 토글에 남는다", () => {
    render(<Host advancedStorageKey="s" />);
    const bar = toggle().closest(".ac-sf-adv-bar");
    expect(bar).not.toBeNull();
    fireEvent.click(toggle());
    toggle().focus();
    fireEvent.click(toggle());
    expect(document.activeElement).toBe(toggle());
  });

  it("닫힌 상태에서 오류 N 칩이 뜬다(자동 열기 후 사용자가 닫은 경우)", () => {
    render(<SchemaForm schema={schema} value={{}} errors={[{ path: "/b", message: "문제" }, { path: "/c", message: "문제2" }]} />);
    expect(screen.getByText(/오류 2/)).toBeTruthy();
    fireEvent.click(toggle());
    expect(expanded()).toBe("false");
    expect(screen.getByText(/오류 2/)).toBeTruthy();
  });

  it("오류가 새로 늘어난 순간에만 다시 열린다", () => {
    const { rerender } = render(<SchemaForm schema={schema} value={{}} errors={[{ path: "/b", message: "문제" }]} />);
    fireEvent.click(toggle());
    rerender(<SchemaForm schema={schema} value={{ x: 1 }} errors={[{ path: "/b", message: "문제" }]} />);
    expect(expanded()).toBe("false");
    act(() => {
      rerender(<SchemaForm schema={schema} value={{}} errors={[{ path: "/b", message: "문제" }, { path: "/c", message: "새" }]} />);
    });
    expect(expanded()).toBe("true");
  });
});
