import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { beforeAll, afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";

// 화면은 처음 열 때 내려받는다(lazyScreen). 느린 파일시스템에서 첫 이동이 제한 시간을 넘지 않게 미리 불러온다.
beforeAll(preloadScreens, 120_000);
import { conversation, createHarness, pending, turn, type Harness } from "./testing/chatFakes";

afterEach(cleanup);

function mount(h: Harness, path = "/chat/c1") {
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: [path] });
  const view = render(<AppRoot createClients={async () => h.clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
  return { router, ...view };
}

const composer = () => screen.findByLabelText("메시지 입력") as Promise<HTMLTextAreaElement>;
const type = (el: HTMLElement, value: string) => fireEvent.change(el, { target: { value } });

describe("대화 목록", () => {
  it("응답 대기 대화가 맨 위에 오고 대기 칩이 보인다", async () => {
    const h = createHarness();
    mount(h, "/chat");
    const list = await screen.findByRole("listbox", { name: "대화 목록" });
    const rows = await within(list).findAllByRole("option");
    expect(rows[0]!.textContent).toContain("로그인 화면 스펙");
    expect(rows[0]!.textContent).toContain("응답 대기 1");
    expect(rows[1]!.textContent).toContain("버그 원인 분석");
  });

  it("chat.list_sort가 갱신순이면 응답 대기와 상관없이 최근 갱신이 위", async () => {
    const h = createHarness({
      getSettingsVersioned: async () => ({ value: { chat: { list_sort: "updated" } }, version_hash: "s" }),
    });
    mount(h, "/chat");
    const rows = await within(await screen.findByRole("listbox", { name: "대화 목록" })).findAllByRole("option");
    await waitFor(() => expect(within(screen.getByRole("listbox", { name: "대화 목록" })).getAllByRole("option")[0]!.textContent).toContain("버그 원인 분석"));
    expect(rows.length).toBe(2);
  });

  it("대화 하나 없고 팀 구성도 없으면 안내와 시작하기 카드", async () => {
    const h = createHarness({ listConversations: async () => [], listGraphs: async () => [], listAgents: async () => [] });
    mount(h, "/chat");
    expect(await screen.findByRole("region", { name: "시작하기" })).toBeTruthy();
    expect(screen.queryByText("먼저 팀 구성을 만드세요")).toBeNull();
  });
});

describe("새 대화", () => {
  it("입구 없는 팀 구성은 선택할 수 없고 사유와 편집 링크를 보인다", async () => {
    const h = createHarness();
    const { router } = mount(h, "/chat");
    fireEvent.click(await screen.findByRole("button", { name: "+ 새 대화" }));
    const dialog = await screen.findByRole("dialog", { name: "새 대화" });
    const noEntry = within(dialog).getByRole("radio", { name: /입구 없는 팀/ });
    expect(noEntry.getAttribute("aria-disabled")).toBe("true");
    expect(within(dialog).getByText("사용자 메시지 입구가 없습니다")).toBeTruthy();
    expect(within(dialog).getByRole("link", { name: "팀 구성 편집 →" }).getAttribute("href")).toBe("/teams/g2");
    fireEvent.click(noEntry);
    expect(noEntry.getAttribute("aria-checked")).toBe("false");
    // 팀 셋을 골라 시작하면 만들고 그 대화로 이동한다
    fireEvent.click(within(dialog).getByRole("radio", { name: /팀 셋/ }));
    type(within(dialog).getByLabelText("제목 (선택)"), "새 제목");
    fireEvent.click(within(dialog).getByRole("button", { name: "시작" }));
    await waitFor(() => expect(h.rest["createConversation"]).toHaveBeenCalledWith({ graph_id: "g3", title: "새 제목" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/chat/c9"));
  });

  it("선택 가능한 행에서도 E 키로 그 팀 구성 편집으로 이동한다", async () => {
    const h = createHarness();
    const { router } = mount(h, "/chat");
    fireEvent.click(await screen.findByRole("button", { name: "+ 새 대화" }));
    const dialog = await screen.findByRole("dialog", { name: "새 대화" });
    const ok = within(dialog).getByRole("radio", { name: /팀 셋/ });
    fireEvent.keyDown(ok, { key: "e" });
    await waitFor(() => expect(router.state.location.pathname).toBe("/teams/g3"));
  });

  it("전부 선택할 수 없어도 첫 라디오 행이 탭 정지(tabIndex 0)다", async () => {
    const h = createHarness({
      listGraphs: async () => [
        { id: "g2", name: "입구 없는 팀", version_hash: "h2", node_count: 1, edge_count: 0, entry_labels: [] },
        { id: "g4", name: "입구 없는 팀 둘", version_hash: "h4", node_count: 1, edge_count: 0, entry_labels: [] },
      ],
    });
    mount(h, "/chat");
    fireEvent.click(await screen.findByRole("button", { name: "+ 새 대화" }));
    const dialog = await screen.findByRole("dialog", { name: "새 대화" });
    const rows = within(dialog).getAllByRole("radio");
    expect(rows.map((r) => r.getAttribute("tabindex"))).toEqual(["0", "-1"]);
  });
});

describe("열린 대화와 입력창 답변 모드", () => {
  it("대기 카드와 답변 띠가 보이고, 입력창 전송이 free_text_path 자리로 응답한다", async () => {
    const h = createHarness();
    mount(h);
    const card = await screen.findByRole("group", { name: /임의 질문/ });
    expect(card.getAttribute("aria-label")).toContain("하나 · 역할 일");
    const strip = await screen.findByTestId("answer-strip");
    expect(strip.textContent).toContain("하나 · 역할 일의 임의 질문에 답하는 중");
    const box = await composer();
    type(box, "이메일로 하자");
    fireEvent.click(screen.getByRole("button", { name: "답하기" }));
    await waitFor(() => expect(h.rest["respondInteraction"]).toHaveBeenCalledWith("r1", "i1", { response: "이메일로 하자" }));
    await waitFor(() => expect((box as HTMLTextAreaElement).value).toBe(""));
  });

  it("[새 메시지로 보내기]로 바꾸면 메시지 전송(postMessage)이 된다", async () => {
    const h = createHarness();
    mount(h);
    fireEvent.click(await screen.findByRole("button", { name: "새 메시지로 보내기" }));
    expect((await screen.findByTestId("answer-strip")).getAttribute("data-answer-mode")).toBe("message");
    type(await composer(), "다음 작업");
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    await waitFor(() => expect(h.rest["postMessage"]).toHaveBeenCalledWith("c1", { text: "다음 작업" }));
    expect(h.rest["respondInteraction"]).not.toHaveBeenCalled();
  });

  it("대기 상호작용이 둘이면 답변 모드가 꺼지고 카드에서 답하라고 안내한다", async () => {
    const h = createHarness({
      listTurns: async () => [turn({ interactions: [pending(), pending({ id: "i2", kind: "kind-w", created_at: 1001 })] })],
    });
    mount(h);
    await screen.findAllByRole("group", { name: /응답 대기/ });
    expect(screen.queryByTestId("answer-strip")).toBeNull();
    expect(await screen.findByText("카드에서 답해 주세요 (2건 대기)")).toBeTruthy();
  });

  it("이미 답한 요청(409)이면 안내하고 서버 상태를 반영한다", async () => {
    const h = createHarness({
      respondInteraction: async () => {
        throw new ApiError(409, { code: "interaction_closed", message: "닫힘", details: { interaction: pending({ status: "answered", closed_at: 1002 }) } });
      },
    });
    mount(h);
    type(await composer(), "답");
    fireEvent.click(screen.getByRole("button", { name: "답하기" }));
    expect((await screen.findAllByText(/이미 답했거나 닫힌 요청입니다/)).length).toBeGreaterThan(0);
    // 카드는 서버가 알려 준 현재 상태(답함)로 접힌다
    await waitFor(() => expect(screen.getByRole("group", { name: /답함|응답 대기|임의 질문/ }).getAttribute("data-card-state")).toBe("answered"));
    // 입력한 텍스트는 유지된다(재시도 가능)
    expect((await composer()).value).toBe("답");
  });

  it("모르는 renderer는 스키마 폼으로 그린다", async () => {
    const h = createHarness({ listTurns: async () => [turn({ interactions: [pending({ kind: "kind-w", id: "i7", actor: "ag-2" })] })] });
    mount(h);
    const input = await screen.findByLabelText("고르기");
    type(input, "값");
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    await waitFor(() => expect(h.rest["respondInteraction"]).toHaveBeenCalledWith("r1", "i7", { pick: "값" }));
  });
});

describe("메시지 전송과 대기열", () => {
  const idleTurn = turn({ status: "completed", interactions: [], replies: [{ edge_id: "ed2", node_id: "n1", agent_id: "ag-1", text: "초안입니다", final: true }] });

  it("실행 중이어서 대기열에 들어가면 대기열 행과 안내가 보인다", async () => {
    let queue: unknown[] = [];
    const h = createHarness({
      listTurns: async () => [idleTurn],
      postMessage: async () => {
        queue = [{ queued: true, id: "q1", position: 1, text: "뒤 메시지" }];
        return { queued: queue[0] };
      },
      listQueue: async () => queue,
    });
    mount(h);
    expect(await screen.findByText("초안입니다")).toBeTruthy();
    type(await composer(), "뒤 메시지");
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    expect(await screen.findByText("대기열 #1")).toBeTruthy();
    expect(screen.getByText(/앞 작업이 끝나면 이어서 처리됩니다/)).toBeTruthy();
    expect(screen.queryByText(/서버를 다시 시작하면 사라집니다/)).toBeNull();
  });

  it("거절 정책(409 busy)이면 안내하고 입력은 지우지 않는다", async () => {
    const h = createHarness({
      listTurns: async () => [idleTurn],
      postMessage: async () => {
        throw new ApiError(409, { code: "conversation_busy", message: "busy" });
      },
    });
    mount(h);
    await screen.findByText("초안입니다");
    const box = await composer();
    type(box, "지우면 안 됨");
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    expect(await screen.findByText(/이전 작업이 끝나야 보낼 수 있습니다/)).toBeTruthy();
    expect(box.value).toBe("지우면 안 됨");
  });

  it("대화가 지워졌으면(404) 목록으로 돌아간다", async () => {
    const h = createHarness({
      listTurns: async () => [idleTurn],
      postMessage: async () => {
        throw new ApiError(404, { code: "not_found", message: "없음" });
      },
    });
    const { router } = mount(h);
    await screen.findByText("초안입니다");
    type(await composer(), "x");
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/chat"));
  });

  it("보관된 대화는 입력창이 비활성이고 보관 해제 버튼이 있다", async () => {
    const h = createHarness({ listTurns: async () => [idleTurn], getConversation: async () => ({ ...conversation({ id: "c1" }), archived: true }) });
    mount(h);
    expect(await screen.findByText("보관된 대화입니다.")).toBeTruthy();
    expect(((await composer()) as HTMLTextAreaElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "보관 해제" }));
    await waitFor(() => expect(h.rest["updateConversation"]).toHaveBeenCalledWith("c1", { archived: false }));
  });

  it("입구 없는 팀 구성이면 비활성 + 팀 구성 편집 링크", async () => {
    const h = createHarness({ listTurns: async () => [], getConversation: async () => conversation({ id: "c1", graph_id: "g2" }) });
    mount(h);
    expect(await screen.findByText(/사용자 메시지 입구가 없어 대화를 시작할 수 없습니다/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "팀 구성 편집 →" }).getAttribute("href")).toBe("/teams/g2");
  });
});

describe("실시간", () => {
  it("스트리밍: 빈 placeholder 카드에 텍스트가 쌓이고 run.reply가 오면 확정된다", async () => {
    const h = createHarness({ listTurns: async () => [turn({ status: "running", interactions: [] })] });
    mount(h, "/chat/c1");
    await screen.findByText("로그인 화면 써줘");
    await waitFor(() => expect(h.subscribedRuns()).toEqual(["r1"]));
    act(() => {
      h.emitRunEvent("r1", { type: "node.started", seq: 1, node_path: ["n1"], payload: { status: "running" } });
      h.emitRunEvent("r1", { type: "agent.text_delta", seq: 2, node_path: ["n1"], payload: { text: "안녕" } });
      h.emitRunEvent("r1", { type: "agent.text_delta", seq: 3, node_path: ["n1"], payload: { text: "하세요" } });
    });
    expect(await screen.findByText(/안녕하세요/)).toBeTruthy();
    act(() => {
      h.emitRunEvent("r1", { type: "run.reply", seq: 4, payload: { edge_id: "ed2", node_id: "n1", text: "안녕하세요, 완성본", final: true } });
    });
    expect(await screen.findByText(/완성본/)).toBeTruthy();
  });

  it("진행 줄: 방식 라벨은 연결 종류 디스크립터의 title", async () => {
    const h = createHarness({ listTurns: async () => [turn({ status: "running", interactions: [] })] });
    mount(h);
    await waitFor(() => expect(h.subscribedRuns()).toEqual(["r1"]));
    act(() => {
      h.emitRunEvent("r1", { type: "edge.traversed", seq: 1, payload: { edge_id: "ed3", source: { node: "n1", port: "out" }, target: { node: "n2", port: "in" } } });
      h.emitRunEvent("r1", { type: "node.started", seq: 2, node_path: ["n2"], payload: { status: "running" } });
    });
    const strip = await screen.findByRole("group", { name: "진행 상황" });
    expect(strip.textContent).toContain("하나");
    expect(strip.textContent).toContain("넘기기 방식");
    expect(strip.textContent).toContain("둘");
    expect(strip.textContent).toContain("작업 중");
  });

  it("B-3: 서버가 먼저 끝났다고 알려도 마지막 이벤트를 받을 때까지 구독을 유지해 진행 줄을 채운다", async () => {
    let serverStatus: "running" | "completed" = "running";
    const listTurns = vi.fn(async () => [turn({ status: serverStatus, interactions: [] })]);
    const h = createHarness({ listTurns });
    mount(h);
    await waitFor(() => expect(h.subscribedRuns()).toEqual(["r1"]));
    act(() => h.emitRunEvent("r1", { type: "node.started", seq: 1, node_path: ["n1"], payload: { status: "running" } }));
    // 알림(다른 토픽)이 이벤트보다 먼저 와서 턴 목록이 completed로 바뀐다.
    serverStatus = "completed";
    act(() => h.emitConversation(conversation({ id: "c1", last_status: "completed" })));
    await waitFor(() => expect(listTurns.mock.calls.length).toBeGreaterThanOrEqual(2));
    await new Promise((r) => setTimeout(r, 300));
    expect(h.subscribedRuns()).toEqual(["r1"]);
    act(() => {
      h.emitRunEvent("r1", { type: "edge.traversed", seq: 2, payload: { edge_id: "ed3", source: { node: "n1", port: "out" }, target: { node: "n2", port: "in" } } });
      h.emitRunEvent("r1", { type: "node.completed", seq: 3, node_path: ["n2"], payload: { status: "succeeded" } });
      h.emitRunEvent("r1", { type: "run.completed", seq: 4, payload: { status: "completed" } });
    });
    await waitFor(() => expect(screen.getByRole("group", { name: "진행 상황" }).textContent).toMatch(/진행 1단계/)); // 끝난 턴은 접혀 있다. 서버 완료 알림 뒤에 온 연결 이동도 반영된다(그전엔 단계 0개)
    await waitFor(() => expect(h.subscribedRuns()).toEqual([]));
  });

  it("상호작용 토픽의 갱신으로 카드가 접힌 답함 상태가 된다", async () => {
    const h = createHarness();
    mount(h);
    await screen.findByRole("group", { name: /응답 대기/ });
    act(() => h.ws.emitInteraction(pending({ status: "answered", closed_at: 1010, answered_by: "user" })));
    await waitFor(() => expect(screen.getByRole("group", { name: /임의 질문/ }).getAttribute("data-card-state")).toBe("answered"));
    await waitFor(() => expect(screen.queryByTestId("answer-strip")).toBeNull());
  });
});

describe("중지", () => {
  it("응답 대기 카드가 있으면 확인을 거치고, 없으면 바로 취소한다", async () => {
    const h = createHarness();
    mount(h);
    fireEvent.click(await screen.findByRole("button", { name: /중지/ }));
    const dialog = await screen.findByRole("dialog", { name: "실행을 중지할까요?" });
    expect(within(dialog).getByText("응답을 기다리는 요청 1건이 취소됩니다.")).toBeTruthy();
    expect(h.rest["cancelRun"]).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "중지" }));
    await waitFor(() => expect(h.rest["cancelRun"]).toHaveBeenCalledWith("r1"));
  });

  it("카드가 없으면 확인 없이 취소한다", async () => {
    const h = createHarness({ listTurns: async () => [turn({ status: "running", interactions: [] })] });
    mount(h);
    fireEvent.click(await screen.findByRole("button", { name: /중지/ }));
    await waitFor(() => expect(h.rest["cancelRun"]).toHaveBeenCalledWith("r1"));
  });
});

