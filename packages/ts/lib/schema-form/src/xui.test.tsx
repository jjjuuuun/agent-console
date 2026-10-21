import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SchemaForm } from "./index";
import type { JsonSchema, SchemaFormProps } from "./index";
import { readXUi, resolveNode, resolveTier, splitByTier } from "./xui";

afterEach(cleanup);
beforeEach(() => localStorage.clear());

// 도메인과 무관한 임의 스키마.
const schema: JsonSchema = {
  type: "object",
  required: ["alpha"],
  properties: {
    alpha: { type: "string", title: "알파", description: "알파를 설명하는 한 줄", "x-ui": { tier: "basic", when: "알파를 바꾸는 때", example: "예시-알파" } },
    beta: { type: "string", title: "베타", description: "베타 설명" },
    gamma: { type: "integer", title: "감마", default: 3, description: "감마 설명", "x-ui": { unit: "초", example: "7", when: "감마를 바꿀 때", group: "g1", group_title: "그룹 하나" } },
    delta: { type: "string", title: "델타", default: "d", description: "델타 설명" },
    ro: { type: "string", title: "읽기", readOnly: true, "x-ui": { tier: "basic" } },
  },
};

function Host(p: Partial<SchemaFormProps> & { initial?: unknown }) {
  const [v, setV] = useState<unknown>(p.initial ?? {});
  const { initial: _i, ...rest } = p;
  void _i;
  return <SchemaForm schema={schema} value={v} onChange={setV} {...rest} />;
}

describe("x-ui 읽기", () => {
  it("키를 읽고 잘못된 타입은 버린다", () => {
    expect(readXUi({ "x-ui": { tier: "advanced", when: "w", example: 1, group: "g", group_title: "t", order: 2, unit: "s" } })).toEqual({ tier: "advanced", when: "w", example: 1, group: "g", groupTitle: "t", order: 2, unit: "s" });
    expect(readXUi({ "x-ui": { tier: "weird", order: "x" } })).toEqual({});
    expect(readXUi({})).toEqual({});
  });

  it("tier 폴백: 명시 > required > 자식 > 기본값 유무", () => {
    const root = {};
    expect(resolveTier({ "x-ui": { tier: "advanced" } }, true, root)).toBe("advanced");
    expect(resolveTier({ default: 1 }, true, root)).toBe("basic");
    expect(resolveTier({ default: 1 }, false, root)).toBe("advanced");
    expect(resolveTier({ type: "string" }, false, root)).toBe("basic");
    expect(resolveTier({ type: "object", properties: { a: { default: 1 }, b: {} } }, false, root)).toBe("basic");
    expect(resolveTier({ type: "object", properties: { a: { default: 1 } } }, false, root)).toBe("advanced");
  });

  it("$ref·allOf 래퍼를 풀고 x-ui를 합친다", () => {
    const root = { $defs: { T: { type: "string", "x-ui": { tier: "advanced", unit: "u" } } } };
    expect(readXUi(resolveNode({ $ref: "#/$defs/T", "x-ui": { unit: "v" } }, root))).toEqual({ tier: "advanced", unit: "v" });
    expect(readXUi(resolveNode({ allOf: [{ $ref: "#/$defs/T" }] }, root)).tier).toBe("advanced");
  });

  it("order가 있는 항목이 먼저 온다", () => {
    const s = { properties: { a: {}, b: { "x-ui": { order: 1 } }, c: { "x-ui": { order: 0 } } } };
    const { basic } = splitByTier([{ name: "a" }, { name: "b" }, { name: "c" }], s, s);
    expect(basic.map((e) => e.name)).toEqual(["c", "b", "a"]);
  });
});

