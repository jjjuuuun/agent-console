import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getContractSchema } from "@agent-console/contracts";
import { SchemaForm, getDefaultValue } from "./index";
import { normalizeNullable } from "./nullable";
import type { FormError, JsonSchema, SchemaFormWidgetProps } from "./index";

afterEach(cleanup);

// 특정 도메인(노드 타입·에이전트)과 무관한 임의 스키마.
const arbitrary: JsonSchema = {
  type: "object",
  required: ["title"],
  properties: {
    title: { type: "string", title: "제목", description: "짧은 이름" },
    count: { type: "integer", title: "개수", minimum: 1, maximum: 5, default: 2 },
    ratio: { type: "number", title: "비율" },
    enabled: { type: "boolean", title: "사용" },
    kind: { type: "string", title: "종류", enum: ["alpha", "beta", "gamma"] },
    tags: { type: "array", title: "태그", items: { type: "string" } },
    nested: {
      type: "object",
      title: "중첩",
      properties: { inner: { type: "object", title: "더 안쪽", properties: { deep: { type: "string", title: "깊은 값" } } } },
    },
  },
};

function Controlled({ schema, initial, onSpy, ...rest }: { schema: JsonSchema; initial?: unknown; onSpy?: (v: unknown) => void } & Partial<React.ComponentProps<typeof SchemaForm>>) {
  const [v, setV] = useState<unknown>(initial);
  return (
    <SchemaForm
      {...rest}
      schema={schema}
      value={v}
      onChange={(next) => {
        setV(next);
        onSpy?.(next);
      }}
    />
  );
}

describe("SchemaForm 필드 생성", () => {
  it("문자열·숫자·불리언·enum·배열·중첩 객체 필드를 그린다", () => {
    render(<SchemaForm schema={arbitrary} value={{}} />);
    for (const label of ["제목", "개수", "비율", "사용", "종류", "태그", "중첩", "더 안쪽", "깊은 값"]) {
      expect(screen.getAllByText(new RegExp(label)).length).toBeGreaterThan(0);
    }
    expect(screen.getByLabelText(/제목/)).toBeTruthy();
    const select = screen.getByLabelText(/종류/) as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.text)).toEqual(expect.arrayContaining(["alpha", "beta", "gamma"]));
    expect(screen.getByText("짧은 이름")).toBeTruthy();
    expect(screen.getByRole("button", { name: /항목 추가/ })).toBeTruthy();
  });

  it("스키마가 바뀌면 다른 필드가 그려진다(코드에 필드 고정 없음)", () => {
    const { rerender } = render(<SchemaForm schema={{ type: "object", properties: { aaa: { type: "string", title: "에이" } } }} value={{}} />);
    expect(screen.getByLabelText("에이")).toBeTruthy();
    rerender(<SchemaForm schema={{ type: "object", properties: { zzz: { type: "string", title: "제트" } } }} value={{}} />);
    expect(screen.queryByLabelText("에이")).toBeNull();
    expect(screen.getByLabelText("제트")).toBeTruthy();
  });

  it("uiSchema 위젯 힌트(textarea)를 따른다", () => {
    render(<SchemaForm schema={{ type: "object", properties: { memo: { type: "string", title: "메모" } } }} uiSchema={{ memo: { "ui:widget": "textarea" } }} value={{}} />);
    expect(screen.getByLabelText("메모").tagName).toBe("TEXTAREA");
  });

  it("idPrefix로 id 충돌을 막는다", () => {
    render(<SchemaForm schema={arbitrary} value={{}} idPrefix="formA" />);
    expect(document.getElementById("formA_title")).toBeTruthy();
    expect(document.getElementById("root_title")).toBeNull();
  });

  it("properties가 없는 객체는 빈 상태 문구를 보인다", () => {
    render(<SchemaForm schema={{ type: "object" }} value={{}} />);
    expect(screen.getByText("설정할 항목이 없습니다")).toBeTruthy();
  });
});

