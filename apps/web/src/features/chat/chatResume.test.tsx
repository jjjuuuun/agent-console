import { cleanup, configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";
import { conversation, createHarness, turn, type Harness } from "./testing/chatFakes";
import { anyRerunnable, canOfferResume, defaultResumeSelection, hasRunningSelected, issuesByNode, isResumed } from "./lib/resume";

beforeAll(preloadScreens, 120_000);
afterEach(cleanup);
configure({ asyncUtilTimeout: 10_000 });
vi.setConfig({ testTimeout: 30_000 });

function mount(h: Harness, path = "/chat/c1") {
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: [path] });
  return render(<AppRoot createClients={async () => h.clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
}

describe("이어 가기 순수 규칙", () => {
  const nodes = [
    { node_id: "a", rerunnable: true, status: "waiting" },
    { node_id: "b", rerunnable: true, status: "running" },
    { node_id: "c", rerunnable: false, status: "waiting" },
  ] as never[];
  it("기본 선택 = rerunnable이면서 응답 대기 중 끊긴 노드만(이름·역할 무관)", () => {
    expect([...defaultResumeSelection(nodes)]).toEqual(["a"]);
    expect(defaultResumeSelection([{ node_id: "x", rerunnable: true, status: "running" }] as never[]).size).toBe(0);
    expect(hasRunningSelected(nodes, new Set(["b"]))).toBe(true);
    expect(hasRunningSelected(nodes, new Set(["a"]))).toBe(false);
    expect(anyRerunnable([{ node_id: "c", rerunnable: false, status: "waiting" }] as never[])).toBe(false);
  });
  it("버튼은 마지막 끊긴 턴에만, 설정이 false면 없다", () => {
    const turns = [{ run_id: "r1", status: "interrupted" }, { run_id: "r2", status: "interrupted" }];
    expect(canOfferResume(turns[1]!, turns, true)).toBe(true);
    expect(canOfferResume(turns[1]!, turns, undefined)).toBe(true);
    expect(canOfferResume(turns[1]!, turns, false)).toBe(false);
    expect(canOfferResume(turns[0]!, turns, true)).toBe(false);
    expect(canOfferResume({ run_id: "r2", status: "completed" }, turns, true)).toBe(false);
    expect(isResumed("r1", [{ resumed_from: "r1" }])).toBe(true);
    expect(issuesByNode({ issues: [{ node_id: "n", message: "m" }, { message: "x" }] })).toEqual({ n: "m" });
  });
});

describe("재시작 뒤 멈춘 대기열", () => {
  function held(extra: Record<string, unknown> = {}) {
    let queue = [
      { queued: true, id: "q1", position: 1, text: "첫째 메시지", held: true },
      { queued: true, id: "q2", position: 2, text: "둘째 메시지", held: true },
    ];
    const release = vi.fn(async (_c: string, qid: string) => {
      queue = queue.map((q) => (q.id === qid ? { ...q, held: false } : q));
      return queue.find((q) => q.id === qid);
    });
    const cancel = vi.fn(async (_c: string, qid: string) => {
      queue = queue.filter((q) => q.id !== qid);
    });
    const h = createHarness({
      listTurns: async () => [turn({ status: "completed", interactions: [] })],
      listQueue: async () => queue,
      releaseQueuedMessage: release,
      cancelQueuedMessage: cancel,
      ...extra,
    });
    return { h, release, cancel };
  }

  it("배너에 멈춘 건수, 행에 멈춤 칩과 [실행]/[취소]. [실행]은 서버 호출 뒤 일반 대기열 칩으로", async () => {
    const { h, release } = held();
    mount(h);
    expect((await screen.findByText(/대기열 2건이 멈춰 있습니다/)).closest("[role]")).toBeTruthy();
    expect(await screen.findByText(/멈춤 #1/)).toBeTruthy();
    const row = screen.getByText("첫째 메시지").closest("[data-queued]") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "실행" }));
    await waitFor(() => expect(release).toHaveBeenCalledWith("c1", "q1"));
    expect(await screen.findByText("대기열 #1")).toBeTruthy();
    await waitFor(() => expect(screen.getByText(/대기열 1건이 멈춰 있습니다/)).toBeTruthy());
  });

  it("[취소]는 확인 없이 DELETE, [입력창으로 가져오기]는 텍스트를 입력창에 넣고 항목을 지운다, [모두 취소]는 확인", async () => {
    const { h, cancel } = held();
    mount(h);
    const row = (await screen.findByText("첫째 메시지")).closest("[data-queued]") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "입력창으로 가져오기" }));
    await waitFor(() => expect(cancel).toHaveBeenCalledWith("c1", "q1"));
    await waitFor(() => expect((screen.getByLabelText("메시지 입력") as HTMLTextAreaElement).value).toBe("첫째 메시지"));
    fireEvent.click(screen.getByRole("button", { name: "모두 취소" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toContain("멈춘 1건을 지웁니다");
    fireEvent.click(within(dialog).getByRole("button", { name: "모두 지우기" }));
    await waitFor(() => expect(cancel).toHaveBeenCalledWith("c1", "q2"));
    await waitFor(() => expect(screen.queryByText(/멈춰 있습니다/)).toBeNull());
  });

  it("실행 실패는 행 아래에 서버 메시지를 보인다", async () => {
    const { h } = held({ releaseQueuedMessage: async () => { throw new ApiError(409, { code: "x", message: "앞 항목이 멈춰 있습니다" }); } });
    mount(h);
    const row = (await screen.findByText("첫째 메시지")).closest("[data-queued]") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "실행" }));
    expect(await within(row).findByText("앞 항목이 멈춰 있습니다")).toBeTruthy();
  });

  it("대화 목록 행에 멈춤 칩(ConversationSummary.held)", async () => {
    const { h } = held({ listConversations: async () => [conversation({ id: "c1", title: "대화", queued: 3, held: 2 })] });
    mount(h, "/chat");
    const list = await screen.findByRole("listbox", { name: "대화 목록" });
    expect(within(list).getByText(/멈춤 2/)).toBeTruthy();
    expect(within(list).getByText("대기열 1")).toBeTruthy();
  });
});