describe("x-ui 렌더", () => {
  it("필수 칩, 설명 한 줄, 예시·기본값, 단위를 보인다", () => {
    render(<Host />);
    const alpha = screen.getByLabelText("알파").closest(".ac-sf-field") as HTMLElement;
    expect(within(alpha).getByText("필수")).toBeTruthy();
    expect(within(alpha).getByText("알파를 설명하는 한 줄")).toBeTruthy();
    // 도움말 버튼은 없다. 예시·기본값·바꾸는 때는 라벨 말풍선(장식)과 Alt+I 팝오버에 있다
    expect(within(alpha).queryByRole("button", { name: "도움말 (Alt+I)" })).toBeNull();
    expect(alpha.querySelector(".ac-sf-help-host[data-help] .ac-sf-help-target")).toBeTruthy();
    expect(alpha.querySelector(".ac-sf-tip")?.textContent).toContain("예: 예시-알파");
    expect(alpha.querySelector(".ac-sf-popover")).toBeNull();
    fireEvent.keyDown(screen.getByLabelText("알파"), { key: "i", code: "KeyI", altKey: true });
    expect(alpha.querySelector(".ac-sf-popover")?.textContent).toContain("예: 예시-알파");
    expect(screen.getByLabelText("감마", { selector: "input" }).closest(".ac-sf-field")?.querySelector(".ac-sf-tip")?.textContent).toContain("기본값: 3");
    expect(screen.getByText("초")).toBeTruthy();
    // 선택 필드는 필수 칩이 없다
    expect(within(screen.getByLabelText("베타").closest(".ac-sf-field") as HTMLElement).queryByText("필수")).toBeNull();
  });

  it("예시를 누르면 빈 칸을 채우고, 값이 있으면 버튼이 아니다", () => {
    const onChange = vi.fn();
    const { rerender } = render(<SchemaForm schema={schema} value={{}} onChange={onChange} />);
    const open = () => fireEvent.keyDown(screen.getByLabelText("알파"), { key: "i", code: "KeyI", altKey: true });
    open();
    fireEvent.click(screen.getByRole("button", { name: "예: 예시-알파" }));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ alpha: "예시-알파" }));
    rerender(<SchemaForm schema={schema} value={{ alpha: "x" }} onChange={onChange} />);
    expect(screen.queryByRole("button", { name: "예: 예시-알파" })).toBeNull();
  });

  it("숫자 필드 예시는 숫자로 채운다", () => {
    const onChange = vi.fn();
    const s: JsonSchema = { type: "object", properties: { n: { type: "integer", title: "수", "x-ui": { tier: "basic", example: "7" } } } };
    render(<SchemaForm schema={s} value={{}} onChange={onChange} />);
    fireEvent.keyDown(screen.getByLabelText("수"), { key: "i", code: "KeyI", altKey: true });
    fireEvent.click(screen.getByRole("button", { name: "예: 7" }));
    expect(onChange).toHaveBeenLastCalledWith({ n: 7 });
  });

  it("고급 영역: 기본 닫힘, 개수 표시, 그룹 소제목, 펼침 기억", () => {
    const { unmount } = render(<Host advancedStorageKey="demo" />);
    const toggle = screen.getByRole("button", { name: /고급 설정 \(2\)/ });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("textbox", { name: "델타" })).toBeNull();
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("그룹 하나")).toBeTruthy();
    expect(screen.getByLabelText("델타")).toBeTruthy();
    expect(localStorage.getItem("ac.form.advanced.demo")).toBe("1");
    unmount();
    render(<Host advancedStorageKey="demo" />);
    expect(screen.getByRole("button", { name: /고급 설정/ }).getAttribute("aria-expanded")).toBe("true");
  });

  it("지정된 고급 필드 수를 칩으로 보인다", () => {
    render(<Host initial={{ delta: "바꿈" }} />);
    expect(screen.getByText("지정 1")).toBeTruthy();
  });

  it("고급 필드에 오류가 있으면 자동으로 펼친다", () => {
    render(<SchemaForm schema={schema} value={{}} errors={[{ path: "/delta", message: "문제" }]} />);
    expect(screen.getByRole("button", { name: /고급 설정/ }).getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText(/문제/)).toBeTruthy();
  });

  it("focusPath가 고급 필드면 펼친다", () => {
    render(<SchemaForm schema={schema} value={{}} focusPath="/delta" />);
    expect(screen.getByRole("button", { name: /고급 설정/ }).getAttribute("aria-expanded")).toBe("true");
  });

  it("읽기 전용 값은 텍스트와 복사 버튼", () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<SchemaForm schema={schema} value={{ ro: "서버-값" }} />);
    expect(screen.getByText("서버-값")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "복사" }));
    expect(writeText).toHaveBeenCalledWith("서버-값");
  });

  it("x-ui 없는 스키마도 폴백으로 동작하고 xui={false}면 기본 모양", () => {
    const plain: JsonSchema = { type: "object", properties: { a: { type: "string", title: "에이", default: "z" }, b: { type: "string", title: "비" } } };
    const { rerender } = render(<SchemaForm schema={plain} value={{}} />);
    expect(screen.getByRole("button", { name: /고급 설정 \(1\)/ })).toBeTruthy();
    expect(screen.getByLabelText("비")).toBeTruthy();
    rerender(<SchemaForm schema={plain} value={{}} xui={false} />);
    expect(screen.queryByRole("button", { name: /고급 설정/ })).toBeNull();
  });

  it("고급만 있는 폼은 접지 않는다", () => {
    const s: JsonSchema = { type: "object", properties: { a: { type: "string", title: "에이", default: "z" } } };
    render(<SchemaForm schema={s} value={{}} />);
    expect(screen.queryByRole("button", { name: /고급 설정/ })).toBeNull();
    expect(screen.getByLabelText("에이")).toBeTruthy();
  });

  it("고급이 없으면 접는 영역이 없다", () => {
    const s: JsonSchema = { type: "object", properties: { a: { type: "string", title: "에이" } } };
    render(<SchemaForm schema={s} value={{}} />);
    expect(screen.queryByRole("button", { name: /고급 설정/ })).toBeNull();
  });

  it("바꾸는 때는 기본·고급 필드 모두 Alt+I 팝오버에 있다", () => {
    const { container } = render(<Host advancedStorageKey="w" />);
    const hint = (t: string) => Array.from(container.querySelectorAll(".ac-sf-popover .ac-sf-hintline")).some((e) => e.textContent === t);
    expect(hint("바꾸는 때: 알파를 바꾸는 때")).toBe(false);
    const alpha = screen.getByLabelText("알파");
    fireEvent.keyDown(alpha, { key: "i", code: "KeyI", altKey: true });
    expect(hint("바꾸는 때: 알파를 바꾸는 때")).toBe(true);
    fireEvent.keyDown(alpha, { key: "i", code: "KeyI", altKey: true });
    expect(hint("바꾸는 때: 알파를 바꾸는 때")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: /고급 설정/ }));
    expect(hint("바꾸는 때: 감마를 바꿀 때")).toBe(false);
    fireEvent.keyDown(screen.getByLabelText("감마"), { key: "i", code: "KeyI", altKey: true });
    expect(hint("바꾸는 때: 감마를 바꿀 때")).toBe(true);
  });

  it("별도 ⓘ 버튼은 없고(말풍선), 배열 필드에도 라벨 줄이 있다", () => {
    const s: JsonSchema = {
      type: "object",
      properties: { tools: { type: "array", title: "도구", description: "도구 설명", items: { type: "string" }, "x-ui": { tier: "basic", when: "좁힐 때" } } },
    };
    const { container } = render(<SchemaForm schema={s} value={{}} />);
    expect(container.querySelectorAll(".ac-sf-info")).toHaveLength(0);
    expect(container.querySelectorAll(".ac-sf-tip")).toHaveLength(1);
    const row = container.querySelector(".ac-sf-field") as HTMLElement;
    expect(within(row.querySelector(".ac-sf-labelrow") as HTMLElement).getByText("도구")).toBeTruthy();
    expect(row.querySelector(".ac-sf-hintline")).toBeNull();
    expect(row.querySelector(".ac-sf-popover")).toBeNull();
  });
});

