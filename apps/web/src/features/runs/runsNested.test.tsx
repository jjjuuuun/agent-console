import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { Interaction, NodeRun, Run, RunEvent } from "@agent-console/contracts";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";
import { createFakeClients } from "../../testing/fakes";
import { DEFINITION_KINDS } from "../library";

beforeAll(preloadScreens, 120_000);

// 캔버스는 레이아웃이 필요해 happy-dom에서 돌지 않는다. 실행 상세가 편집기에 내려보내는 props만 확인한다.
vi.mock("@agent-console/graph-editor", () => ({
  createElkEngine: () => ({ id: "fake", title: "fake", options: [], run: async () => ({ positions: {} }) }),
  GraphEditor: (props: Record<string, unknown>) => {
    const sel = props["onSelectionChange"] as (s: { nodeIds: string[]; edgeIds: string[] }) => void;
    const pick = (key: string) => JSON.stringify(props[key] ?? null);
    return (
      <div data-testid="graph">
        <pre data-testid="p-runBadges">{pick("nodeRunBadges")}</pre>
        <pre data-testid="p-edgeBadges">{pick("edgeBadges")}</pre>
        <pre data-testid="p-edgeChips">{pick("edgeExtraChips")}</pre>
        <pre data-testid="p-nodeBadges">{pick("nodeBadgesOverride")}</pre>
        <pre data-testid="p-states">{pick("nodeStates")}</pre>
        <pre data-testid="p-edgeStates">{pick("edgeStates")}</pre>
        <pre data-testid="p-binds">{JSON.stringify(Object.fromEntries(Object.entries((props["bindSummaries"] ?? {}) as Record<string, { title: string; subtitle?: string }>).map(([k, v]) => [k, { title: v.title, subtitle: v.subtitle }])))}</pre>
        <button type="button" onClick={() => sel({ nodeIds: ["w"], edgeIds: [] })}>작성자 선택</button>
        <button type="button" onClick={() => sel({ nodeIds: [], edgeIds: ["e-cond"] })}>조건 연결 선택</button>
        <button type="button" onClick={() => (props["bindSummaries"] as Record<string, { open?: { onOpen(): void } }>)["t"]?.open?.onOpen()}>자식 열기 카드</button>
        <button type="button" onClick={() => (props["nodeRunBadges"] as Record<string, { onClick?(): void }>)["w"]?.onClick?.()}>회차 배지</button>
      </div>
    );
  },
}));

afterEach(cleanup);

const now = Math.floor(Date.now() / 1000);
const run = (id: string, status: Run["status"], extra: Partial<Run> = {}): Run => ({ id, graph_id: "g1", graph_version: "v1", status, input: {}, origin: "chat", created_at: now - 120, started_at: now - 100, ...extra });
const nr = (node: string, iteration: number, started: number, extra: Partial<NodeRun> = {}): NodeRun => ({ run_id: "r1", node_id: node, status: "succeeded", attempt: 1, iteration, call: 0, started_at: now - started, duration_ms: 1500, ...extra });
const ev = (seq: number, type: string, payload: Record<string, unknown>, extra: Partial<RunEvent> = {}): RunEvent => ({ event_id: `e${seq}`, run_id: "r1", seq, ts: now - 100 + seq, node_path: [], type, payload, ...extra });

const child = run("c1abcdef", "running", { parent_run_id: "r1", root_run_id: "r1", parent_node_id: "t", graph_id: "g2", created_at: now - 50, started_at: now - 49 });
const childPending: Interaction = { id: "ci1", run_id: "c1abcdef", root_run_id: "r1", node_id: "z", node_path: ["z"], kind: "k-free", status: "pending", title: "자식의 질문", created_at: now - 5, response_schema: { type: "object", properties: { reply: { type: "string", title: "답장" } } } };

const graph1 = {
  id: "g1",
  name: "부모 팀",
  nodes: [{ id: "w", type: "t-a", label: "작성자" }, { id: "v", type: "t-a", label: "검토" }, { id: "t", type: "t-inner", label: "하위 팀", config: { pick: "g2" } }],
  edges: [
    { id: "e-cond", source: { node: "w", port: "o" }, target: { node: "v", port: "i" }, kind: "k-cond" },
    { id: "e-loop", source: { node: "v", port: "o" }, target: { node: "w", port: "i" }, kind: "k-loop" },
    { id: "e-fail", source: { node: "v", port: "o" }, target: { node: "t", port: "i" }, kind: "k-fail" },
  ],
};
const graph2 = { id: "g2", name: "자식 팀", nodes: [{ id: "z", type: "t-a", label: "자식 노드" }], edges: [] };

