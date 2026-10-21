import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConditionList, type OperatorsState } from "./ConditionList";
import type { ConditionOperatorDescriptor, ConditionSpec } from "./conditions";

afterEach(cleanup);

// 임의의 가짜 연산자 5종: 값 모양(문자열·숫자·불리언·배열·객체)과 값 없음을 각각 대표한다.
const ops: ConditionOperatorDescriptor[] = [
  { id: "x-str", title: "문자열형", description: "문자열을 받음", value_schema: { type: "string" } },
  { id: "x-num", title: "숫자형", value_schema: { type: "integer" } },
  { id: "x-bool", title: "불리언형", value_schema: { type: "boolean" } },
  { id: "x-arr", title: "배열형", value_schema: { type: "array", items: { type: "string" } } },
  { id: "x-obj", title: "객체형", value_schema: { type: "object" } },
  { id: "x-none", title: "값없음형", value_schema: { not: {} } },
  { id: "x-free", title: "자유형", value_schema: {} },
];

function Host({ initial, operators = ops, state = "ready", onRetry, errors, pathSuggestions }: { initial?: ConditionSpec | undefined; operators?: ConditionOperatorDescriptor[] | null; state?: OperatorsState; onRetry?: () => void; errors?: { path: string; message: string }[]; pathSuggestions?: { value: string; title?: string }[] }) {
  const [value, setValue] = useState<ConditionSpec | undefined>(initial);
  return (
    <>
      <ConditionList value={value} onChange={setValue} operators={operators} operatorsState={state} onRetryOperators={onRetry} errors={errors} pathSuggestions={pathSuggestions} idPrefix="t" />
      <pre data-testid="out">{JSON.stringify(value ?? null)}</pre>
    </>
  );
}
const out = () => JSON.parse(screen.getByTestId("out").textContent ?? "null") as ConditionSpec | null;

