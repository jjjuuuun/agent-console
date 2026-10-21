import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { beforeAll, afterEach, describe, expect, it, vi } from "vitest";
import type { Interaction, Run, RunEvent } from "@agent-console/contracts";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";

// 화면은 처음 열 때 내려받는다(lazyScreen). 느린 파일시스템에서 첫 이동이 제한 시간을 넘지 않게 미리 불러온다.
beforeAll(preloadScreens, 120_000);
import { createFakeClients } from "../../testing/fakes";

// 캔버스(React Flow)는 레이아웃 API가 필요해 happy-dom에서 돌지 않는다. 실행 상태가 어떤 props로 내려가는지만 확인한다.
vi.mock("@agent-console/graph-editor", () => ({
  // 팀 편집 화면이 모듈 수준에서 만드는 자동 배치 엔진(이 테스트에서는 쓰이지 않는다)
  createElkEngine: () => ({ id: "fake", title: "fake", options: [], run: async () => ({ positions: {} }) }),
  GraphEditor: (props: Record<string, unknown>) => (
    <div data-testid="graph" data-mode={String(props["mode"])} data-props={JSON.stringify({ nodeStates: props["nodeStates"], edgeOrder: props["edgeOrder"], edgeCounts: props["edgeCounts"], waitingNodes: props["waitingNodes"], badges: props["nodeBadgesOverride"] })}>
      <button type="button" onClick={() => (props["onSelectionChange"] as (s: { nodeIds: string[]; edgeIds: string[] }) => void)({ nodeIds: ["n-wait"], edgeIds: [] })}>
        노드 선택
      </button>
    </div>
  ),
}));

afterEach(cleanup);

const now = Math.floor(Date.now() / 1000);
const run = (id: string, status: Run["status"], extra: Partial<Run> = {}): Run => ({ id, graph_id: "g1", graph_version: "v1", status, input: { text: `입력 ${id}` }, origin: "chat", created_at: now - 120, started_at: now - 100, ...extra });

