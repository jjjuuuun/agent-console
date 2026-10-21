import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { agents, edgeTypes, nodeTypes, resourceTypes, sampleGraph } from "../../testing/teamFixtures";

configure({ asyncUtilTimeout: 10_000 });
afterEach(cleanup);

/** 편집기 화면이 쓰는 서버 응답(임의 이름 디스크립터). 실행 백엔드는 기본값으로 정해 둔다. */
function editorRest(overrides: Record<string, unknown> = {}, withDefaultBackend = true) {
  return createFakeClients({
    listNodeTypes: vi.fn(async () => nodeTypes),
    listEdgeTypes: vi.fn(async () => edgeTypes),
    listResourceTypes: vi.fn(async () => resourceTypes),
    listAgents: vi.fn(async () => agents),
    listInteractionKinds: vi.fn(async () => []),
    listDelegationStrategies: vi.fn(async () => []),
    listRuns: vi.fn(async () => []),
    listBackendModels: vi.fn(async () => []),
    listConversations: vi.fn(async () => []),
    listGraphs: vi.fn(async () => [{ id: "tm1", name: "임의 팀", labels: [], version_hash: "h1", saved_at: 1, node_count: 2, edge_count: 1, entry_labels: ["일꾼"] }]),
    getGraph: vi.fn(async () => ({ graph: sampleGraph(), version_hash: "h1", saved_at: 1 })),
    validateGraph: vi.fn(async () => []),
    updateGraph: vi.fn(async (_id: string, g: unknown) => ({ graph: g, version_hash: "h2" })),
    resolvePorts: vi.fn(async () => ({ inputs: [], outputs: [] })),
    getGraphPlan: vi.fn(async () => ({ entries: [{ edge_id: "x1", node_id: "a1" }], answers: [], grants: {} })),
    planDraftGraph: vi.fn(async () => ({ entries: [{ edge_id: "x1", node_id: "a1" }], answers: [], grants: {} })),
    getNodeEffectiveSettings: vi.fn(async () => ({ value: {}, provenance: {}, layers: [{ id: "L0", label: "공통" }, { id: "L1", label: "팀 구성" }, { id: "L2", label: "에이전트" }, { id: "L3", label: "이 팀의 노드" }] })),
    getAgentEffectiveSettings: vi.fn(async () => ({ value: {}, provenance: {}, layers: [] })),
    listResources: vi.fn(async () => [{ id: "rs1", type: "rt-doc", name: "공용 문서", version_hash: "r1", usage_count: 0 }]),
    ...(withDefaultBackend ? { getSettingsVersioned: vi.fn(async () => ({ value: { agent_defaults: { backend: "be-1" } }, version_hash: "s1" })) } : {}),
    ...overrides,
  });
}

async function openAddMenu() {
  fireEvent.click(await screen.findByTestId("add-button"));
  return screen.findByRole("menu");
}