const events = [
  ev(1, "edge.traversed", { edge_id: "e-cond", condition: { result: true, combinator: "all", items: [{ path: "/output", op: "op-1", value: "PASS", actual: "all PASS", result: true }] } }, { node_path: [] }),
  ev(2, "loop.iteration", { edge_id: "e-loop", iteration: 1, nodes: ["w", "v"] }),
  ev(3, "edge.traversed", { edge_id: "e-loop" }),
  ev(4, "loop.iteration", { edge_id: "e-loop", iteration: 2, nodes: ["w", "v"] }),
  ev(5, "edge.traversed", { edge_id: "e-loop" }),
  ev(6, "loop.exhausted", { edge_id: "e-loop", iteration: 2, max_iterations: 2 }),
  ev(7, "run.child_started", { child_run_id: "c1abcdef", node_id: "t", graph_id: "g2" }, { node_path: ["t"] }),
];

function overrides(extra: Record<string, unknown> = {}) {
  return {
    listGraphs: async () => [{ id: "g1", name: "부모 팀", version_hash: "v1", node_count: 3, edge_count: 3 }, { id: "g2", name: "자식 팀", version_hash: "v2", node_count: 1, edge_count: 0 }],
    listAgents: async () => [],
    listConversations: async () => [],
    listNodeTypes: async () => [{ id: "t-a", title: "에이전트류", binds: { kind: "k-agent", field: "ref" } }, { id: "t-inner", title: "내포", executable: true, binds: { kind: DEFINITION_KINDS.graph, field: "pick" } }],
    listEdgeTypes: async () => [
      { id: "k-cond", title: "조건 연결", scheduling: "flow", config_schema: {}, ui_schema: {} },
      { id: "k-loop", title: "반복 연결", scheduling: "flow", cycle: { max_iterations: 2 } },
      { id: "k-fail", title: "실패 시", scheduling: "flow", handles_failure: true },
    ],
    listConditionOperators: async () => [{ id: "op-1", title: "포함", value_schema: { type: "string" } }],
    listInteractionKinds: async () => [{ id: "k-free", title: "자유 질문" }],
    getRun: async (id: string) =>
      id === "r1"
        ? { run: run("r1", "running"), node_runs: [nr("w", 0, 90), nr("w", 1, 60), nr("w", 2, 30, { status: "running" }), nr("t", 0, 20, { status: "running" })], last_seq: 7, children: [child] }
        : { run: child, node_runs: [], last_seq: 1, children: [] },
    listRuns: async (p?: { root?: string }) => (p?.root === "r1" ? [child] : []),
    getGraphVersion: async (gid: string) => ({ kind: "graph", id: gid, version_hash: "v", saved_at: 1, content: gid === "g2" ? graph2 : graph1 }),
    listRunEvents: async (id: string) => (id === "r1" ? events : []),
    getRunTrace: async () => ({ run_id: "r1", spans: [], links: [] }),
    listRunInteractions: async () => [],
    listInteractions: async () => [childPending],
    ...extra,
  };
}

