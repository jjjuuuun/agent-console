import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import type { EdgeTypeDescriptor, Graph } from "@agent-console/contracts";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";
import { createHarness, edgeTypes as baseEdgeTypes, graph as baseGraph, pending, turn, type Harness } from "./testing/chatFakes";

beforeAll(preloadScreens, 120_000);
afterEach(cleanup);

// 모든 종류·이름은 임의 값이다.
const edgeTypes: EdgeTypeDescriptor[] = [
  ...baseEdgeTypes,
  { id: "e-loop", title: "되돌림", scheduling: "flow", cycle: { max_iterations: 3 } },
  { id: "e-call", title: "독립 위임", scheduling: "none", invocation: { strategy: "s" } as never },
];
const parent: Graph = {
  ...baseGraph,
  nodes: [...(baseGraph.nodes ?? []), { id: "sub", type: "nt-a", label: "하위 팀 노드", config: { ref: "ag-2" } }],
  edges: [
    ...(baseGraph.edges ?? []),
    { id: "ed-loop", source: { node: "n2", port: "out" }, target: { node: "n1", port: "in" }, kind: "e-loop" },
    { id: "ed-call", source: { node: "n1", port: "out" }, target: { node: "n2", port: "call" }, kind: "e-call" },
  ],
};
const childGraph: Graph = { id: "g9", name: "자식 팀", nodes: [{ id: "z1", type: "nt-a", label: "자식 일꾼 하나", config: { ref: "ag-1" } }, { id: "z2", type: "nt-a", label: "자식 일꾼 둘", config: { ref: "ag-2" } }], edges: [{ id: "ze", source: { node: "z1", port: "o" }, target: { node: "z2", port: "i" }, kind: "e-flow" }] };