describe("간소 출처 표시", () => {
  const layers = [
    { id: "L1", label: "공통" },
    { id: "L2", label: "팀" },
  ];
  const s: JsonSchema = {
    type: "object",
    properties: {
      a: { type: "string", title: "에이", "x-ui": { tier: "basic" } },
      b: { type: "string", title: "비", "x-ui": { tier: "basic" } },
    },
  };
  const props = { schema: s, layers, editLayerId: "L2", provenance: { "/b": "L1" }, effectiveValue: { b: "상속값" } } as const;

  it("지정된 필드만 배지·되돌리기 아이콘이 있다", () => {
    render(<SchemaForm {...props} compactProvenance value={{ a: "내값" }} onInherit={vi.fn()} onOverride={vi.fn()} />);
    const a = screen.getByLabelText("에이").closest(".ac-sf-prov-row") as HTMLElement;
    const b = screen.getByLabelText("비").closest(".ac-sf-prov-row") as HTMLElement;
    expect(within(a).getByRole("button", { name: "상속으로 되돌리기" })).toBeTruthy();
    expect(within(a).getByText("팀")).toBeTruthy();
    expect(within(b).queryByRole("button", { name: /상속으로 되돌리기|덮어쓰기|지정/ })).toBeNull();
    expect(within(b).getByText("공통에서 상속")).toBeTruthy();
  });

  it("지정하지 않은 필드를 바로 편집하면 이 층 값으로 들어간다", () => {
    const onChange = vi.fn();
    render(<SchemaForm {...props} compactProvenance value={{}} onChange={onChange} />);
    const input = screen.getByLabelText("비") as HTMLInputElement;
    expect(input.disabled).toBe(false);
    expect(input.value).toBe("상속값");
    fireEvent.change(input, { target: { value: "새값" } });
    expect(onChange).toHaveBeenLastCalledWith({ b: "새값" });
  });

  it("다른 필드만 바꾸면 빈 nullable 객체는 이 층 값에 들어가지 않는다", () => {
    const sc: JsonSchema = {
      type: "object",
      properties: {
        a: { type: "string", title: "에이", "x-ui": { tier: "basic" } },
        lim: { anyOf: [{ type: "object", properties: { n: { type: "integer", title: "수" } } }, { type: "null" }], default: null, title: "한도", "x-ui": { tier: "basic" } },
      },
    };
    const onChange = vi.fn();
    render(<SchemaForm schema={sc} compactProvenance layers={layers} editLayerId="L2" provenance={{}} effectiveValue={{ lim: null }} value={{}} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("에이"), { target: { value: "x" } });
    expect(onChange).toHaveBeenLastCalledWith({ a: "x" });
  });
});