describe("SchemaForm onChange", () => {
  it("마운트 시 기본값 채움으로는 onChange를 호출하지 않는다", () => {
    const spy = vi.fn();
    render(<SchemaForm schema={arbitrary} value={{}} onChange={spy} />);
    expect(spy).not.toHaveBeenCalled();
  });

  it("문자열 편집 시 새 값을 전달한다", () => {
    const spy = vi.fn();
    render(<Controlled schema={arbitrary} initial={{}} onSpy={spy} />);
    fireEvent.change(screen.getByLabelText(/제목/), { target: { value: "안녕" } });
    expect(spy).toHaveBeenCalled();
    expect(spy.mock.calls.at(-1)?.[0]).toMatchObject({ title: "안녕" });
  });

  it("숫자·enum 편집이 타입에 맞게 전달된다", () => {
    const spy = vi.fn();
    render(<Controlled schema={arbitrary} initial={{}} onSpy={spy} />);
    fireEvent.change(screen.getByLabelText(/개수/), { target: { value: "4" } });
    expect(spy.mock.calls.at(-1)?.[0]).toMatchObject({ count: 4 });
    const select = screen.getByLabelText(/종류/) as HTMLSelectElement;
    const beta = Array.from(select.options).find((o) => o.text === "beta");
    fireEvent.change(select, { target: { value: beta?.value } });
    expect(spy.mock.calls.at(-1)?.[0]).toMatchObject({ kind: "beta" });
  });

  it("배열 항목을 추가하고 입력할 수 있다", () => {
    const spy = vi.fn();
    render(<Controlled schema={arbitrary} initial={{}} onSpy={spy} />);
    fireEvent.click(screen.getByRole("button", { name: /항목 추가/ }));
    expect((spy.mock.calls.at(-1)?.[0] as { tags: unknown[] }).tags).toHaveLength(1);
    const input = document.getElementById("root_tags_0") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "x" } });
    expect(spy.mock.calls.at(-1)?.[0]).toMatchObject({ tags: ["x"] });
  });

  it("깊게 중첩된 필드 편집이 전달된다", () => {
    const spy = vi.fn();
    render(<Controlled schema={arbitrary} initial={{}} onSpy={spy} />);
    fireEvent.change(screen.getByLabelText("깊은 값"), { target: { value: "v" } });
    expect(spy.mock.calls.at(-1)?.[0]).toMatchObject({ nested: { inner: { deep: "v" } } });
  });
});

describe("오류 표시", () => {
  it("errors의 JSON Pointer를 필드별 오류로 매핑한다(경고 포함)", () => {
    const errors: FormError[] = [
      { path: "/title", message: "서버 거부" },
      { path: "/ratio", message: "주의 값", severity: "warning" },
    ];
    render(<SchemaForm schema={arbitrary} value={{}} errors={errors} />);
    expect(screen.getByText(/서버 거부/).textContent).toContain("⚠");
    expect(screen.getByText(/주의 값/).textContent).toContain("▲");
  });

  it("validateOn=change이면 클라이언트 검증 메시지를 한국어로 보인다", () => {
    render(<SchemaForm schema={arbitrary} value={{ count: 9 }} validateOn="change" />);
    expect(screen.getByText(/5 이하여야 합니다/)).toBeTruthy();
  });

  it("validateOn=submit이면 클라이언트 검증을 표시하지 않는다", () => {
    render(<SchemaForm schema={arbitrary} value={{ count: 9 }} validateOn="submit" />);
    expect(screen.queryByText(/이하여야/)).toBeNull();
  });
});