describe("팀 편집기 [+ 추가] 메뉴", () => {
  it("메뉴 항목은 노드 타입 디스크립터에서 나오고 숫자 키로 고른다", async () => {
    const { clients } = editorRest();
    mountApp(clients, "/teams/tm1");
    const menu = await openAddMenu();
    const labels = within(menu).getAllByRole("menuitem").map((n) => n.getAttribute("title"));
    expect(labels).toEqual(["행위자 고르기…", "새 행위자…", "자산 고르기…", "새 자산…", "사람 추가"]);
    fireEvent.keyDown(within(menu).getAllByRole("menuitem")[0]!, { key: "2" });
    expect(await screen.findByRole("dialog", { name: "새 행위자" })).toBeTruthy();
  });

  it("Alt+N이 메뉴를 연다", async () => {
    const { clients } = editorRest();
    mountApp(clients, "/teams/tm1");
    await screen.findByTestId("add-button");
    fireEvent.keyDown(document, { key: "n", altKey: true });
    expect(await screen.findByRole("menu")).toBeTruthy();
  });

  it("에이전트 고르기: 목록에서 고르면 팀 초안에 노드가 늘고 저장은 하지 않는다", async () => {
    const { clients, rest: r } = editorRest();
    mountApp(clients, "/teams/tm1");
    const menu = await openAddMenu();
    fireEvent.click(within(menu).getByRole("menuitem", { name: /행위자 고르기/ }));
    const list = await screen.findByRole("listbox", { name: "행위자" });
    expect(within(list).getByText("이미 1개")).toBeTruthy(); // ag1은 이미 노드가 있다
    fireEvent.click(within(list).getByRole("option", { name: /둘째 에이전트/ }));
    expect(await screen.findByText("저장 안 됨")).toBeTruthy();
    expect(r.updateGraph).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(r.updateGraph).toHaveBeenCalledTimes(1));
    const sent = r.updateGraph.mock.calls[0]![1] as { nodes: { type: string; config?: { ref?: string } }[] };
    expect(sent.nodes).toHaveLength(3);
    expect(sent.nodes.at(-1)).toMatchObject({ type: "t-actor", config: { ref: "ag2" } });
  });

  it("리소스 고르기: 붙일 곳을 팀 공용으로 고르면 팀 공용 첨부가 늘어난다", async () => {
    const { clients, rest: r } = editorRest();
    mountApp(clients, "/teams/tm1");
    const menu = await openAddMenu();
    fireEvent.click(within(menu).getByRole("menuitem", { name: /자산 고르기/ }));
    const list = await screen.findByRole("listbox", { name: "자산" });
    expect(screen.getByRole("radio", { name: "팀 공용" })).toBeTruthy();
    fireEvent.click(within(list).getByRole("option", { name: /공용 문서/ }));
    await waitFor(() => expect(screen.getByText("저장 안 됨")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(r.updateGraph).toHaveBeenCalledTimes(1));
    const sent = r.updateGraph.mock.calls[0]![1] as { settings?: { resources?: { ref: string }[] } };
    expect(sent.settings?.resources).toEqual([{ ref: "rs1" }]);
  });
});

describe("CreateDefinitionDrawer", () => {
  it("에이전트 전체 폼으로 만들면 목록 갱신 → 노드 추가 → 서랍 닫힘, 팀은 저장하지 않는다", async () => {
    const createAgent = vi.fn(async (a: unknown) => a);
    const { clients, rest: r } = editorRest({ createAgent });
    mountApp(clients, "/teams/tm1");
    const menu = await openAddMenu();
    fireEvent.click(within(menu).getByRole("menuitem", { name: /새 행위자/ }));
    const drawer = await screen.findByRole("dialog", { name: "새 행위자" });
    // 에이전트 화면과 같은 폼: 정체성 + 설정 폼
    fireEvent.change(within(drawer).getByLabelText("이름"), { target: { value: "My Planner" } });
    expect((within(drawer).getByLabelText("id") as HTMLInputElement).value).toBe("my-planner");
    fireEvent.change(within(drawer).getByLabelText("역할"), { target: { value: "설계" } });
    expect(within(drawer).getByText(/화면에도 나타납니다/)).toBeTruthy();
    fireEvent.click(within(drawer).getByRole("button", { name: "만들고 팀에 추가" }));
    await waitFor(() => expect(createAgent).toHaveBeenCalledTimes(1));
    expect(createAgent.mock.calls[0]![0]).toMatchObject({ id: "my-planner", name: "My Planner", role: "설계" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "새 행위자" })).toBeNull());
    expect(await screen.findByText("저장 안 됨")).toBeTruthy();
    expect(r.updateGraph).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(r.updateGraph).toHaveBeenCalled());
    const sent = r.updateGraph.mock.calls[0]![1] as { nodes: { config?: { ref?: string } }[] };
    expect(sent.nodes.at(-1)?.config?.ref).toBe("my-planner");
  });

  it("정의 생성이 실패하면 서랍을 닫지 않고 원인을 보이며, 팀 초안은 그대로다", async () => {
    const createAgent = vi.fn(async () => {
      throw new Error("이미 있는 id");
    });
    const { clients } = editorRest({ createAgent });
    mountApp(clients, "/teams/tm1");
    const menu = await openAddMenu();
    fireEvent.click(within(menu).getByRole("menuitem", { name: /새 행위자/ }));
    const drawer = await screen.findByRole("dialog", { name: "새 행위자" });
    fireEvent.change(within(drawer).getByLabelText("이름"), { target: { value: "충돌" } });
    fireEvent.click(within(drawer).getByRole("button", { name: "만들고 팀에 추가" }));
    expect(await within(drawer).findByText("이미 있는 id")).toBeTruthy();
    expect(screen.getByRole("dialog", { name: "새 행위자" })).toBeTruthy();
    expect(screen.getByText("저장됨")).toBeTruthy();
  });

  it("입력한 채 닫으면 버릴지 묻고, 입력이 없으면 바로 닫힌다", async () => {
    const { clients } = editorRest();
    mountApp(clients, "/teams/tm1");
    let menu = await openAddMenu();
    fireEvent.click(within(menu).getByRole("menuitem", { name: /새 행위자/ }));
    let drawer = await screen.findByRole("dialog", { name: "새 행위자" });
    fireEvent.keyDown(drawer, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "새 행위자" })).toBeNull());
    menu = await openAddMenu();
    fireEvent.click(within(menu).getByRole("menuitem", { name: /새 행위자/ }));
    drawer = await screen.findByRole("dialog", { name: "새 행위자" });
    fireEvent.change(within(drawer).getByLabelText("이름"), { target: { value: "작성 중" } });
    fireEvent.keyDown(drawer, { key: "Escape" });
    expect(await screen.findByText("작성 중인 내용을 버릴까요?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "버리고 닫기" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "새 행위자" })).toBeNull());
  });

  it("리소스는 종류를 고른 뒤 같은 편집기로 만들고 팀 공용으로 붙인다", async () => {
    const createResource = vi.fn(async (r: unknown) => ({ value: r, version_hash: "rv1" }));
    const putResourceContent = vi.fn(async () => ({ value: "", version_hash: "rv2" }));
    const { clients, rest: r } = editorRest({ createResource, putResourceContent });
    mountApp(clients, "/teams/tm1");
    const menu = await openAddMenu();
    fireEvent.click(within(menu).getByRole("menuitem", { name: /새 자산/ }));
    const drawer = await screen.findByRole("dialog", { name: "새 자산" });
    const firstType = within(drawer).getAllByRole("radio")[0]!;
    fireEvent.click(firstType);
    fireEvent.change(await within(drawer).findByLabelText("이름"), { target: { value: "새 문서" } });
    expect(within(drawer).getByRole("radio", { name: "팀 공용으로 붙이기" })).toBeTruthy();
    fireEvent.click(within(drawer).getByRole("button", { name: "만들고 추가" }));
    await waitFor(() => expect(createResource).toHaveBeenCalledTimes(1));
    expect(createResource.mock.calls[0]![0]).toMatchObject({ name: "새 문서" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "새 자산" })).toBeNull());
    expect(await screen.findByText("저장 안 됨")).toBeTruthy();
    expect(r.updateGraph).not.toHaveBeenCalled();
  });
});