function mount(path: string, overrides: Record<string, unknown> = {}, setup?: (clients: ReturnType<typeof createFakeClients>) => void) {
  const { clients, rest, ws } = createFakeClients({
    listGraphs: async () => [{ id: "g1", name: "개발 팀", version_hash: "v1", node_count: 3, edge_count: 2 }],
    listConversations: async () => [{ id: "c1", graph_id: "g1", title: "로그인 화면 스펙", created_at: 1, updated_at: 2 }],
    listAgents: async () => [{ id: "pl", name: "PL" }, { id: "be", name: "백엔드 리더" }],
    ...overrides,
  });
  setup?.({ clients, rest, ws } as ReturnType<typeof createFakeClients>);
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: [path] });
  render(<AppRoot createClients={async () => clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
  return { router, rest, ws, clients };
}

describe("실행 기록 목록", () => {
  const runs = [run("r-wait", "waiting", { conversation_id: "c1", totals: { input_tokens: 3000, output_tokens: 1100 } }), run("r-run", "running", { origin: "api" }), run("r-done", "completed", { started_at: now - 90, ended_at: now - 40 })];

  it("행마다 상태 칩·팀 구성·대화/출처·토큰을 보이고 응답 대기 행을 표시한다", async () => {
    mount("/runs", { listRuns: async () => runs });
    const table = await screen.findByRole("grid", { name: "실행 목록" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(rows[0]!.getAttribute("data-waiting")).toBe("true");
    expect(within(rows[0]!).getByText("응답 대기")).toBeTruthy();
    expect(within(rows[0]!).getByRole("link", { name: "로그인 화면 스펙" })).toBeTruthy();
    expect(within(rows[0]!).getByText("4.1k")).toBeTruthy();
    expect(within(rows[1]!).getByText("(직접 실행: API)")).toBeTruthy();
    expect(screen.getByText("실행 중 1 · 응답 대기 1")).toBeTruthy();
  });

  it("[응답 대기만] 단축 필터가 상태를 URL에 반영하고, 결과가 없으면 필터 지우기를 안내한다", async () => {
    const { router } = mount("/runs", { listRuns: async () => runs });
    await screen.findByRole("grid", { name: "실행 목록" });
    fireEvent.click(screen.getByRole("button", { name: "응답 대기만" }));
    await waitFor(() => expect(within(screen.getByRole("grid")).getAllByRole("row")).toHaveLength(2));
    expect(router.state.location.search).toContain("status=waiting");
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "없는검색어" } });
    expect(await screen.findByText("조건에 맞는 실행이 없습니다")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "필터 지우기" }));
    expect(await screen.findByRole("grid", { name: "실행 목록" })).toBeTruthy();
    expect(router.state.location.search).toBe("");
  });

  it("실행이 하나도 없으면 안내와 채팅으로 가는 버튼", async () => {
    mount("/runs", { listRuns: async () => [] });
    expect(await screen.findByText(/아직 실행 기록이 없습니다/)).toBeTruthy();
    expect(screen.getByText("채팅에서 대화를 시작하면 여기에 쌓입니다.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "채팅으로" })).toBeTruthy();
  });

  it("행 메뉴의 취소는 확인을 거쳐 cancelRun을 부른다(활성 실행만 메뉴에 있음)", async () => {
    const cancelRun = vi.fn(async () => run("r-run", "cancelled"));
    mount("/runs", { listRuns: async () => runs, cancelRun });
    await screen.findByRole("grid");
    fireEvent.click(screen.getByRole("button", { name: "행 동작: r-run" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "취소" }));
    expect(cancelRun).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button", { name: "실행 취소" }));
    await waitFor(() => expect(cancelRun).toHaveBeenCalledWith("r-run"));
    fireEvent.click(screen.getByRole("button", { name: "행 동작: r-done" }));
    expect(screen.queryByRole("menuitem", { name: "취소" })).toBeNull();
  });

  it("위임 집계 탭: 행렬 표에 숫자와 방식 분해가 있다", async () => {
    mount("/runs?view=handoffs", {
      listRuns: async () => runs,
      getHandoffs: async () => ({ runs: 2, cells: [{ source: "pl", target: "be", kind: "k-x", count: 5 }, { source: "pl", target: "be", kind: "delegated", count: 2 }] }),
      listEdgeTypes: async () => [{ id: "k-x", title: "연결 가나" }],
    });
    const table = await screen.findByRole("table", { name: "위임 집계 표" });
    const cell = await within(table).findByRole("button", { name: /PL에서 백엔드 리더\(으\)로 7회/ });
    expect(cell.getAttribute("aria-label")).toContain("연결 가나 5");
    expect(cell.getAttribute("aria-label")).toContain("delegated 2");
  });
});

// ---------------------------------------------------------------- 실행 상세

const ev = (seq: number, type: string, extra: Partial<RunEvent> = {}): RunEvent => ({ event_id: `e${seq}`, run_id: "r1", seq, ts: now - 100 + seq, node_path: [], type, ...extra });
const pendingI: Interaction = { id: "i1", run_id: "r1", node_id: "n-wait", actor: "be", kind: "k-free", status: "pending", title: "확인 요청", created_at: now - 12, response_schema: { type: "object", properties: { reply: { type: "string", title: "답장" } } } };
const answeredI: Interaction = { id: "i0", run_id: "r1", node_id: "n-lead", actor: "pl", kind: "k-free", status: "answered", answered_by: "user", created_at: now - 60, closed_at: now - 40, response: { reply: "ok" } };