describe("기타", () => {
  it("customWidgets가 ui:widget 이름으로 주입된다", () => {
    function Pick({ value, onChange, label }: SchemaFormWidgetProps) {
      return (
        <button type="button" onClick={() => onChange("picked")}>
          {label}:{String(value ?? "-")}
        </button>
      );
    }
    const spy = vi.fn();
    render(
      <Controlled
        schema={{ type: "object", properties: { target: { type: "string", title: "대상" } } }}
        uiSchema={{ target: { "ui:widget": "picker" } }}
        customWidgets={{ picker: Pick }}
        initial={{}}
        onSpy={spy}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /대상/ }));
    expect(spy.mock.calls.at(-1)?.[0]).toEqual({ target: "picked" });
  });

  it("해석 불가 스키마(true, {})는 원시 JSON 편집기로 대체되고 유효한 JSON일 때만 onChange", () => {
    const spy = vi.fn();
    render(<SchemaForm schema={{}} value={{ a: 1 }} onChange={spy} />);
    const ta = screen.getByLabelText("JSON 편집");
    fireEvent.change(ta, { target: { value: "{bad" } });
    expect(spy).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toContain("올바른 JSON이 아닙니다");
    fireEvent.change(ta, { target: { value: '{"b":2}' } });
    expect(spy).toHaveBeenCalledWith({ b: 2 });
  });

  it("{ } JSON 토글로 폼과 원시 편집을 전환한다", () => {
    render(<SchemaForm schema={arbitrary} value={{ title: "t" }} />);
    fireEvent.click(screen.getByRole("button", { name: "{ } JSON" }));
    expect((screen.getByLabelText("JSON 편집") as HTMLTextAreaElement).value).toContain('"title": "t"');
    fireEvent.click(screen.getByRole("button", { name: "폼으로 보기" }));
    expect(screen.getByLabelText(/제목/)).toBeTruthy();
  });

  it("focusPath의 필드로 포커스를 옮긴다", () => {
    render(<SchemaForm schema={arbitrary} value={{}} focusPath="/title" />);
    expect(document.activeElement?.id).toBe("root_title");
  });

  it("focusPath 필드가 늦게 그려져도 생기면 포커스하고 onFocusReached를 부른다", async () => {
    const early: JsonSchema = { type: "object", properties: { other: { type: "string", title: "다른" } } };
    const onReached = vi.fn();
    const { rerender } = render(<SchemaForm schema={early} value={{}} focusPath="/title" onFocusReached={onReached} />);
    expect(document.activeElement?.id).not.toBe("root_title");
    rerender(<SchemaForm schema={arbitrary} value={{}} focusPath="/title" onFocusReached={onReached} />);
    await waitFor(() => expect(document.activeElement?.id).toBe("root_title"));
    expect(onReached).toHaveBeenCalledTimes(1);
  });

  it("disabled이면 입력이 비활성화된다", () => {
    render(<SchemaForm schema={arbitrary} value={{}} disabled />);
    expect((screen.getByLabelText(/제목/) as HTMLInputElement).disabled).toBe(true);
  });

  it("getDefaultValue가 스키마 기본값으로 초기 값을 만든다", () => {
    expect(getDefaultValue(arbitrary)).toMatchObject({ count: 2 });
  });
});

describe("정수·oneOf·additionalProperties (1.17 QA 권고)", () => {
  it("integer는 정수로 전달되고, 정수가 아니면 type 오류를 한국어로 보인다", () => {
    const schema: JsonSchema = { type: "object", properties: { n: { type: "integer", title: "정수값", minimum: 0 } } };
    const spy = vi.fn();
    render(<Controlled schema={schema} initial={{}} onSpy={spy} />);
    fireEvent.change(screen.getByLabelText("정수값"), { target: { value: "7" } });
    expect(spy.mock.calls.at(-1)?.[0]).toEqual({ n: 7 });
    expect(Number.isInteger((spy.mock.calls.at(-1)?.[0] as { n: number }).n)).toBe(true);
    cleanup();
    render(<SchemaForm schema={schema} value={{ n: 1.5 }} validateOn="change" />);
    expect(screen.getByText(/integer 형식이어야 합니다/)).toBeTruthy();
  });

  it("oneOf: 선택한 분기의 필드를 그린다", () => {
    const schema: JsonSchema = {
      type: "object",
      properties: {
        choice: {
          title: "선택",
          oneOf: [
            { title: "문자 분기", type: "object", properties: { kind: { const: "a", type: "string" }, aText: { type: "string", title: "에이 텍스트" } } },
            { title: "숫자 분기", type: "object", properties: { kind: { const: "b", type: "string" }, bNum: { type: "number", title: "비 숫자" } } },
          ],
        },
      },
    };
    render(<SchemaForm schema={schema} value={{ choice: { kind: "b", bNum: 3 } }} />);
    expect(screen.getByLabelText(/비 숫자/)).toBeTruthy();
    expect(screen.queryByLabelText(/에이 텍스트/)).toBeNull();
    const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
    const options = selects.flatMap((s) => Array.from(s.options).map((o) => o.text));
    expect(options).toEqual(expect.arrayContaining(["문자 분기", "숫자 분기"]));
  });

  it("additionalProperties: 키를 추가하고 값을 편집할 수 있다", () => {
    const schema: JsonSchema = {
      type: "object",
      properties: { extra: { type: "object", title: "추가 속성", additionalProperties: { type: "string" } } },
    };
    const spy = vi.fn();
    render(<Controlled schema={schema} initial={{ extra: { k1: "v1" } }} onSpy={spy} />);
    expect((screen.getByDisplayValue("v1") as HTMLInputElement).value).toBe("v1");
    fireEvent.click(screen.getByRole("button", { name: /항목 추가/ }));
    const added = spy.mock.calls.at(-1)?.[0] as { extra: Record<string, string> };
    expect(Object.keys(added.extra)).toHaveLength(2);
    fireEvent.change(screen.getByDisplayValue("v1"), { target: { value: "v2" } });
    expect((spy.mock.calls.at(-1)?.[0] as { extra: Record<string, string> }).extra.k1).toBe("v2");
  });
});

