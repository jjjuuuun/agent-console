import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Graph, NodeTypeDescriptor } from "@agent-console/contracts";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { agents, edgeTypes, nodeTypes, resourceTypes, sampleGraph } from "../../testing/teamFixtures";
import { DEFINITION_KINDS } from "../library";

// 화면 조각을 lazy 로딩하므로 부하에서 1초 기본 대기로는 흔들린다(5.2R.9)
configure({ asyncUtilTimeout: 10_000 });

afterEach(cleanup);

// 중첩 노드 = binds.kind가 지금 편집 중인 정의 종류(팀 구성)와 같은 노드. 노드 타입 id·이름은 임의 값이다.
const nestedType = {
  id: "t-inner",
  version: 1,
  title: "내포 노드",
  role: "r-inner",
  executable: true,
  binds: { kind: DEFINITION_KINDS.graph, field: "pick" },
  ui_hints: { shape: "stacked" },
  config_schema: { type: "object", properties: { pick: { type: "string" }, version: { anyOf: [{ type: "string" }, { type: "null" }], default: null, title: "고정" }, over: { anyOf: [{ type: "object", properties: { k: { type: "string", title: "덮는 값" } } }, { type: "null" }], default: null, title: "덮어쓰기" } } },
  static_ports: { inputs: [{ name: "i1" }], outputs: [{ name: "o1" }] },
} as unknown as NodeTypeDescriptor;

const summary = (id: string, name: string) => ({ id, name, labels: [], version_hash: `h-${id}`, saved_at: 1, node_count: 5, edge_count: 4, entry_labels: ["입구"] });

function graphWith(pick: string, pin?: string): Graph {
  const g = sampleGraph();
  return { ...g, nodes: [...(g.nodes ?? []), { id: "in1", type: "t-inner", label: "검토 파이프라인", config: { pick, ...(pin ? { version: pin } : {}) }, position: { x: 100, y: 200 } }] } as Graph;
}

function clientsFor(graphs: Record<string, Graph>, extra: Record<string, unknown> = {}) {
  return createFakeClients({
    listNodeTypes: vi.fn(async () => [...nodeTypes, nestedType]),
    listEdgeTypes: vi.fn(async () => edgeTypes),
    listResourceTypes: vi.fn(async () => resourceTypes),
    listAgents: vi.fn(async () => agents),
    listInteractionKinds: vi.fn(async () => []),
    listDelegationStrategies: vi.fn(async () => []),
    listRuns: vi.fn(async () => []),
    listConversations: vi.fn(async () => []),
    resolvePorts: vi.fn(async () => ({ inputs: [], outputs: [] })),
    listGraphs: vi.fn(async () => Object.values(graphs).map((g) => summary(g.id, g.name))),
    getGraph: vi.fn(async (id: string) => ({ graph: graphs[id], version_hash: `h-${id}`, saved_at: 1 })),
    validateGraph: vi.fn(async () => []),
    updateGraph: vi.fn(async (_id: string, g: unknown) => ({ graph: g, version_hash: "h2" })),
    getGraphPlan: vi.fn(async () => ({ entries: [{ edge_id: "x1", node_id: "a1" }], answers: [], grants: {} })),
    planDraftGraph: vi.fn(async () => ({ entries: [{ edge_id: "x1", node_id: "a1" }], answers: [], grants: {} })),
    getNodeEffectiveSettings: vi.fn(async () => ({ value: {}, provenance: {}, layers: [] })),
    listResources: vi.fn(async () => []),
    ...extra,
  });
}

const child = (): Graph => ({ ...sampleGraph(), id: "tm2", name: "둘째 팀" }) as Graph;