function setup(over: Record<string, unknown> = {}): Harness {
  return createHarness({
    listEdgeTypes: async () => edgeTypes,
    getGraph: async (id: string) => ({ graph: id === "g9" ? childGraph : { ...parent, id }, version_hash: "h" }),
    listTurns: async () => [turn({ status: "running", interactions: [] })],
    ...over,
  });
}
function mount(h: Harness) {
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: ["/chat/c1"] });
  render(<AppRoot createClients={async () => h.clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
  return router;
}
const emit = async (h: Harness, runId: string, seq: number, type: string, payload: Record<string, unknown> = {}, node_path: string[] = []) => {
  await act(async () => h.emitRunEvent(runId, { seq, type, payload, node_path }));
};
async function ready(h: Harness) {
  await screen.findByRole("article");
  await waitFor(() => expect(h.subscribedRuns()).toContain("r1"));
}

describe("채팅 진행 줄: 위임·반복·중첩 팀", () => {
  it("독립 위임 칩: 위임자 아래 들여 쓰고 별도 세션 배지, 연결 종류 제목", async () => {
    const h = setup();
    mount(h);
    await ready(h);
    await emit(h, "r1", 1, "node.started", { status: "running", call: 0 }, ["n1", "n2"]);
    const chip = await screen.findByText("별도 세션");
    expect(chip).toBeTruthy();
    expect(screen.getByText("독립 위임")).toBeTruthy();
  });

  it("반복 시작은 회차(값 + 1) 칩, 한도 도달은 경고 칩", async () => {
    const h = setup();
    mount(h);
    await ready(h);
    await emit(h, "r1", 1, "loop.iteration", { edge_id: "ed-loop", iteration: 1, nodes: ["n1", "n2"] });
    await emit(h, "r1", 2, "loop.exhausted", { edge_id: "ed-loop", iteration: 3, max_iterations: 3 });
    expect(await screen.findByText("2회차")).toBeTruthy();
    expect(screen.getByText("반복 한도 도달 (한도 3회)")).toBeTruthy();
  });

  it("중첩 팀 칩: 부모 Run 상태를 바꾸지 않고, 접힌 채 [실행 상세 ↗] 링크가 있으며 펼치면 자식 단계가 나온다", async () => {
    const h = setup();
    mount(h);
    await ready(h);
    await emit(h, "r1", 1, "run.child_started", { child_run_id: "c1", node_id: "sub", graph_id: "g9" }, ["sub"]);
    // 자식 Run 구독이 생기고 자식 이벤트가 하위 단계로 쌓인다
    await waitFor(() => expect(h.subscribedRuns()).toContain("c1"));
    await emit(h, "c1", 1, "edge.traversed", { edge_id: "ze", source: { node: "z1" }, target: { node: "z2" } });
    const chip = await screen.findByRole("button", { name: /^(?!진행).*자식 팀/ });
    expect(chip.getAttribute("aria-expanded")).toBe("false");
    // 5.2R.21: 헤더의 실행 상세는 글자 없는 아이콘 링크 하나, 턴 푸터의 [실행 상세]도 하나
    expect(screen.getByRole("link", { name: "마지막 실행 상세 열기" }).textContent).toBe("");
    expect(screen.getAllByRole("button", { name: "실행 상세" })).toHaveLength(1);
    expect(screen.getAllByRole("link", { name: /실행 상세/ }).map((l) => l.getAttribute("href"))).toContain("/runs/c1");
    fireEvent.click(chip);
    expect(await screen.findByText("자식 일꾼 둘")).toBeTruthy();
    // 부모 Run은 계속 진행 중이다(자식 알림이 부모 상태를 바꾸지 않는다)
    expect(screen.getByTestId("turn-status").textContent).toContain("실행 중");
  });

  it("자식 실행이 실패하면 오류 블록에 중첩 팀 이름과 [자식 실행에서 원인 보기]", async () => {
    let current = turn({ status: "running", interactions: [] });
    const h = setup({ listTurns: async () => [current] });
    const router = mount(h);
    await ready(h);
    await emit(h, "r1", 1, "run.child_started", { child_run_id: "c1", node_id: "sub", graph_id: "g9" }, ["sub"]);
    await emit(h, "r1", 2, "run.child_finished", { child_run_id: "c1", node_id: "sub", status: "failed" }, ["sub"]);
    await emit(h, "r1", 3, "run.failed", { status: "failed", error: { code: "x", message: "자식이 죽었습니다" } });
    // 서버가 끝났다고 알리면(턴 다시 읽기) 오류 블록이 보인다
    current = turn({ status: "failed", interactions: [] });
    await act(async () => h.emitConversation({ id: "c1", graph_id: "g1", title: "t", created_at: 1, updated_at: 5, last_status: "failed" } as never));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("중첩 팀 ‘자식 팀’에서 실패했습니다");
    fireEvent.click(within(alert).getByRole("button", { name: /자식 실행에서 원인 보기/ }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/runs/c1"));
  });
});

describe("채팅 상호작용 카드: 루트 기준", () => {
  const childAsk = pending({ id: "ci", run_id: "c1", root_run_id: "r1", node_id: "z1", node_path: ["z1"], actor: "ag-1", conversation_id: null, title: "자식이 묻습니다" });

  it("자식 실행의 요청이 같은 턴 카드로 섞여 나오고 중첩 팀 칩·부모 노드 표기가 붙으며 답은 자식 Run에 보낸다", async () => {
    const h = setup({ listTurns: async () => [turn({ status: "waiting", interactions: [childAsk] })] });
    mount(h);
    await screen.findByRole("article");
    await act(async () => h.emitRunEvent("r1", { seq: 1, type: "run.child_started", payload: { child_run_id: "c1", node_id: "sub", graph_id: "g9" }, node_path: ["sub"] }));
    const card = await screen.findByRole("group", { name: /임의 질문/ });
    expect(within(card).getByText("중첩 팀")).toBeTruthy();
    await waitFor(() => expect(card.textContent).toContain("하위 팀 노드(중첩 팀) ›"));
    // 대기 요청이 하나이고 자유 텍스트 하나로 끝나는 모양이면 답은 입력창에서 받는다(카드에는 입력칸이 없다)
    expect(within(card).queryByLabelText("답변칸")).toBeNull();
    fireEvent.change(await screen.findByLabelText("메시지 입력"), { target: { value: "예" } });
    fireEvent.click(screen.getByRole("button", { name: "답하기" }));
    await waitFor(() => expect(h.rest["respondInteraction"]).toHaveBeenCalledWith("c1", "ci", { response: "예" }));
  });

  it("WS로 대화 id 없이 오는 자식 요청도 루트 Run 기준으로 이 대화에 쌓인다", async () => {
    const h = setup();
    mount(h);
    await screen.findByRole("article");
    await waitFor(() => expect(h.ws.subscribeInteractions).toBeDefined());
    await act(async () => (h.ws as unknown as { emitInteraction(i: unknown): void }).emitInteraction({ ...childAsk, status: "pending" }));
    expect(await screen.findByText("자식이 묻습니다")).toBeTruthy();
  });

  it("중지 확인: 진행 중인 중첩 팀이 있으면 한 줄이 더해진다", async () => {
    const h = setup({ listTurns: async () => [turn({ status: "waiting", interactions: [pending()] })] });
    mount(h);
    await ready(h);
    await emit(h, "r1", 1, "run.child_started", { child_run_id: "c1", node_id: "sub", graph_id: "g9" }, ["sub"]);
    await screen.findByRole("button", { name: /^(?!진행).*자식 팀/ });
    fireEvent.click(screen.getByRole("button", { name: /중지/ }));
    expect(await screen.findByText("진행 중인 중첩 팀 실행도 함께 중지됩니다.")).toBeTruthy();
  });
});