describe("검증 문구 덮어쓰기", () => {
  it("messages로 검증 문구(템플릿)와 required를 바꿀 수 있다", () => {
    const schema: JsonSchema = {
      type: "object",
      required: ["name"],
      properties: { name: { type: "string", title: "이름" }, n: { type: "number", title: "수", maximum: 3 } },
    };
    render(
      <SchemaForm
        schema={schema}
        value={{ n: 9 }}
        validateOn="change"
        messages={{ maximum: "max is {limit}", required: "REQUIRED!" }}
      />,
    );
    expect(screen.getByText(/max is 3/)).toBeTruthy();
    expect(screen.getByText(/REQUIRED!/)).toBeTruthy();
    expect(screen.queryByText(/이하여야/)).toBeNull();
  });
});

describe("$defs / $ref 스키마 (설정 화면용)", () => {
  it("계약의 WorkspaceSettings($ref EditorSettings 포함)가 폼으로 그려진다", () => {
    const schema = getContractSchema("WorkspaceSettings") as JsonSchema;
    const spy = vi.fn();
    render(<Controlled schema={schema} initial={getDefaultValue(schema)} onSpy={spy} />);
    // 계약에서 `deprecated: true`이고 값이 없는 필드는 그리지 않는다(일반 규칙)
    expect(screen.queryByLabelText(/기본 실행 백엔드/)).toBeNull();
    // $ref로 참조된 EditorSettings의 필드
    const kind = screen.getByLabelText(/새 연결 기본 종류/) as HTMLInputElement;
    expect(kind.value).toBe("");
    expect(screen.getByText(/비우면 이을 수 있는 첫 종류/)).toBeTruthy();
    fireEvent.change(kind, { target: { value: "flow" } });
    expect(spy.mock.calls.at(-1)?.[0]).toMatchObject({ editor: { default_edge_kind: "flow" } });
    // 원시 JSON 편집기로 대체되지 않았다
    expect(screen.queryByText(/이 스키마로 폼을 만들 수 없습니다/)).toBeNull();
  });
});

describe("nullable 필드 (Pydantic `str | None`)", () => {
  it("anyOf [string, null]은 선택기가 아니라 텍스트 입력으로 그려지고 null도 유효하다", () => {
    const schema: JsonSchema = {
      type: "object",
      properties: { opt: { anyOf: [{ type: "string" }, { type: "null" }], default: null, title: "선택값" } },
    };
    const spy = vi.fn();
    render(<Controlled schema={schema} initial={{ opt: null }} onSpy={spy} validateOn="change" />);
    const input = screen.getByLabelText("선택값") as HTMLInputElement;
    expect(input.tagName).toBe("INPUT");
    expect(screen.queryByText(/형식이어야/)).toBeNull();
    fireEvent.change(input, { target: { value: "g1" } });
    expect(spy.mock.calls.at(-1)?.[0]).toEqual({ opt: "g1" });
  });
});