describe("서버 재시작으로 끊긴 대기", () => {
  it("[답을 새 메시지로 보내기]가 질문을 인용해 입력창을 채운다", async () => {
    const cut = pending({ status: "expired", close_reason: "interrupted", closed_at: 1100, payload: { questions: [{ question: "어느 방식?", options: [{ label: "가" }, { label: "나" }] }] } });
    const h = createHarness({ listTurns: async () => [turn({ status: "interrupted", interactions: [cut] })] });
    mount(h);
    fireEvent.click(await screen.findByRole("button", { name: "답을 새 메시지로 보내기" }));
    const box = await composer();
    await waitFor(() => expect(box.value).toBe("> (하나 · 역할 일의 질문) 어느 방식?\n선택지: 가 / 나\n\n"));
  });
});

describe("팀 구성 전환", () => {
  it("실행이 끝난 대화에서 확인 문구를 보이고 graph_id를 바꾼다", async () => {
    const h = createHarness({ listTurns: async () => [turn({ status: "completed", interactions: [] })] });
    mount(h);
    await screen.findByText("로그인 화면 써줘");
    fireEvent.click(screen.getByRole("button", { name: "팀 구성 바꾸기…" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "팀 구성 바꾸기…" }));
    const dialog = await screen.findByRole("dialog", { name: "팀 구성 바꾸기" });
    expect(within(dialog).getByText(/새 팀 구성에 없는 노드의 세션은 이어 쓰지 않습니다/)).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("radio", { name: /팀 셋/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "바꾸기" }));
    await waitFor(() => expect(h.rest["updateConversation"]).toHaveBeenCalledWith("c1", { graph_id: "g3" }));
  });

  it("실행 중이면 전환 메뉴가 비활성이다", async () => {
    const h = createHarness();
    mount(h);
    await screen.findByRole("group", { name: /응답 대기/ });
    fireEvent.click(screen.getByRole("button", { name: "팀 구성 바꾸기…" }));
    const item = await screen.findByRole("menuitem", { name: /팀 구성 바꾸기/ });
    expect((item as HTMLButtonElement).disabled).toBe(true);
    expect(item.textContent).toContain("실행이 끝난 뒤 바꿀 수 있습니다");
  });
});