describe("ConditionList: 연산자 목록이 있을 때", () => {
  it("행을 추가하면 연산자는 비워 두고, 모드 전환은 항목을 그대로 둔 채 키만 옮긴다", () => {
    render(<Host />);
    fireEvent.click(screen.getByRole("button", { name: /조건 추가/ }));
    expect(out()).toEqual({ all: [{ path: "", op: "" }] });
    fireEvent.click(screen.getByRole("radio", { name: "하나라도 만족" }));
    expect(out()).toEqual({ any: [{ path: "", op: "" }] });
    fireEvent.click(screen.getByLabelText("결과 뒤집기"));
    expect(out()?.negate).toBe(true);
    fireEvent.click(screen.getByLabelText("결과 뒤집기"));
    expect(out()).toEqual({ any: [{ path: "", op: "" }] });
  });

  it("연산자 value_schema에 맞춰 값 입력 모양이 정해진다(문자열·숫자·불리언·배열·객체·값 없음)", () => {
    render(<Host initial={{ all: [{ path: "/a", op: "x-str", value: "p" }] }} />);
    const select = screen.getByLabelText("연산자") as HTMLSelectElement;
    const pick = (id: string) => fireEvent.change(select, { target: { value: id } });
    expect((screen.getByLabelText("값") as HTMLInputElement).type).toBe("text");
    pick("x-num");
    expect((screen.getByLabelText("값") as HTMLInputElement).type).toBe("number");
    fireEvent.change(screen.getByLabelText("값"), { target: { value: "7" } });
    expect(out()?.all?.[0]).toMatchObject({ op: "x-num", value: 7 });
    pick("x-bool");
    expect((screen.getByLabelText("값") as HTMLInputElement).type).toBe("checkbox");
    fireEvent.click(screen.getByLabelText("값"));
    expect(out()?.all?.[0]?.value).toBe(true);
    pick("x-arr");
    const chips = screen.getByRole("group", { name: "값" });
    const input = within(chips).getByRole("textbox");
    fireEvent.change(input, { target: { value: "aa" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(out()?.all?.[0]?.value).toEqual(["aa"]);
    pick("x-obj");
    fireEvent.change(screen.getByLabelText("값"), { target: { value: '{"k":1}' } });
    expect(out()?.all?.[0]?.value).toEqual({ k: 1 });
    pick("x-none");
    expect((screen.getByLabelText("값") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText("값이 필요 없는 연산자입니다", { selector: "span" })).toBeTruthy();
    expect(out()?.all?.[0]?.value).toBeUndefined();
  });

  it("값 스키마가 비어 있으면 형식 선택이 붙는다", () => {
    render(<Host initial={{ all: [{ path: "/a", op: "x-free", value: "p" }] }} />);
    const kind = screen.getByLabelText("값 — 값 형식") as HTMLSelectElement;
    expect(kind.value).toBe("string");
    fireEvent.change(kind, { target: { value: "boolean" } });
    expect(out()?.all?.[0]?.value).toBe(false);
  });

  it("모르는 연산자는 알 수 없음으로 값과 함께 보존되고 경고한다", () => {
    render(<Host initial={{ all: [{ path: "/a", op: "gone-op", value: "keep" }] }} />);
    const select = screen.getByLabelText("연산자") as HTMLSelectElement;
    expect(select.value).toBe("gone-op");
    expect(within(select).getByText("알 수 없음: gone-op")).toBeTruthy();
    expect(select.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByRole("alert", { name: "" }).textContent).toContain("gone-op");
    expect(out()?.all?.[0]).toEqual({ path: "/a", op: "gone-op", value: "keep" });
  });

  it("경로가 /로 시작하지 않으면 인라인 오류", () => {
    render(<Host initial={{ all: [{ path: "output", op: "x-str" }] }} />);
    expect(screen.getByText("경로는 /로 시작해야 합니다(예: /output)")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("대상"), { target: { value: "/output" } });
    expect(screen.queryByText("경로는 /로 시작해야 합니다(예: /output)")).toBeNull();
  });

  it("요약 줄: 항목이 없으면 항상 통과 경고, 있으면 전문", () => {
    const { rerender } = render(<Host initial={{ all: [] }} />);
    expect(screen.getByText("조건이 비어 있어 항상 통과합니다.")).toBeTruthy();
    rerender(<Host key="filled" initial={{ all: [{ path: "/a", op: "x-str", value: "v" }] }} />);
    expect(screen.queryByText("조건이 비어 있어 항상 통과합니다.")).toBeNull();
  });

  it("서버 이슈는 해당 행 값·연산자 아래에 붙는다", () => {
    render(<Host initial={{ all: [{ path: "/a", op: "x-str", value: "p" }, { path: "/b", op: "x-num", value: 1 }] }} errors={[{ path: "/all/1/value", message: "값 형식 오류" }, { path: "/all/0/op", message: "연산자 경고" }]} />);
    const rows = screen.getAllByRole("group", { name: /조건 \d\/2/ });
    expect(within(rows[1]!).getByText("값 형식 오류")).toBeTruthy();
    expect(within(rows[0]!).getByText(/연산자 경고/)).toBeTruthy();
  });

  it("경로 제안은 스키마 examples(제목 포함)에서 온다", () => {
    render(<Host initial={{ all: [{ path: "", op: "x-str" }] }} pathSuggestions={[{ value: "/q1", title: "제목1" }, { value: "/q2" }]} />);
    const list = document.querySelector("datalist");
    expect(Array.from(list?.querySelectorAll("option") ?? []).map((o) => o.getAttribute("value"))).toEqual(["/q1", "/q2"]);
  });

  it("행 키보드: Delete 삭제, Insert 아래에 새 행, Alt+↑↓ 이동, Enter는 아무 동작도 하지 않는다", () => {
    render(<Host initial={{ all: [{ path: "/1", op: "x-str" }, { path: "/2", op: "x-str" }] }} />);
    const row = (n: number) => screen.getAllByRole("group", { name: /조건 \d\/\d/ })[n]!;
    const submit = vi.fn();
    row(0).closest("form")?.addEventListener("submit", submit);
    fireEvent.keyDown(row(0), { key: "Enter" });
    expect(out()?.all).toHaveLength(2);
    fireEvent.keyDown(row(0), { key: "ArrowDown", altKey: true });
    expect(out()?.all?.map((i) => i.path)).toEqual(["/2", "/1"]);
    fireEvent.keyDown(row(1), { key: "ArrowUp", altKey: true });
    expect(out()?.all?.map((i) => i.path)).toEqual(["/1", "/2"]);
    fireEvent.keyDown(row(0), { key: "Insert" });
    expect(out()?.all).toHaveLength(3);
    expect(out()?.all?.[1]).toEqual({ path: "", op: "" });
    fireEvent.keyDown(row(1), { key: "Delete" });
    expect(out()?.all?.map((i) => i.path)).toEqual(["/1", "/2"]);
  });

  it("입력 칸 안에서는 행 단축키가 동작하지 않고, 한글 조합 중에는 모든 단축키가 멈춘다", () => {
    render(<Host initial={{ all: [{ path: "/1", op: "x-str" }] }} />);
    const input = screen.getByLabelText("대상");
    fireEvent.keyDown(input, { key: "Delete" });
    expect(out()?.all).toHaveLength(1);
    const row = screen.getByRole("group", { name: "조건 1/1" });
    fireEvent.keyDown(row, { key: "Delete", isComposing: true });
    fireEvent.keyDown(row, { key: "Delete", keyCode: 229 });
    expect(out()?.all).toHaveLength(1);
    fireEvent.keyDown(row, { key: "Delete" });
    expect(out()?.all ?? []).toHaveLength(0);
  });

  it("조합 중 Enter는 칩을 추가하지 않는다", () => {
    render(<Host initial={{ all: [{ path: "/1", op: "x-arr" }] }} />);
    const input = within(screen.getByRole("group", { name: "값" })).getByRole("textbox");
    fireEvent.compositionStart(input);
    fireEvent.change(input, { target: { value: "한" } });
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    expect(out()?.all?.[0]?.value).toBeUndefined();
    fireEvent.compositionEnd(input);
  });
});

describe("ConditionList: 연산자 목록 3상태", () => {
  const initial: ConditionSpec = { all: [{ path: "/a", op: "typed-op", value: "v" }] };
  it("로딩: 연산자 칸은 스켈레톤, 다른 칸은 입력할 수 있다", () => {
    render(<Host initial={initial} operators={null} state="loading" />);
    expect(screen.getByRole("status", { name: "연산자 목록을 불러오는 중" })).toBeTruthy();
    expect((screen.getByLabelText("대상") as HTMLInputElement).disabled).toBe(false);
  });
  it("오류: 자유 입력으로 폴백하고 안내 줄과 [다시 시도], 입력 내용은 보존", () => {
    const retry = vi.fn();
    render(<Host initial={initial} operators={null} state="error" onRetry={retry} />);
    const op = screen.getByLabelText("연산자") as HTMLInputElement;
    expect(op.tagName).toBe("INPUT");
    expect(op.value).toBe("typed-op");
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(retry).toHaveBeenCalled();
    fireEvent.change(op, { target: { value: "other-op" } });
    expect(out()?.all?.[0]).toMatchObject({ op: "other-op", value: "v" });
  });
  it("없음(연동 꺼짐): 자유 입력만 있고 안내 줄도 [다시 시도]도 없다", () => {
    render(<Host initial={initial} operators={null} state="absent" />);
    expect((screen.getByLabelText("연산자") as HTMLInputElement).tagName).toBe("INPUT");
    expect(screen.queryByText(/불러오지 못해/)).toBeNull();
    expect(screen.queryByRole("button", { name: "다시 시도" })).toBeNull();
  });
});

describe("ConditionList: all+any 동시 데이터", () => {
  const both = { all: [{ path: "/a", op: "x-str" }], any: [{ path: "/b", op: "x-str" }] } as ConditionSpec;
  it("폼으로 그리지 않고 JSON 편집만 열어 두며 데이터는 바뀌지 않는다", () => {
    render(<Host initial={both} />);
    expect(screen.getByText(/함께 있는 조건은 폼으로 편집할 수 없습니다/)).toBeTruthy();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(out()).toEqual(both);
    fireEvent.click(screen.getByRole("button", { name: "JSON으로 편집" }));
    const area = screen.getByLabelText("조건 JSON");
    fireEvent.change(area, { target: { value: "{" } });
    expect(screen.getByText("JSON 형식이 올바르지 않습니다")).toBeTruthy();
    expect(out()).toEqual(both);
    fireEvent.change(area, { target: { value: '{"all":[]}' } });
    expect(out()).toEqual({ all: [] });
  });
});

describe("ConditionList: 행이 많을 때", () => {
  it("20행을 넘으면 안내를 보이되 막지 않는다", () => {
    const many = { all: Array.from({ length: 21 }, (_, i) => ({ path: `/${i}`, op: "x-str" })) };
    render(<Host initial={many} />);
    expect(screen.getByText(/조건이 많습니다/)).toBeTruthy();
    expect((screen.getByRole("button", { name: /조건 추가/ }) as HTMLButtonElement).disabled).toBe(false);
  });
});
