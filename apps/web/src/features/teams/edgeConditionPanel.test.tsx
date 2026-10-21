import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { EdgeSpec, EdgeTypeDescriptor, Graph, Issue } from "@agent-console/contracts";
import { ApiProvider } from "../../app/ApiContext";
import { createAppQueryClient } from "../../app/queries";
import { LINK_PART_IDS, LinkPartsProvider, ModulesProvider, type LinkPartDef } from "../../modules";
import { createFakeClients } from "../../testing/fakes";
import { agents, nodeTypes, sampleGraph } from "../../testing/teamFixtures";
import { EdgePanel } from "./EdgePanel";
import type { TeamPanelContext } from "./panelContext";

// 연동 부분 등록 데이터(앱 조립 층 `links/`는 기능 폴더가 import하지 않는다): 연산자 목록은 실행 역할이 있을 때만
const PARTS: readonly LinkPartDef[] = [{ id: LINK_PART_IDS.teamsConditionOperators, requires: ["runs"], onMissing: "hide" }];

afterEach(cleanup);

// 임의 이름의 연결 종류. 조건 위젯 이름만 앱 레지스트리에 등록된 이름을 쓴다(서버 ui_schema가 정하는 데이터).
const conditionSchema = {
  type: "object",
  properties: { rules: { anyOf: [{ $ref: "#/$defs/Spec" }, { type: "null" }], default: null, title: "규칙" }, odd: { anyOf: [{ $ref: "#/$defs/Spec" }, { type: "null" }], default: null, title: "이상한 위젯" } },
  $defs: {
    Spec: { type: "object", properties: { all: { anyOf: [{ type: "array", items: { $ref: "#/$defs/Item" } }, { type: "null" }] }, any: { anyOf: [{ type: "array", items: { $ref: "#/$defs/Item" } }, { type: "null" }] }, negate: { anyOf: [{ type: "boolean" }, { type: "null" }] } } },
    Item: { type: "object", properties: { path: { type: "string", examples: ["/p1", "/p2"] }, op: { type: "string" }, value: {} }, required: ["path", "op"] },
  },
};
const kindCond = { id: "k-cond", title: "조건 종류", scheduling: "flow", config_schema: conditionSchema, ui_schema: { rules: { "ui:widget": "condition-list", "ui:options": { path_titles: { "/p1": "첫째" } } }, odd: { "ui:widget": "not-registered" } } } as unknown as EdgeTypeDescriptor;
const kindLoop = { id: "k-loop", title: "반복 종류", scheduling: "flow", cycle: { max_iterations: 3, title: "반복" }, config_schema: { type: "object", properties: { cap: { type: "integer" } } } } as unknown as EdgeTypeDescriptor;

const edgeOf = (kind: string, config?: Record<string, unknown>): EdgeSpec => ({ id: "ex", kind, source: { node: "h1", port: "says" }, target: { node: "a1", port: "i1" }, ...(config ? { config } : {}) }) as EdgeSpec;

function Harness({ edge, kinds = [kindCond, kindLoop], issues = [], clients }: { edge: EdgeSpec; kinds?: EdgeTypeDescriptor[]; issues?: Issue[]; clients: ReturnType<typeof createFakeClients>["clients"] }) {
  const [graph, setGraph] = useState<Graph>({ ...sampleGraph(), edges: [edge] } as Graph);
  const current = (graph.edges ?? [])[0]!;
  const ctx: TeamPanelContext = {
    graphId: "tm1",
    graph,
    savedNodeIds: new Set(),
    savedVersion: "h1",
    dirty: false,
    nodeTypes,
    edgeTypes: kinds,
    agents,
    resources: [],
    resourceTypes: [],
    interactionKinds: [],
    strategies: [],
    workspace: undefined,
    issues,
    plan: { data: undefined, isLoading: false, isError: false, isDraft: false, updating: false, error: null, refetch: () => {} } as never,
    disabled: false,
    onGraphChange: setGraph,
    onUndoableChange: setGraph,
    onApplySuggestion: () => {},
    onPreviewBundle: () => {},
    navigateTo: () => {},
  };
  return (
    <ApiProvider clients={clients}>
      <ModulesProvider>
        <LinkPartsProvider parts={PARTS}>
          <EdgePanel ctx={ctx} edge={current} />
          <pre data-testid="cfg">{JSON.stringify(current.config ?? null)}</pre>
        </LinkPartsProvider>
      </ModulesProvider>
    </ApiProvider>
  );
}

const operators = [
  { id: "op-a", title: "포함", description: "문자열 포함", value_schema: { type: "string" } },
  { id: "op-b", title: "있음", value_schema: { not: {} } },
];