const detailOverrides = (extra: Record<string, unknown> = {}) => ({
  getRun: async () => ({ run: run("r1", "waiting", { conversation_id: "c1", totals: { input_tokens: 1204, output_tokens: 340 } }), node_runs: [{ run_id: "r1", node_id: "n-lead", status: "succeeded", started_at: now - 90 }, { run_id: "r1", node_id: "n-wait", status: "waiting", started_at: now - 50 }], last_seq: 6 }),
  getGraphVersion: async () => ({
    kind: "graph",
    id: "g1",
    version_hash: "v1",
    saved_at: 1,
    content: {
      id: "g1",
      name: "개발 팀",
      nodes: [{ id: "n-lead", type: "t-a", label: "PL" }, { id: "n-wait", type: "t-a", label: "백엔드" }, { id: "n-sub", type: "t-a", label: "QA" }],
      edges: [
        { id: "e-flow", source: { node: "n-lead", port: "o" }, target: { node: "n-wait", port: "i" }, kind: "k-flow" },
        { id: "e-call", source: { node: "n-lead", port: "o" }, target: { node: "n-sub", port: "i" }, kind: "k-call" },
      ],
    },
  }),
  listNodeTypes: async () => [{ id: "t-a", title: "타입 에이" }],
  listEdgeTypes: async () => [
    { id: "k-flow", title: "넘기기류", scheduling: "flow" },
    { id: "k-call", title: "부르기류", scheduling: "none", invocation: { strategy: "s" } },
  ],
  listInteractionKinds: async () => [{ id: "k-free", title: "자유 질문" }],
  listRunEvents: async () => [
    ev(1, "run.started"),
    ev(2, "agent.text_delta", { actor: "pl", node_path: ["n-lead"], payload: { text: "안" } }),
    ev(3, "agent.text_delta", { actor: "pl", node_path: ["n-lead"], payload: { text: "녕" } }),
    ev(4, "edge.traversed", { payload: { edge_id: "e-flow" } }),
    ev(5, "agent.subagent_started", { actor: "pl", node_path: ["n-lead"], payload: { name: "n-sub" } }),
    ev(6, "agent.subagent_started", { actor: "pl", node_path: ["n-lead"], payload: { name: "n-sub" } }),
    ev(7, "hook.completed", { actor: "pl", node_path: ["n-lead"], payload: { event: "PreToolUse", duration_ms: 12 } }),
    ev(8, "mcp.call_completed", { actor: "be", node_path: ["n-wait"], payload: { server: "srv", tool: "tl", duration_ms: 30, is_error: true } }),
  ],
  getRunTrace: async () => ({
    run_id: "r1",
    spans: [
      { id: "s1", kind: "node", node_id: "n-lead", actor: "pl", status: "running", started_at: now - 90, usage: { input_tokens: 10, output_tokens: 5 } },
      { id: "s2", kind: "delegated", parent_id: "s1", node_id: "n-sub", actor: "be", status: "succeeded", started_at: now - 80, ended_at: now - 70, usage: { total_tokens: 3200 }, task_preview: "과제 설명" },
      { id: "s3", kind: "interaction", parent_id: "s1", node_id: "n-wait", interaction_id: "i1", status: "waiting", started_at: now - 12 },
    ],
    links: [],
  }),
  listRunInteractions: async () => [pendingI, answeredI],
  ...extra,
});