describe("편집기 [대화 시작] 백엔드 점검", () => {
  it("백엔드가 비어 있으면 해결 카드를 먼저 보이고, 고르면 기본값으로 저장한 뒤 대화를 연다", async () => {
    const { clients, rest: r } = editorRest({}, false);
    mountApp(clients, "/teams/tm1");
    const start = await screen.findByRole("button", { name: /대화 시작/ });
    await waitFor(() => expect((start as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(start);
    const card = await screen.findByTestId("backend-chooser");
    expect(within(card).getByText(/'일꾼'/)).toBeTruthy();
    expect(r.createConversation).not.toHaveBeenCalled();
    fireEvent.click(within(card).getByRole("radio", { name: /백엔드 하나/ }));
    fireEvent.click(within(card).getByRole("button", { name: "선택하고 계속" }));
    await waitFor(() => expect(r.putSettingsVersioned).toHaveBeenCalledTimes(1));
    expect((r.putSettingsVersioned.mock.calls[0]![0] as { agent_defaults?: { backend?: string } }).agent_defaults?.backend).toBe("be-1");
    await waitFor(() => expect(r.createConversation).toHaveBeenCalledWith({ graph_id: "tm1" }));
  });

  it("백엔드가 정해져 있으면 카드 없이 바로 시작한다", async () => {
    const { clients, rest: r } = editorRest();
    mountApp(clients, "/teams/tm1");
    const start = await screen.findByRole("button", { name: /대화 시작/ });
    await waitFor(() => expect((start as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(start);
    await waitFor(() => expect(r.createConversation).toHaveBeenCalledWith({ graph_id: "tm1" }));
    expect(screen.queryByTestId("backend-chooser")).toBeNull();
  });
});