describe("검증 요약(계약 v3)과 계획 요약", () => {
  // 임의 이슈 코드·문구: 화면은 코드로 분기하지 않고 서버 문장을 그대로 보인다.
  const graphs = [
    { id: "g1", name: "팀 하나", version_hash: "h1", node_count: 3, edge_count: 3, entry_labels: ["하나"], validation: null },
    { id: "gb", name: "막힌 팀", version_hash: "hb", node_count: 2, edge_count: 1, entry_labels: ["둘"], validation: { blocks_run: true, error_count: 7, warning_count: 0, codes: ["zz.code"] } },
    { id: "gw", name: "경고 팀", version_hash: "hw", node_count: 2, edge_count: 1, entry_labels: ["둘"], validation: { blocks_run: false, error_count: 0, warning_count: 2, codes: ["qq.code"] } },
  ];
  const issues = Array.from({ length: 7 }, (_, i) => ({ severity: "error", code: `zz.code${i}`, message: `서버 문장 ${i} ***`, blocks_run: true }));

  it("blocks_run 팀 구성은 비활성+사유, 문제 보기는 서버 메시지를 그대로 최대 5개 + 외 N건", async () => {
    const h = createHarness({ listGraphs: async () => graphs, validateGraph: vi.fn(async () => issues) });
    mount(h, "/chat");
    fireEvent.click(await screen.findByRole("button", { name: "+ 새 대화" }));
    const dialog = await screen.findByRole("dialog", { name: "새 대화" });
    const blocked = within(dialog).getByRole("radio", { name: /막힌 팀/ });
    expect(blocked.getAttribute("aria-disabled")).toBe("true");
    // 칩·펼침 버튼은 aria-disabled 라디오 밖(같은 항목 안)에 있다
    const item = (id: string) => dialog.querySelector<HTMLElement>(`[data-team-row="${id}"]`)!;
    expect(within(item("gb")).getByText(/실행을 막는 문제 7건/)).toBeTruthy();
    expect(within(blocked).queryByRole("button")).toBeNull();
    fireEvent.click(blocked);
    expect(blocked.getAttribute("aria-checked")).toBe("false");
    fireEvent.click(within(item("gb")).getByRole("button", { name: /문제 보기/ }));
    expect(await within(dialog).findByText("서버 문장 0 ***")).toBeTruthy();
    expect(within(dialog).getAllByText(/^서버 문장 \d \*\*\*/).length).toBe(5);
    expect(within(dialog).getByText("외 2건")).toBeTruthy();
    expect(h.rest["validateGraph"]).toHaveBeenCalledWith("gb");
    // 경고만 있는 팀 구성은 칩만 달고 선택할 수 있다. validation이 null이면 칩이 없다
    const warn = within(dialog).getByRole("radio", { name: /경고 팀/ });
    expect(within(item("gw")).getByText(/경고 2건/)).toBeTruthy();
    fireEvent.click(warn);
    expect(warn.getAttribute("aria-checked")).toBe("true");
    expect(within(item("g1")).queryByText(/건/)).toBeNull();
  });

  it("차단 행에서 Enter는 문제 보기를 펼치고 Space는 선택하지 못한다고 알린다", async () => {
    const h = createHarness({ listGraphs: async () => graphs, validateGraph: async () => issues });
    mount(h, "/chat");
    fireEvent.click(await screen.findByRole("button", { name: "+ 새 대화" }));
    const dialog = await screen.findByRole("dialog", { name: "새 대화" });
    const blocked = within(dialog).getByRole("radio", { name: /막힌 팀/ });
    fireEvent.keyDown(blocked, { key: " " });
    expect(await within(dialog).findByText("선택할 수 없습니다. 실행을 막는 문제가 있습니다")).toBeTruthy();
    fireEvent.keyDown(blocked, { key: "Enter" });
    expect(await within(dialog).findByText("서버 문장 1 ***")).toBeTruthy();
  });

  it("빈 대화 안내 카드는 계획 요약(TeamPlanSummary)에서 입구·답변·되묻기 노드를 읽는다", async () => {
    const h = createHarness({
      listTurns: async () => [],
      getGraphPlan: vi.fn(async () => ({ entries: [{ edge_id: "x", node_id: "n2" }], answers: [{ edge_id: "y", node_id: "n1" }], grants: { u: {} } })),
    });
    mount(h);
    const card = await screen.findByRole("region", { name: /팀 하나|팀 구성/ });
    await waitFor(() => expect(within(card).getByText("둘")).toBeTruthy());
    expect(within(card).getAllByText("하나").length).toBeGreaterThan(0);
    expect(within(card).getByText("사용자")).toBeTruthy();
    expect(h.rest["getGraphPlan"]).toHaveBeenCalledWith("g1");
  });

  it("계획 요약을 못 읽으면 카드에 오류와 다시 시도가 있고 나머지는 동작한다", async () => {
    const h = createHarness({ listTurns: async () => [], getGraphPlan: async () => { throw new ApiError(500, { code: "internal", message: "실패" }); } });
    mount(h);
    expect(await screen.findByText(/요약을 불러오지 못했습니다/)).toBeTruthy();
    expect(await composer()).toBeTruthy();
  });
});