function mount(path: string, over: Record<string, unknown> = {}) {
  const { clients, rest, ws } = createFakeClients(overrides(over));
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: [path] });
  render(<AppRoot createClients={async () => clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
  return { router, rest, ws };
}
const json = (id: string) => JSON.parse(screen.getByTestId(id).textContent ?? "null");

describe("실행 상세: 회차·반복·실패 처리·자식 실행", () => {
  it("노드 회차 배지·연결 배지(통과 횟수·한도 도달)·중첩 노드 자식 실행 줄이 편집기 props로 내려간다", async () => {
    mount("/runs/r1");
    await screen.findByTestId("graph");
    await waitFor(() => expect(json("p-runBadges")["w"]).toBeTruthy());
    expect(json("p-runBadges")["w"]).toMatchObject({ text: "#3", picked: false });
    expect(json("p-runBadges")["w"].ariaLabel).toBe("작성자, 3회차, 실행 중. 실행 3개 중 3번째");
    expect(json("p-runBadges")["t"]).toBeUndefined();
    expect(json("p-edgeBadges")["e-loop"]).toEqual([{ text: "↻×2 한도 2회 도달", ariaLabel: "반복 연결 2번 지나감, 반복 한도 2회에 도달", tone: "warning" }]);
    // 반복 연결은 순번 배지를 쓰지 않는다
    expect(json("p-edgeStates")["e-loop"]).toBe("dead");
    await waitFor(() => expect(json("p-binds")["t"]).toEqual({ title: "자식 팀", subtitle: "자식 실행 c1abcd · 실행 중" }));
  });

  it("조건 연결 칩은 서버 연산자·ui_schema 위젯이 없어도 종류 속성만으로 안전하다", async () => {
    mount("/runs/r1");
    await screen.findByTestId("graph");
    expect(json("p-edgeChips")["e-loop"][0]).toMatchObject({ title: "최대 2회" });
  });

  it("노드 탭: 실행이 3개면 실행 목록, 행을 고르면 보이는 실행이 고정되고 End는 최신으로 따라간다", async () => {
    const { router } = mount("/runs/r1");
    fireEvent.click(await screen.findByRole("button", { name: "작성자 선택" }));
    await waitFor(() => expect(router.state.location.search).toContain("node=w"));
    fireEvent.click(await screen.findByRole("tab", { name: "노드·연결" }));
    const grid = await screen.findByRole("grid", { name: "실행 목록" });
    const rows = within(grid).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("gridcell")[0]!.textContent)).toEqual(["1회차", "2회차", "3회차"]);
    expect(rows[2]!.getAttribute("aria-selected")).toBe("true");
    fireEvent.click(rows[0]!);
    await waitFor(() => expect(json("p-runBadges")["w"]).toMatchObject({ text: "#1", picked: true }));
    expect(json("p-runBadges")["w"].ariaLabel).toContain("(고름)");
    fireEvent.keyDown(rows[0]!, { key: "End" });
    await waitFor(() => expect(json("p-runBadges")["w"]).toMatchObject({ text: "#3", picked: false }));
  });

  it("`,` `.` 키로 선택한 노드의 이전·다음 실행으로 옮기고 경계에서 멈춘다", async () => {
    mount("/runs/r1");
    fireEvent.click(await screen.findByRole("button", { name: "작성자 선택" }));
    await waitFor(() => expect(json("p-runBadges")["w"]).toBeTruthy());
    fireEvent.keyDown(document.body, { key: "," });
    await waitFor(() => expect(json("p-runBadges")["w"].text).toBe("#2"));
    fireEvent.keyDown(document.body, { key: "," });
    await waitFor(() => expect(json("p-runBadges")["w"].text).toBe("#1"));
    fireEvent.keyDown(document.body, { key: "," });
    expect((await screen.findAllByText("첫 실행입니다")).length).toBeGreaterThan(0);
    fireEvent.keyDown(document.body, { key: "." });
    await waitFor(() => expect(json("p-runBadges")["w"].text).toBe("#2"));
  });

  it("연결을 고르면 노드·연결 탭에 연결 상세(판정 근거)가 나온다", async () => {
    const { router } = mount("/runs/r1");
    fireEvent.click(await screen.findByRole("button", { name: "조건 연결 선택" }));
    await waitFor(() => expect(router.state.location.search).toContain("edge=e-cond"));
    expect(await screen.findByText("연결: 작성자 → 검토")).toBeTruthy();
    expect(screen.getByText("모두 만족 → 결과: 통과")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("포함")).toBeTruthy());
    expect(screen.getByText(/all PASS/)).toBeTruthy();
  });

  it("노드를 고른 뒤 연결을 고르면 노드 선택이 풀리고 연결 상세가 남는다(선택 비우기 호출이 연결 선택을 지우지 않는다)", async () => {
    const { router } = mount("/runs/r1");
    fireEvent.click(await screen.findByRole("button", { name: "작성자 선택" }));
    await waitFor(() => expect(router.state.location.search).toContain("node=w"));
    fireEvent.click(screen.getByRole("button", { name: "조건 연결 선택" }));
    await waitFor(() => expect(router.state.location.search).toContain("edge=e-cond"));
    expect(router.state.location.search).not.toContain("node=");
    expect(await screen.findByText("연결: 작성자 → 검토")).toBeTruthy();
  });

  it("에이전트 탭의 이벤트 요약: 반복 시작은 값 + 1 회차, 한도 도달은 한도, 자식 실행 시작은 팀 이름·짧은 id", async () => {
    mount("/runs/r1?tab=agents");
    expect(await screen.findByText("↻ 반복 2회차 시작 · 작성자, 검토")).toBeTruthy();
    expect(screen.getByText("↻ 반복 3회차 시작 · 작성자, 검토")).toBeTruthy();
    expect(screen.getByText(/↻ 반복 한도 도달 \(한도 2회\)/)).toBeTruthy();
    expect(await screen.findByText("▣ 자식 실행 시작 · 자식 팀 · c1abcd")).toBeTruthy();
    // 실행 전체 항목(actor가 없는 이벤트)
    expect(screen.getByRole("button", { name: /실행 전체/ })).toBeTruthy();
  });
});

