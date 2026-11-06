import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KNOWN_UI_WIDGETS } from "@agent-console/contracts/constants";
import { getContractSchema } from "@agent-console/contracts";
import { SchemaForm } from "@agent-console/schema-form";
import { ConfigIssuesProvider, type ConfigIssue } from "../delegation";
import { WIDGET_REF_SOURCES } from "./sddConfig";
import { SDD_WIDGET_FIELDS } from "./widgets/fields";
import { SddWidgetEnvProvider, type SddWidgetEnv } from "./widgets/SddWidgetEnv";
import { widgetUiSchema } from "./widgets/widgetUi";
import type { SchemaNode } from "../../lib/schemaTools";

vi.mock("../delegation/ConditionListField", async (orig) => ({
  ...(await orig<object>()),
  ConditionListField: (p: { options: Record<string, unknown>; label: string }) => <div data-testid="cond" data-pointer={String(p.options["$pointer"])}>{p.label}</div>,
}));

afterEach(cleanup);

const NAMES = new Set(Object.keys(SDD_WIDGET_FIELDS));
const W = KNOWN_UI_WIDGETS;
const EMPTY: SddWidgetEnv = { refs: {}, variables: [] };

/** 임의 필드 이름의 가짜 스키마: 위젯 이름만 `x-ui.widget`으로 달린다. */
function schemaWith(widget: string, field: SchemaNode, extra: SchemaNode = {}): SchemaNode {
  return { type: "object", properties: { zz: { ...field, title: "필드", "x-ui": { widget } } }, ...extra };
}

function Host({ schema, initial, env = EMPTY, issues = [], readonly }: { schema: SchemaNode; initial?: unknown; env?: SddWidgetEnv; issues?: ConfigIssue[]; readonly?: boolean }) {
  const [value, setValue] = useState<unknown>(initial ?? {});
  return (
    <SddWidgetEnvProvider env={env}>
      <ConfigIssuesProvider issues={issues}>
        <SchemaForm schema={schema} uiSchema={widgetUiSchema(schema, NAMES)} customFields={SDD_WIDGET_FIELDS} value={value} onChange={setValue} errors={issues} rawJsonToggle={false} readonly={readonly} idPrefix="t" />
      </ConfigIssuesProvider>
      <pre data-testid="out">{JSON.stringify(value)}</pre>
    </SddWidgetEnvProvider>
  );
}
const out = () => JSON.parse(screen.getByTestId("out").textContent ?? "null") as Record<string, unknown>;

describe("위젯 등록: 계약 상수", () => {
  it("등록된 위젯 이름은 모두 계약 KNOWN_UI_WIDGETS에 있고 8종이 빠짐없이 있다", () => {
    const known = new Set(Object.values(W));
    for (const name of NAMES) expect(known.has(name as never)).toBe(true);
    for (const name of [W.CONDITION, W.REGEX, W.TEMPLATE_TEXT, W.GRAPH_REF, W.PROFILE_REF, W.STATE_REF, W.STATUS_REF, W.TONE]) expect(NAMES.has(name)).toBe(true);
  });
  it("값 목록 위치 표의 키는 계약 위젯 상수 이름이다", () => {
    for (const key of Object.keys(WIDGET_REF_SOURCES)) expect(key in W).toBe(true);
  });
  it("실제 계약 스키마의 x-ui.widget 중 등록된 이름만 ui:field가 되고 모르는 이름은 건드리지 않는다", () => {
    const root = getContractSchema("SpecDefinition") as SchemaNode;
    const fieldsOf = (ui: unknown): string[] => {
      const found: string[] = [];
      const walk = (n: unknown) => {
        if (typeof n !== "object" || n === null) return;
        for (const [k, v] of Object.entries(n)) {
          if (k === "ui:field") found.push(String(v));
          else if (k !== "ui:options") walk(v);
        }
      };
      walk(ui);
      return found;
    };
    const all = new Set(fieldsOf(widgetUiSchema(root, NAMES)));
    for (const name of [W.CONDITION, W.REGEX, W.TEMPLATE_TEXT, W.GRAPH_REF, W.STATE_REF, W.STATUS_REF, W.TONE, W.PROFILE_REF]) expect(all.has(name)).toBe(true);
    expect([...new Set(fieldsOf(widgetUiSchema(root, new Set([W.REGEX]))))]).toEqual([W.REGEX]);
    expect(Object.keys(widgetUiSchema({ type: "object", properties: { a: { type: "string", "x-ui": { widget: "future-widget" } } } }, NAMES))).toEqual([]);
  });
});