describe("중첩 노드 카드·열기·돌아오기", () => {
  it("중첩 노드 카드에 정의 이름·노드 수·버전 고정 배지가 보이고 [열기]가 부모 정보를 싣고 자식 편집기를 연다", async () => {
    const { clients } = clientsFor({ tm1: graphWith("tm2", "3fa9c1b2deadbeef"), tm2: child() });
    mountApp(clients, "/teams/tm1");
    const card = await screen.findByLabelText(/^노드 검토 파이프라인/);
    expect(within(card).getByText("노드 5개 · 입구 1")).toBeTruthy();
    expect(within(card).getByText("고정 3fa9c1b")).toBeTruthy();
    fireEvent.click(within(card).getByRole("button", { name: "열기" }));
    // 자식 편집기: 브레드크럼이 부모를 이어 보인다
    const crumbs = await screen.findByRole("navigation", { name: "위치" });
    expect(within(crumbs).getByRole("link", { name: "임의 팀" })).toBeTruthy();
    expect(crumbs.querySelector("[aria-current='page']")?.textContent).toBe("둘째 팀");
  });

  it("U 키로 부모 팀 구성에 돌아온다. 주소로 직접 연 편집기에는 U도 브레드크럼도 없다", async () => {
    const { clients } = clientsFor({ tm1: graphWith("tm2"), tm2: child() });
    const { router } = mountApp(clients, "/teams/tm1");
    fireEvent.click(within(await screen.findByLabelText(/^노드 검토 파이프라인/)).getByRole("button", { name: "열기" }));
    await screen.findByRole("navigation", { name: "위치" });
    fireEvent.keyDown(document.body, { key: "u" });
    await waitFor(() => expect(router.state.location.pathname).toBe("/teams/tm1"));
    cleanup();
    const direct = mountApp(clientsFor({ tm1: graphWith("tm2"), tm2: child() }).clients, "/teams/tm2");
    await screen.findByText("둘째 팀", { selector: "h1" });
    expect(screen.queryByRole("navigation", { name: "위치" })).toBeNull();
    fireEvent.keyDown(document.body, { key: "u" });
    expect(direct.router.state.location.pathname).toBe("/teams/tm2");
  });

  it("저장하지 않은 변경이 있으면 [열기]가 저장하고 열기 / 저장 안 하고 열기 / 취소를 묻는다", async () => {
    const { clients, rest: r } = clientsFor({ tm1: graphWith("tm2"), tm2: child() });
    const { router } = mountApp(clients, "/teams/tm1");
    const card = await screen.findByLabelText(/^노드 검토 파이프라인/);
    fireEvent.click(screen.getByLabelText(/^노드 일꾼/));
    fireEvent.change(await screen.findByLabelText("이름", { selector: "input" }), { target: { value: "바뀐 이름" } });
    await screen.findByText("저장 안 됨");
    fireEvent.click(within(card).getByRole("button", { name: "열기" }));
    const dialog = await screen.findByRole("dialog", { name: "저장하지 않은 변경이 있습니다" });
    fireEvent.click(within(dialog).getByRole("button", { name: "취소" }));
    expect(router.state.location.pathname).toBe("/teams/tm1");
    fireEvent.click(within(card).getByRole("button", { name: "열기" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "저장하고 열기" }));
    await waitFor(() => expect(r.updateGraph).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(router.state.location.pathname).toBe("/teams/tm2"));
  });

  it("저장 안 하고 열기는 변경을 버리고 바로 이동한다(이탈 확인이 겹치지 않는다)", async () => {
    const { clients, rest: r } = clientsFor({ tm1: graphWith("tm2"), tm2: child() });
    const { router } = mountApp(clients, "/teams/tm1");
    const card = await screen.findByLabelText(/^노드 검토 파이프라인/);
    fireEvent.click(screen.getByLabelText(/^노드 일꾼/));
    fireEvent.change(await screen.findByLabelText("이름", { selector: "input" }), { target: { value: "바뀐 이름" } });
    await screen.findByText("저장 안 됨");
    fireEvent.click(within(card).getByRole("button", { name: "열기" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "저장 안 하고 열기" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/teams/tm2"));
    expect(r.updateGraph).not.toHaveBeenCalled();
  });

  it("정의 없음·자기 자신은 [열기]가 없거나 경고 배지가 붙는다", async () => {
    const { clients } = clientsFor({ tm1: graphWith("zz-missing"), tm2: child() });
    mountApp(clients, "/teams/tm1");
    const missing = await screen.findByLabelText(/^노드 검토 파이프라인/);
    expect(within(missing).getAllByText(/찾을 수 없음/).length).toBeGreaterThan(0);
    expect(within(missing).queryByRole("button", { name: "열기" })).toBeNull();
    cleanup();
    mountApp(clientsFor({ tm1: graphWith("tm1") }).clients, "/teams/tm1");
    const self = await screen.findByLabelText(/^노드 검토 파이프라인/);
    expect(within(self).getByText(/자기 자신/)).toBeTruthy();
  });
});

describe("중첩 노드 패널·팔레트", () => {
  it("설정 탭은 유효 설정(에이전트용) 계산을 부르지 않고 노드 타입 스키마의 일반 폼을 그린다", async () => {
    const { clients, rest: r } = clientsFor({ tm1: graphWith("tm2"), tm2: child() });
    mountApp(clients, "/teams/tm1");
    fireEvent.click(await screen.findByLabelText(/^노드 검토 파이프라인/));
    fireEvent.click(await screen.findByRole("tab", { name: "설정" }));
    expect(await screen.findByText("덮어쓰기")).toBeTruthy();
    expect(r.getNodeEffectiveSettings).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("tab", { name: "역할" }));
    expect(await screen.findByText("정의 정보")).toBeTruthy();
    expect(screen.getByText("내포 노드: 둘째 팀")).toBeTruthy();
    expect(screen.getByText("노드 5개 · 입구 입구")).toBeTruthy();
  });

  it("개요 탭에 중첩된 팀 구성 목록이 있다", async () => {
    const { clients } = clientsFor({ tm1: graphWith("tm2"), tm2: child() });
    mountApp(clients, "/teams/tm1");
    await screen.findByLabelText(/^노드 검토 파이프라인/);
    const section = await screen.findByRole("region", { name: "중첩된 팀 구성" }).catch(() => screen.getByLabelText("중첩된 팀 구성"));
    expect(within(section).getByText("검토 파이프라인 → 둘째 팀")).toBeTruthy();
  });
});