describe("끊긴 턴 이어 가기", () => {
  const interrupted = turn({ run_id: "r1", status: "interrupted", interactions: [] });
  const options = { run_id: "r1", nodes: [
    { node_id: "n-wait", label: "검토 노드", rerunnable: true, status: "waiting" },
    { node_id: "n-run", label: "실행 노드", rerunnable: true, status: "running" },
    { node_id: "n-fixed", label: "고정 노드", rerunnable: false, status: "running" },
  ] };

  it("버튼 -> 옵션 조회 -> 기본은 대기 중이던 rerunnable만 체크 -> 실행하면 resume 호출", async () => {
    const getResumeOptions = vi.fn(async () => options);
    const resumeRun = vi.fn(async () => ({ id: "r2", status: "running" }));
    const h = createHarness({ listTurns: async () => [interrupted], getResumeOptions, resumeRun });
    mount(h);
    expect(getResumeOptions).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button", { name: "이 지점부터 다시 실행" }));
    const dialog = await screen.findByRole("dialog", { name: "이 지점부터 다시 실행" });
    const wait = (await within(dialog).findByRole("checkbox", { name: "검토 노드" })) as HTMLInputElement;
    const run = within(dialog).getByRole("checkbox", { name: "실행 노드" }) as HTMLInputElement;
    const fixed = within(dialog).getByRole("checkbox", { name: "고정 노드" }) as HTMLInputElement;
    expect([wait.checked, run.checked, fixed.checked]).toEqual([true, false, false]);
    expect(fixed.disabled).toBe(true);
    expect(within(dialog).queryByText(/사용량이 늘 수 있습니다/)).toBeNull();
    fireEvent.click(run);
    expect(within(dialog).getByText(/사용량이 늘 수 있습니다/)).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: /^다시 실행/ }));
    await waitFor(() => expect(resumeRun).toHaveBeenCalledWith("r1", ["n-wait", "n-run"]));
  });

  it("422는 해당 행에 서버 메시지를 붙이고 체크를 풀며, 선택이 없으면 실행이 비활성", async () => {
    const resumeRun = vi.fn(async () => {
      throw new ApiError(422, { code: "validation_failed", message: "v", details: { issues: [{ node_id: "n-wait", message: "다시 실행할 수 없습니다" }] } });
    });
    const h = createHarness({ listTurns: async () => [interrupted], getResumeOptions: async () => options, resumeRun });
    mount(h);
    fireEvent.click(await screen.findByRole("button", { name: "이 지점부터 다시 실행" }));
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByRole("checkbox", { name: "검토 노드" });
    fireEvent.click(within(dialog).getByRole("button", { name: /^다시 실행/ }));
    expect(await within(dialog).findByText("다시 실행할 수 없습니다")).toBeTruthy();
    expect((within(dialog).getByRole("checkbox", { name: "검토 노드" }) as HTMLInputElement).checked).toBe(false);
    expect((within(dialog).getByRole("button", { name: /^다시 실행/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("409/404는 서버 메시지를 토스트로 알리고 옵션을 다시 읽는다(행 오류 아님)", async () => {
    const resumeRun = vi.fn(async () => {
      throw new ApiError(409, { code: "run_not_interrupted", message: "이미 이어 간 실행입니다" });
    });
    const getResumeOptions = vi.fn(async () => options);
    const h = createHarness({ listTurns: async () => [interrupted], getResumeOptions, resumeRun });
    mount(h);
    fireEvent.click(await screen.findByRole("button", { name: "이 지점부터 다시 실행" }));
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByRole("checkbox", { name: "검토 노드" });
    fireEvent.click(within(dialog).getByRole("button", { name: /^다시 실행/ }));
    expect(await screen.findByText("이미 이어 간 실행입니다")).toBeTruthy();
    await waitFor(() => expect(getResumeOptions.mock.calls.length).toBeGreaterThan(1));
    expect(resumeRun).toHaveBeenCalledTimes(1);
  });

  it("nodes가 비었거나 rerunnable이 없으면 빈 상태", async () => {
    const h = createHarness({ listTurns: async () => [interrupted], getResumeOptions: async () => ({ run_id: "r1", nodes: [] }) });
    mount(h);
    fireEvent.click(await screen.findByRole("button", { name: "이 지점부터 다시 실행" }));
    expect(await screen.findByText("다시 실행할 수 있는 지점이 없습니다")).toBeTruthy();
  });

  it("chat.offer_resume=false면 버튼을 그리지 않는다", async () => {
    const h = createHarness({
      listTurns: async () => [interrupted],
      getSettingsVersioned: async () => ({ value: { chat: { offer_resume: false } }, version_hash: "s" }),
    });
    mount(h);
    await screen.findByText("로그인 화면 써줘");
    await waitFor(() => expect(screen.queryByRole("button", { name: "이 지점부터 다시 실행" })).toBeNull());
  });

  it("이어 간 턴은 칩과 함께 같은 턴처럼 보이고(사용자 메시지 중복 없음) 끊긴 배너는 접힌 한 줄", async () => {
    const resumed = turn({ run_id: "r2", status: "running", interactions: [], resumed_from: "r1" });
    const h = createHarness({ listTurns: async () => [interrupted, resumed] });
    mount(h);
    expect(await screen.findByTestId("resumed-chip")).toBeTruthy();
    expect(screen.getByText("끊긴 실행에서 다시 시작함")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "이 지점부터 다시 실행" })).toBeNull();
    expect(screen.getAllByText("로그인 화면 써줘")).toHaveLength(1);
  });
});