describe("모르는 위젯 이름", () => {
  it("스키마 타입 기본 위젯으로 그려진다", () => {
    render(<Host schema={schemaWith("future-widget", { type: "string" })} />);
    fireEvent.change(screen.getByLabelText("필드"), { target: { value: "값" } });
    expect(out()).toEqual({ zz: "값" });
  });
});

describe("regex 위젯", () => {
  it("문자열 하나를 입력하고, 비우면 null이며, 서버 이슈를 칸 아래에 보인다", () => {
    render(<Host schema={schemaWith(W.REGEX, { type: ["string", "null"] })} issues={[{ path: "/zz", message: "닫히지 않은 괄호", severity: "error" }]} />);
    const input = screen.getByLabelText("필드");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText("닫히지 않은 괄호")).toBeTruthy();
    fireEvent.change(input, { target: { value: "^a(" } });
    expect(out()).toEqual({ zz: "^a(" });
    fireEvent.change(input, { target: { value: "" } });
    expect(out()).toEqual({ zz: null });
  });
  it("목록이면 항목마다 칸이 있고 이슈는 해당 항목 아래에 붙는다", () => {
    render(<Host schema={schemaWith(W.REGEX, { type: "array", items: { type: "string" } })} initial={{ zz: ["a", "b"] }} issues={[{ path: "/zz/1", message: "두번째 문제", severity: "error" }]} />);
    const second = screen.getByLabelText("필드 2");
    expect(second.getAttribute("aria-invalid")).toBe("true");
    expect(within(second.closest(".sdd-w-row") as HTMLElement).getByText("두번째 문제")).toBeTruthy();
    expect(screen.getByLabelText("필드 1").getAttribute("aria-invalid")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "추가" }));
    expect(out()["zz"]).toEqual(["a", "b", ""]);
    fireEvent.click(screen.getByRole("button", { name: "필드 1 삭제" }));
    expect(out()["zz"]).toEqual(["b", ""]);
  });
  it("읽기 전용이면 입력이 잠긴다", () => {
    render(<Host schema={schemaWith(W.REGEX, { type: "string" })} initial={{ zz: "x" }} readonly />);
    expect((screen.getByLabelText("필드") as HTMLInputElement).disabled).toBe(true);
  });
});