describe("normalizeNullable 경계", () => {
  const nullBranch = { type: "null" };
  const wrap = (schema: Record<string, unknown>): JsonSchema => ({ type: "object", properties: { f: schema } });
  const fold = (s: JsonSchema) => normalizeNullable(s) as { properties: { f: Record<string, unknown> } };

  // 1.9 QA 후속: object/array/$ref + null 2분기는 이제 접는다(아래 "비스칼라 nullable" 참고).
  // 접지 않는 형태는 oneOf, 3분기 이상, null이 없는 anyOf, 순환 $ref.
  it.each([
    ["oneOf [string,null]", { oneOf: [{ type: "string" }, nullBranch] }],
    ["anyOf [string,integer]", { anyOf: [{ type: "string" }, { type: "integer" }] }],
    ["anyOf 3분기", { anyOf: [{ type: "string" }, { type: "integer" }, nullBranch] }],
    ["oneOf [object,null]", { oneOf: [{ type: "object", properties: {} }, nullBranch] }],
    ["해석 불가 $ref", { anyOf: [{ $ref: "#/$defs/Missing" }, nullBranch] }],
  ])("접지 않는다: %s", (_n, f) => {
    expect(fold(wrap(f)).properties.f).toEqual(f);
  });

  it("순환 $ref는 접지 않고 무한 재귀하지 않는다", () => {
    const schema = {
      type: "object",
      properties: { node: { anyOf: [{ $ref: "#/$defs/Node" }, nullBranch] } },
      $defs: { Node: { type: "object", properties: { next: { anyOf: [{ $ref: "#/$defs/Node" }, nullBranch] } } } },
    } as JsonSchema;
    const out = normalizeNullable(schema) as { properties: { node: { type: unknown } } };
    expect(out.properties.node.type).toEqual(["object", "null"]);
    // 한 번 인라인한 안쪽의 재귀 참조는 접지 않고 남는다(종료 보장).
    const inner = (out.properties.node as unknown as { properties: { next: unknown } }).properties.next;
    expect(inner).toEqual({ anyOf: [{ $ref: "#/$defs/Node" }, nullBranch] });
  });

  it("enum 분기를 접으면 null이 허용 값에 들어가 null이 검증을 통과한다", () => {
    const f = fold(wrap({ anyOf: [{ type: "string", enum: ["a", "b"] }, nullBranch], title: "열거" })).properties.f;
    expect(f).toMatchObject({ type: ["string", "null"], enum: ["a", "b", null], title: "열거" });
    render(<SchemaForm schema={wrap({ anyOf: [{ type: "string", enum: ["a", "b"] }, nullBranch], title: "열거" })} value={{ f: null }} validateOn="change" />);
    expect(screen.queryByText(/허용된 값이 아닙니다/)).toBeNull();
  });

  it("const 분기는 enum [const, null]이 된다", () => {
    const f = fold(wrap({ anyOf: [{ type: "string", const: "x" }, nullBranch] })).properties.f;
    expect(f.enum).toEqual(["x", null]);
    expect("const" in f).toBe(false);
  });

  it("입력을 지우면 null로 돌아오고(왕복), 다시 쓰면 문자열", () => {
    const schema = wrap({ anyOf: [{ type: "string" }, nullBranch], title: "선택값" });
    const spy = vi.fn();
    render(<Controlled schema={schema} initial={{ f: "abc" }} onSpy={spy} />);
    const input = screen.getByLabelText("선택값") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "" } });
    expect(spy.mock.calls.at(-1)?.[0]).toEqual({ f: null });
    fireEvent.change(input, { target: { value: "z" } });
    expect(spy.mock.calls.at(-1)?.[0]).toEqual({ f: "z" });
  });

  it("$ref로 참조된 객체 안의 nullable도 비우면 null", () => {
    const schema = getContractSchema("WorkspaceSettings") as JsonSchema;
    const spy = vi.fn();
    render(<Controlled schema={schema} initial={getDefaultValue(schema)} onSpy={spy} />);
    fireEvent.change(screen.getByLabelText(/새 연결 기본 종류/), { target: { value: "t" } });
    fireEvent.change(screen.getByLabelText(/새 연결 기본 종류/), { target: { value: "" } });
    expect(spy.mock.calls.at(-1)?.[0]).toMatchObject({ editor: { default_edge_kind: null } });
  });
});