describe("중첩 객체 설명(출처 표시)", () => {
  it("접을 수 있는 객체(null 허용)의 설명은 한 번만 그려진다(행과 객체 템플릿이 겹치지 않는다)", () => {
    const nested: JsonSchema = {
      type: "object",
      properties: {
        group: {
          type: ["object", "null"],
          title: "묶음",
          description: "묶음을 설명하는 한 줄",
          properties: { inner: { type: "string", title: "안쪽", description: "안쪽 설명" } },
          "x-ui": { tier: "basic" },
        },
      },
    };
    const { container } = render(
      <Host schema={nested} initial={{ group: { inner: "v" } }} layers={[{ id: "L1", label: "첫째" }]} editLayerId="L1" provenance={{ "/group": "L1" }} effectiveValue={{ group: { inner: "v" } }} />,
    );
    expect((container.textContent ?? "").split("묶음을 설명하는 한 줄").length - 1).toBe(1);
    expect(screen.getByText("안쪽 설명")).toBeTruthy();
  });
});

describe("불리언·enum·속성 추가 단추 (F11)", () => {
  const s: JsonSchema = {
    type: "object",
    additionalProperties: true,
    properties: {
      flag: { type: "boolean", title: "답하기", description: "설명 한 번만", default: true, "x-ui": { tier: "basic", when: "끌 때" } },
      mode: { type: "string", title: "방식", enum: ["ask", "run"], "x-ui": { tier: "basic", enum_labels: { ask: "물어보기", run: "바로 실행" } } },
      pick: { type: "string", title: "고르기", oneOf: [{ const: "a", title: "에이 라벨" }, { const: "b", title: "비 라벨" }], "x-ui": { tier: "basic" } },
    },
  };
  it("불리언은 체크박스+라벨 한 줄이고 설명은 한 번, 빈 ? 줄이 없다", () => {
    const { container } = render(<SchemaForm schema={s} value={{}} />);
    expect(screen.getAllByText("설명 한 번만")).toHaveLength(1);
    expect(screen.getByRole("checkbox", { name: "답하기" })).toBeTruthy();
    const row = screen.getByRole("checkbox", { name: "답하기" }).closest(".ac-sf-field") as HTMLElement;
    expect(row.querySelector(".ac-sf-labelrow")).toBeNull();
    expect(row.querySelector(".ac-sf-check[data-help] .ac-sf-tip")).toBeTruthy();
    expect(container.querySelector(".ac-sf-info")).toBeNull();
  });
  it("enum은 x-ui.enum_labels, oneOf는 title을 라벨로 쓴다", () => {
    render(<SchemaForm schema={s} value={{}} />);
    expect(screen.getByRole("option", { name: "물어보기" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "바로 실행" })).toBeTruthy();
    expect(screen.queryByRole("option", { name: "ask" })).toBeNull();
    expect(screen.getByRole("option", { name: "에이 라벨" })).toBeTruthy();
  });
  it("선언된 속성이 있는 루트에는 속성 추가 단추가 없다", () => {
    render(<SchemaForm schema={s} value={{}} />);
    expect(screen.queryByRole("button", { name: "항목 추가" })).toBeNull();
  });
});