describe("실행 상세: 자식 실행 이동", () => {
  it("루트 헤더에 자식 실행 메뉴가 있고 열면 자식 실행 화면으로 간다. 취소 확인에 활성 자식 수가 들어간다", async () => {
    const { router } = mount("/runs/r1");
    const menu = await screen.findByRole("button", { name: /자식 실행 1개/ });
    fireEvent.click(menu);
    fireEvent.click(screen.getByRole("menuitem", { name: /자식 팀 · 하위 팀/ }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/runs/c1abcdef"));
    cleanup();
    mount("/runs/r1");
    fireEvent.click(await screen.findByRole("button", { name: "취소" }));
    expect(await screen.findByText("진행 중인 자식 실행 1개도 함께 취소됩니다.")).toBeTruthy();
  });

  it("자식 실행 화면: 빵부스러기·상위 링크, [취소] 대신 [상위 실행에서 취소], U 키로 상위로", async () => {
    const { router } = mount("/runs/c1abcdef");
    const crumbs = await screen.findByRole("navigation", { name: "실행 위치" });
    expect(within(crumbs).getByRole("link", { name: "루트 r1" })).toBeTruthy();
    expect(crumbs.querySelector("[aria-current='page']")?.textContent).toContain("c1abcd");
    expect(await screen.findByText(/자식 실행 · 상위 r1의 ‘하위 팀’ 노드/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "취소" })).toBeNull();
    expect(screen.getByRole("link", { name: "상위 실행에서 취소 ↗" }).getAttribute("href")).toBe("/runs/r1");
    fireEvent.keyDown(document.body, { key: "u" });
    await waitFor(() => expect(router.state.location.pathname).toBe("/runs/r1"));
  });

  it("중첩 노드 카드의 [열기]와 D 키가 보이는 실행의 자식 실행으로 간다", async () => {
    const { router } = mount("/runs/r1");
    fireEvent.click(await screen.findByRole("button", { name: "자식 열기 카드" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/runs/c1abcdef"));
  });

  it("상호작용 탭: 루트 실행이면 자식 실행의 대기 요청이 출처 칩과 함께 오고, 답은 자식 Run에 보낸다", async () => {
    const respondInteraction = vi.fn(async () => ({ ...childPending, status: "answered" as const }));
    mount("/runs/r1?tab=interactions", { respondInteraction });
    expect(await screen.findByText("자식 실행의 지난 요청은 각 실행 화면에서 볼 수 있습니다.")).toBeTruthy();
    const chip = await screen.findByRole("link", { name: /자식 실행 c1abcd · 자식 팀/ });
    expect(chip.getAttribute("href")).toBe("/runs/c1abcdef");
    // 요청자 표기에 부모 노드(중첩 팀)가 붙는다
    expect(screen.getAllByText(/하위 팀\(중첩 팀\) ›/).length).toBeGreaterThan(0);
    fireEvent.change(await screen.findByLabelText("답장"), { target: { value: "네" } });
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    await waitFor(() => expect(respondInteraction).toHaveBeenCalledWith("c1abcdef", "ci1", { reply: "네" }));
  });

  it("활성 자식은 자식 Run 구독(run:<id>)을 만들고 화면을 떠나면 해제한다", async () => {
    const unsub = vi.fn();
    const subscribeRun = vi.fn((...args: unknown[]) => (args.length >= 0 ? { topic: "x", unsubscribe: unsub } : undefined));
    const { clients } = createFakeClients(overrides());
    clients.ws.subscribeRun = subscribeRun as never;
    const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: ["/runs/r1"] });
    const view = render(<AppRoot createClients={async () => clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
    await waitFor(() => expect(subscribeRun.mock.calls.map((c) => c[0])).toContain("c1abcdef"));
    await act(async () => {
      await router.navigate("/runs");
    });
    await waitFor(() => expect(unsub).toHaveBeenCalled());
    view.unmount();
  });
});

describe("실행 기록: 자식 실행 포함 토글", () => {
  const rootRun = run("r1", "completed");
  it("기본은 자식 실행을 가리고, 켜면 ↳·자식 칩·상위 링크·상위에 포함이 나온다", async () => {
    const { router } = mount("/runs", { listRuns: async () => [rootRun, child] });
    const grid = await screen.findByRole("grid", { name: "실행 목록" });
    expect(within(grid).getAllByRole("row")).toHaveLength(2);
    fireEvent.click(screen.getByRole("checkbox", { name: "자식 실행 포함" }));
    await waitFor(() => expect(within(screen.getByRole("grid")).getAllByRole("row")).toHaveLength(3));
    expect(router.state.location.search).toContain("children=1");
    const childRow = document.querySelector<HTMLElement>("[data-run-id='c1abcdef']")!;
    expect(within(childRow).getByText("자식")).toBeTruthy();
    expect(within(childRow).getByRole("link", { name: "상위 r1" })).toBeTruthy();
    expect(within(childRow).getByText("상위에 포함")).toBeTruthy();
  });
  it("자식 실행만 있는 구간이면 안내와 [자식 실행 포함]", async () => {
    mount("/runs", { listRuns: async () => [child] });
    expect(await screen.findByText("자식 실행만 있는 구간입니다")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "자식 실행 포함" }));
    expect(await screen.findByRole("grid", { name: "실행 목록" })).toBeTruthy();
  });
});