describe("실행 상세", () => {
  it("헤더: 응답 대기 칩·배너·토큰·사용자 대기 포함 문구, 그래프에는 실행 상태가 props로 내려간다", async () => {
    mount("/runs/r1", detailOverrides());
    expect(await screen.findByText("응답을 기다리는 요청 1건")).toBeTruthy();
    expect(screen.getByText("토큰 입력 1,204 / 출력 340")).toBeTruthy();
    expect(screen.getByText(/\(사용자 대기 .* 포함\)/)).toBeTruthy();
    const graph = await screen.findByTestId("graph");
    expect(graph.getAttribute("data-mode")).toBe("readonly-run");
    const props = JSON.parse(graph.getAttribute("data-props") ?? "{}");
    expect(props.waitingNodes["n-wait"]).toBeTruthy();
    expect(props.edgeOrder).toEqual({ "e-flow": 1 });
    expect(props.edgeCounts).toEqual({ "e-call": 2 });
    expect(props.badges).toEqual({ "n-sub": ["×2"] });
    expect(props.nodeStates["n-sub"].status).toBe("running");
  });

  it("위임 흐름 탭: 서브에이전트는 들여 쓴 자식 행, 방식 배지는 연결 종류 title, 상세에는 총 토큰만 안내", async () => {
    mount("/runs/r1", detailOverrides());
    const tree = await screen.findByRole("tree", { name: "위임 흐름" });
    const items = within(tree).getAllByRole("treeitem");
    expect(items.length).toBe(3);
    // 5.2R.16: 방식·세션은 글자 칩이 아니라 아이콘(aria-label + 툴팁)이다
    expect(await within(tree).findByRole("img", { name: "부르기류" })).toBeTruthy();
    expect(within(tree).getAllByRole("img", { name: "같은 세션" }).length).toBeGreaterThan(0);
    fireEvent.click(items[1]!);
    expect(await screen.findByText(/총 토큰 3,200만 제공됩니다/)).toBeTruthy();
    expect(screen.getByText("과제 설명", { exact: false })).toBeTruthy();
  });

  it("에이전트 탭: actor 목록(서브에이전트 칩), 텍스트 조각 합침, actor 필터가 URL에 남는다", async () => {
    const { router } = mount("/runs/r1?tab=agents", detailOverrides());
    const list = await screen.findByRole("listbox", { name: "에이전트 목록" });
    expect(within(list).getAllByRole("option").length).toBe(3);
    expect(await screen.findByText("텍스트 2자")).toBeTruthy();
    fireEvent.click(within(list).getByRole("button", { name: /백엔드 리더/ }));
    await waitFor(() => expect(router.state.location.search).toContain("actor=be"));
    expect(screen.queryByText("텍스트 2자")).toBeNull();
  });

  it("hook·MCP 탭: 접두 세그먼트는 데이터에서, 집계 줄·오류만 필터", async () => {
    mount("/runs/r1?tab=observe", detailOverrides());
    const table = await screen.findByRole("table", { name: "hook·MCP 호출" });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(screen.getByText(/hook 1건 · mcp 1건 · 오류 1건 · 평균 21ms/)).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox", { name: "오류만" }));
    expect(within(table).getAllByRole("row")).toHaveLength(2);
    fireEvent.click(within(table).getByText("srv · tl", { exact: false }));
    expect(await screen.findByLabelText("상세")).toBeTruthy();
  });

  it("hook·MCP 탭: 관측 이벤트가 없으면 켜져 있지 않을 수 있다는 안내와 설정 링크", async () => {
    mount("/runs/r1?tab=observe", detailOverrides({ listRunEvents: async () => [ev(1, "run.started")] }));
    expect(await screen.findByText(/꺼져 있을 수 있습니다/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "공통 설정 열기" }).getAttribute("href")).toBe("/settings");
  });

  it("상호작용 탭: 요약, 대기 요청은 같은 카드로 여기서 답하고(스키마 폼), 닫힌 요청은 대기 시간·응답자를 보인다", async () => {
    const respondInteraction = vi.fn(async () => ({ ...pendingI, status: "answered" as const }));
    mount("/runs/r1?tab=interactions", detailOverrides({ respondInteraction }));
    expect(await screen.findByText(/총 2건 · 응답 대기 1 · 평균 응답 시간 20초/)).toBeTruthy();
    expect(screen.getByText("응답자 사용자")).toBeTruthy();
    expect(screen.getByText(/대기 20초/)).toBeTruthy();
    const input = await screen.findByLabelText("답장");
    fireEvent.change(input, { target: { value: "네" } });
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    await waitFor(() => expect(respondInteraction).toHaveBeenCalledWith("r1", "i1", { reply: "네" }));
  });

  it("이미 닫힌 요청(409)에는 다른 곳에서 먼저 응답했을 수 있다는 안내", async () => {
    const { ApiError } = await import("@agent-console/api-client");
    const respondInteraction = vi.fn(async () => {
      throw new ApiError(409, { code: "interaction_closed", message: "closed" });
    });
    mount("/runs/r1?tab=interactions", detailOverrides({ respondInteraction }));
    fireEvent.click(await screen.findByRole("button", { name: "보내기" }));
    expect(await screen.findByText(/이미 닫힌 요청입니다/)).toBeTruthy();
  });

  it("대기 중 노드를 그래프에서 고르면 상호작용 탭으로 바뀌고, 노드 탭은 그 노드를 보여 준다", async () => {
    const { router } = mount("/runs/r1", detailOverrides());
    fireEvent.click(await screen.findByRole("button", { name: "노드 선택" }));
    await waitFor(() => expect(router.state.location.search).toContain("tab=interactions"));
    expect(router.state.location.search).toContain("node=n-wait");
    expect(screen.getByRole("tab", { name: /상호작용/ }).getAttribute("aria-selected")).toBe("true");
  });

  it("취소: 확인 문구에 대기 요청 수가 있고, 확인하면 cancelRun", async () => {
    const cancelRun = vi.fn(async () => run("r1", "cancelled"));
    mount("/runs/r1", detailOverrides({ cancelRun }));
    fireEvent.click(await screen.findByRole("button", { name: "취소" }));
    expect(await screen.findByText(/응답을 기다리는 요청 1건은 취소됩니다/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "실행 취소" }));
    await waitFor(() => expect(cancelRun).toHaveBeenCalledWith("r1"));
  });

  it("실행 당시 버전이 없으면 현재 팀 구성으로 그리고 안내 배너", async () => {
    const getGraph = async () => ({ graph: { id: "g1", name: "개발 팀", nodes: [], edges: [] }, version_hash: "v2" });
    mount("/runs/r1", detailOverrides({ getGraphVersion: async () => { throw new Error("no"); }, getGraph }));
    expect(await screen.findByText(/실행 당시의 팀 구성을 찾지 못해/)).toBeTruthy();
  });

  it("없는 실행(404)은 안내와 목록 링크", async () => {
    const { ApiError } = await import("@agent-console/api-client");
    mount("/runs/zzz", { getRun: async () => { throw new ApiError(404, { code: "not_found", message: "없음" }); } });
    expect(await screen.findByText("실행을 찾을 수 없습니다", { selector: "h2" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "실행 기록으로" })).toBeTruthy();
  });

  it("중단된 실행은 서버 재시작 안내 배너", async () => {
    mount("/runs/r1", detailOverrides({ getRun: async () => ({ run: run("r1", "interrupted", { ended_at: now }), node_runs: [], last_seq: 1 }), listRunInteractions: async () => [] }));
    expect(await screen.findByText(/서버가 다시 시작되어 이 실행은 중단되었습니다/)).toBeTruthy();
  });

  it("실시간 이벤트(WS): 마지막 seq 이후부터 구독하고, 같은 seq는 한 번만 적용하며 새 이벤트가 그래프 상태에 반영된다", async () => {
    const handlers: Array<(e: RunEvent) => void> = [];
    const subscribeRun = vi.fn((_id: string, h: (e: RunEvent) => void) => {
      handlers.push(h);
      return { topic: "run:r1", unsubscribe: vi.fn() };
    });
    mount("/runs/r1", detailOverrides(), ({ ws }) => {
      ws.subscribeRun = subscribeRun as never;
    });
    const graph = await screen.findByTestId("graph");
    await waitFor(() => expect(subscribeRun).toHaveBeenCalled());
    expect((subscribeRun.mock.calls[0] as unknown[])[2]).toEqual({ sinceSeq: 8 });
    const counts = () => JSON.parse(graph.getAttribute("data-props") ?? "{}").edgeCounts["e-call"];
    expect(counts()).toBe(2);
    const started = ev(9, "agent.subagent_started", { actor: "pl", node_path: ["n-lead"], payload: { name: "n-sub" } });
    act(() => handlers[0]!(started));
    await waitFor(() => expect(counts()).toBe(3));
    act(() => handlers[0]!(started));
    expect(counts()).toBe(3);
  });
});

describe("단축키 도움말", () => {
  it("목록과 상세 모두 `?` 도움말에 그 화면 단축키가 나온다", async () => {
    mount("/runs", { listRuns: async () => [run("r-a", "completed")] });
    await screen.findByRole("grid");
    fireEvent.keyDown(document.body, { key: "?" });
    expect(await screen.findByText("실행 검색")).toBeTruthy();
    cleanup();
    mount("/runs/r1", detailOverrides());
    await screen.findByTestId("graph");
    fireEvent.keyDown(document.body, { key: "?" });
    expect(await screen.findByText("위임 흐름 탭")).toBeTruthy();
    expect(screen.getByText("실행 취소")).toBeTruthy();
    expect(screen.getByText("다음 노드 선택")).toBeTruthy();
  });
});