describe("비스칼라 nullable (object / array / $ref + null)", () => {
  const nullBranch = { type: "null" };
  const schema: JsonSchema = {
    type: "object",
    properties: {
      obj: { anyOf: [{ type: "object", properties: { a: { type: "string", title: "에이" } } }, nullBranch], default: null, title: "객체" },
      arr: { anyOf: [{ type: "array", items: { type: "string" } }, nullBranch], default: null, title: "목록" },
      ref: { anyOf: [{ $ref: "#/$defs/Inner" }, nullBranch], default: null, title: "참조" },
    },
    $defs: { Inner: { type: "object", title: "Inner", properties: { b: { type: "string", title: "비" } } } },
  };

  it("세 형태 모두 선택기(combobox) 없이 그려지고 null도 검증을 통과한다", () => {
    render(<SchemaForm schema={schema} value={{ obj: null, arr: null, ref: null }} validateOn="change" />);
    expect(screen.queryAllByRole("combobox")).toHaveLength(0);
    expect(screen.queryByText(/option 1/)).toBeNull();
    expect(screen.queryByText(/형식이어야/)).toBeNull();
    expect(screen.getByLabelText("에이")).toBeTruthy();
    expect(screen.getByLabelText("비")).toBeTruthy();
    expect(screen.getByRole("button", { name: /항목 추가/ })).toBeTruthy();
  });

  it("입력하면 객체가 생기고, 모두 지우면 null로 돌아온다(왕복)", () => {
    const spy = vi.fn();
    render(<Controlled schema={schema} initial={{ obj: null, arr: null, ref: null }} onSpy={spy} />);
    fireEvent.change(screen.getByLabelText("에이"), { target: { value: "x" } });
    expect(spy.mock.calls.at(-1)?.[0]).toMatchObject({ obj: { a: "x" } });
    fireEvent.change(screen.getByLabelText("에이"), { target: { value: "" } });
    expect(spy.mock.calls.at(-1)?.[0]).toMatchObject({ obj: null });
    fireEvent.change(screen.getByLabelText("비"), { target: { value: "y" } });
    expect(spy.mock.calls.at(-1)?.[0]).toMatchObject({ ref: { b: "y" } });
    fireEvent.change(screen.getByLabelText("비"), { target: { value: "" } });
    expect(spy.mock.calls.at(-1)?.[0]).toMatchObject({ ref: null });
  });

  it("배열: 항목을 추가하면 배열, 모두 삭제하면 null", () => {
    const spy = vi.fn();
    render(<Controlled schema={schema} initial={{ obj: null, arr: null, ref: null }} onSpy={spy} />);
    fireEvent.click(screen.getByRole("button", { name: /항목 추가/ }));
    expect(spy.mock.calls.at(-1)?.[0]).toMatchObject({ arr: [undefined] });
    fireEvent.click(screen.getByRole("button", { name: "삭제" }));
    expect(spy.mock.calls.at(-1)?.[0]).toMatchObject({ arr: null });
  });
});

describe("배열 버튼 템플릿 (glyphicon 없음)", () => {
  const schema: JsonSchema = { type: "object", properties: { tags: { type: "array", title: "태그", items: { type: "string" } } } };
  it("추가·삭제·이동 버튼은 한국어 접근성 이름과 title을 갖고 glyphicon 클래스가 없다", () => {
    const { container } = render(<SchemaForm schema={schema} value={{ tags: ["a", "b"] }} />);
    for (const name of ["항목 추가", "삭제", "위로 이동", "아래로 이동"]) {
      expect(screen.getAllByRole("button", { name }).length).toBeGreaterThan(0);
    }
    expect(screen.getAllByRole("button", { name: "삭제" })[0]?.getAttribute("title")).toBe("삭제");
    expect(container.innerHTML).not.toMatch(/glyphicon/);
  });
  it("messages로 버튼 이름을 바꿀 수 있다", () => {
    render(<SchemaForm schema={schema} value={{ tags: ["a"] }} messages={{ addItem: "Add" }} />);
    expect(screen.getByRole("button", { name: "Add" })).toBeTruthy();
  });
});

describe("값의 모양을 정하지 않는 위치는 원시 JSON 편집기", () => {
  it("additionalProperties: true 자유 객체와 스키마 없는 값도 JSON 편집기로 그린다", () => {
    const schema: JsonSchema = { type: "object", properties: { free: { type: "object", title: "자유", additionalProperties: true }, any: { title: "아무값" } } };
    const { container } = render(<SchemaForm schema={schema} value={{ free: { x: [1, { y: 2 }] }, any: [1] }} />);
    expect(container.querySelectorAll("textarea.ac-sf-raw-input")).toHaveLength(2);
    expect(container.textContent).not.toMatch(/Unsupported field schema/);
  });
});