describe("template-text 위젯", () => {
  const env: SddWidgetEnv = { refs: {}, variables: ["x_var", "y_var"] };
  it("변수 칩을 누르면 커서 위치에 {이름}이 들어간다", () => {
    render(<Host schema={schemaWith(W.TEMPLATE_TEXT, { type: "object", additionalProperties: { type: "string" } })} initial={{ zz: { request: "작업 " } }} env={env} />);
    const area = screen.getByLabelText("필드 request") as HTMLTextAreaElement;
    area.focus();
    area.setSelectionRange(3, 3);
    fireEvent.click(screen.getByRole("button", { name: "{x_var} 넣기" }));
    expect(out()["zz"]).toEqual({ request: "작업 {x_var}" });
    expect(screen.getByRole("group", { name: "쓸 수 있는 변수" })).toBeTruthy();
  });
  it("항목을 추가·삭제하고 이름이 겹치면 추가할 수 없다", () => {
    render(<Host schema={schemaWith(W.TEMPLATE_TEXT, { type: "object", additionalProperties: { type: "string" } })} initial={{ zz: { a: "1" } }} env={env} />);
    const key = screen.getByLabelText("새 항목 이름");
    fireEvent.change(key, { target: { value: "a" } });
    expect((screen.getByRole("button", { name: "항목 추가" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(key, { target: { value: "b" } });
    fireEvent.click(screen.getByRole("button", { name: "항목 추가" }));
    expect(out()["zz"]).toEqual({ a: "1", b: "" });
    fireEvent.click(screen.getByRole("button", { name: "a 삭제" }));
    expect(out()["zz"]).toEqual({ b: "" });
  });
  it("서버가 준 모르는 변수 경고가 칸 아래에 보인다", () => {
    render(<Host schema={schemaWith(W.TEMPLATE_TEXT, { type: "object", additionalProperties: { type: "string" } })} initial={{ zz: { request: "{q}" } }} env={env} issues={[{ path: "/zz/request", message: "알 수 없는 변수 q", severity: "warning" }]} />);
    expect(screen.getByText("알 수 없는 변수 q")).toBeTruthy();
  });
});

describe("값 고르기 위젯 4종 (graph-ref·profile-ref·state-ref·status-ref)", () => {
  const env: SddWidgetEnv = {
    refs: { [W.GRAPH_REF]: [{ id: "t-1", label: "팀 하나" }], [W.PROFILE_REF]: [{ id: "p-1" }], [W.STATE_REF]: [{ id: "s-a" }, { id: "s-b" }], [W.STATUS_REF]: [{ id: "k-1" }] },
    variables: [],
  };
  it.each([W.GRAPH_REF, W.PROFILE_REF, W.STATE_REF, W.STATUS_REF])("%s: 목록 값을 고르거나 직접 입력하고 목록에 없으면 경고한다", (name) => {
    render(<Host schema={schemaWith(name, { type: ["string", "null"] })} env={env} />);
    const input = screen.getByLabelText("필드") as HTMLInputElement;
    const list = document.getElementById(input.getAttribute("list") ?? "");
    expect(list?.querySelectorAll("option").length).toBe((env.refs[name] ?? []).length);
    const first = env.refs[name]?.[0]?.id ?? "";
    fireEvent.change(input, { target: { value: first } });
    expect(out()).toEqual({ zz: first });
    expect(screen.queryByTestId("sdd-w-missing")).toBeNull();
    fireEvent.change(input, { target: { value: "없는-값" } });
    expect(out()).toEqual({ zz: "없는-값" });
    expect(screen.getByTestId("sdd-w-missing").textContent).toContain("없는-값");
  });
  it("graph-ref 경고는 실행할 때 가져온다는 안내 문구다", () => {
    render(<Host schema={schemaWith(W.GRAPH_REF, { type: "string" })} initial={{ zz: "t-x" }} env={env} />);
    expect(screen.getByTestId("sdd-w-missing").textContent).toBe("이 프로젝트에 ‘t-x’ 팀 구성이 없습니다 — 실행할 때 가져와서 실행합니다");
  });
  it("목록을 모르면(null) 경고 없이 직접 입력만 된다", () => {
    render(<Host schema={schemaWith(W.GRAPH_REF, { type: "string" })} initial={{ zz: "t-x" }} env={{ refs: { [W.GRAPH_REF]: null }, variables: [] }} />);
    expect(screen.queryByTestId("sdd-w-missing")).toBeNull();
    expect(screen.getByLabelText("필드").getAttribute("list")).toBeNull();
  });
  it("status-ref 표 모양: 실행 상태 이름 → 작업 상태 id", () => {
    render(<Host schema={schemaWith(W.STATUS_REF, { type: "object", additionalProperties: { type: "string" } })} initial={{ zz: { done: "k-1" } }} env={env} />);
    fireEvent.change(screen.getByLabelText("필드 done"), { target: { value: "k-2" } });
    expect(out()["zz"]).toEqual({ done: "k-2" });
  });
  it("서버 이슈가 이미 있으면 같은 내용의 경고를 따로 만들지 않는다", () => {
    render(<Host schema={schemaWith(W.STATE_REF, { type: "string" })} initial={{ zz: "s-x" }} env={env} issues={[{ path: "/zz", message: "서버 경고", severity: "warning" }]} />);
    expect(screen.queryByTestId("sdd-w-missing")).toBeNull();
    expect(screen.getByText("서버 경고")).toBeTruthy();
  });
});

describe("tone 위젯", () => {
  it("제안 칩을 고르면 값이 되고 다시 누르면 비며 직접 입력도 된다", () => {
    render(<Host schema={schemaWith(W.TONE, { type: ["string", "null"] })} />);
    const group = screen.getByRole("group", { name: "색조" });
    const success = within(group).getByRole("button", { name: "성공" });
    fireEvent.click(success);
    expect(out()).toEqual({ zz: "success" });
    expect(success.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(success);
    expect(out()).toEqual({ zz: null });
    fireEvent.change(screen.getByLabelText("직접 입력"), { target: { value: "x-custom" } });
    expect(out()).toEqual({ zz: "x-custom" });
  });
});

describe("condition 위젯", () => {
  it("조건 편집 부품에 폼이 알려 준 위치(배열 인덱스 포함)를 넘긴다", () => {
    const schema: SchemaNode = { type: "object", properties: { list: { type: "array", items: { type: "object", properties: { req: { type: "object", title: "조건", "x-ui": { widget: W.CONDITION } } } } } } };
    render(<Host schema={schema} initial={{ list: [{ req: {} }, { req: {} }] }} />);
    const pointers = screen.getAllByTestId("cond").map((e) => e.getAttribute("data-pointer"));
    expect(pointers).toEqual(["/list/0/req", "/list/1/req"]);
  });
});