function mount(edge: EdgeSpec, over: Record<string, unknown> = {}, issues: Issue[] = []) {
  const { clients, rest } = createFakeClients({ listConditionOperators: vi.fn(async () => operators), ...over });
  const queryClient = createAppQueryClient({ retry: false });
  render(
    <QueryClientProvider client={queryClient}>
      <Harness edge={edge} clients={clients} issues={issues} />
    </QueryClientProvider>,
  );
  return { rest };
}
const cfg = () => JSON.parse(screen.getByTestId("cfg").textContent ?? "null") as Record<string, unknown> | null;

describe("연결 패널: 조건 목록 위젯(ui:widget 이름 → 레지스트리)", () => {
  it("서버 ui_schema의 위젯 이름으로 조건 목록을 그리고, 연산자는 서버 목록에서 온다", async () => {
    const { rest } = mount(edgeOf("k-cond", { rules: { all: [{ path: "/p1", op: "op-a", value: "x" }] } }));
    const group = await screen.findByRole("group", { name: "규칙" });
    await waitFor(() => expect((within(group).getByLabelText("연산자") as HTMLElement).tagName).toBe("SELECT"));
    expect(rest.listConditionOperators).toHaveBeenCalledTimes(1);
    expect(within(group).getByRole("option", { name: "포함" })).toBeTruthy();
    // 경로 제안은 스키마 examples
    expect(Array.from(group.querySelectorAll("datalist option")).map((o) => o.getAttribute("value"))).toEqual(["/p1", "/p2"]);
    expect(group.closest("[data-edge-config]")).not.toBeNull();
  });

  it("편집하면 연결 config의 해당 키에 희소하게 저장된다", async () => {
    mount(edgeOf("k-cond"));
    const group = await screen.findByRole("group", { name: "규칙" });
    fireEvent.click(within(group).getByRole("button", { name: /조건 추가/ }));
    await waitFor(() => expect(cfg()).toEqual({ rules: { all: [{ path: "", op: "" }] } }));
    fireEvent.change(within(group).getByLabelText("대상"), { target: { value: "/p2" } });
    await waitFor(() => expect(cfg()).toEqual({ rules: { all: [{ path: "/p2", op: "" }] } }));
  });

  it("서버 이슈(경로가 조건 값을 가리킴)는 해당 행 아래에 매달린다", async () => {
    mount(edgeOf("k-cond", { rules: { all: [{ path: "/p1", op: "op-a", value: 3 }] } }), {}, [
      { severity: "error", code: "condition.invalid_value", message: "값 형식이 맞지 않습니다", edge_id: "ex", path: "/edges/0/config/rules/all/0/value" } as Issue,
    ]);
    const group = await screen.findByRole("group", { name: "규칙" });
    const row = within(group).getByRole("group", { name: "조건 1/1" });
    expect(within(row).getByText("값 형식이 맞지 않습니다")).toBeTruthy();
  });

  it("레지스트리에 없는 위젯 이름이 객체 필드에 지정되면 JSON으로 표시하고 안내한다", async () => {
    mount(edgeOf("k-cond", { odd: { any: [] } }));
    expect(await screen.findByText("이 설정을 그리는 위젯을 찾지 못해 JSON으로 표시합니다.")).toBeTruthy();
    expect(screen.getByText(/"any": \[\]/)).toBeTruthy();
  });

  it("연산자 목록 요청이 실패하면 자유 입력으로 폴백하고 입력은 그대로 보존한다", async () => {
    mount(edgeOf("k-cond", { rules: { all: [{ path: "/p1", op: "typed", value: "v" }] } }), { listConditionOperators: vi.fn(async () => { throw new Error("boom"); }) });
    const group = await screen.findByRole("group", { name: "규칙" });
    await waitFor(() => expect(within(group).getByText(/불러오지 못해 직접 입력합니다/)).toBeTruthy());
    expect((within(group).getByLabelText("연산자") as HTMLInputElement).value).toBe("typed");
  });
});

describe("연결 패널: 반복 연결 속성(cycle)", () => {
  it("반복 태그와 유효 최대 반복(출처: 연결 종류 기본)을 읽기 전용 줄로 보인다", async () => {
    mount(edgeOf("k-loop"));
    expect(await screen.findByText("반복", { selector: ".ac-tag" })).toBeTruthy();
    expect(screen.getByText("이 연결의 최대 반복: 3회 · 출처: 연결 종류 기본")).toBeTruthy();
  });
  it("연결 config의 한도가 있으면 출처가 연결이다", async () => {
    mount(edgeOf("k-loop", { max_iterations: 5 }));
    expect(await screen.findByText("이 연결의 최대 반복: 5회 · 출처: 연결")).toBeTruthy();
  });
});
