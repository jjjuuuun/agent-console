import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";
import { createHarness, kinds, pending, turn, type Harness } from "./testing/chatFakes";

// 화면은 처음 열 때 내려받는다(lazyScreen). 느린 파일시스템에서 첫 이동이 제한 시간을 넘지 않게 미리 불러온다.
beforeAll(preloadScreens, 120_000);
afterEach(cleanup);

function mount(h: Harness) {
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: ["/chat/c1"] });
  return render(<AppRoot createClients={async () => h.clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
}
const box = () => screen.findByLabelText("메시지 입력") as Promise<HTMLTextAreaElement>;
const type = (el: HTMLElement, value: string) => fireEvent.change(el, { target: { value } });
const cards = () => Array.from(document.querySelectorAll<HTMLElement>("[data-interaction-id]"));
/** 화면의 "답을 쓰는 칸" 수: 입력창(답변 모드면 1) + 카드 안 입력 요소 */
const answerFields = (id: string) => (document.querySelector(`[data-interaction-id="${id}"]`)?.querySelectorAll("textarea, input").length ?? 0) + (document.querySelector('[data-testid="answer-strip"][data-answer-mode="answer"]') ? 1 : 0);

const freeAsk = { questions: [{ question: "어느 환경에 배포할까요?", options: [] }] };
const withKinds = (patch: (k: typeof kinds) => typeof kinds) => ({ listInteractionKinds: async () => patch(kinds) });

describe("되묻기 답 입력칸은 한 곳 (5.7R.40)", () => {
  it("AC1 자유 답 하나: 입력창이 칸, 카드에는 입력칸·[보내기]가 없고 힌트가 있다. 한 번만 응답한다", async () => {
    const h = createHarness({ listTurns: async () => [turn({ interactions: [pending({ payload: freeAsk })] })] });
    mount(h);
    await screen.findByTestId("answer-strip");
    const [card] = cards();
    expect(within(card!).queryByRole("button", { name: /보내기/ })).toBeNull();
    expect(answerFields("i1")).toBe(1);
    expect(within(card!).getByText("아래 입력창에 답하세요")).toBeTruthy();
    expect(card!.getAttribute("aria-label")).toContain("답은 입력창에서");
    const input = await box();
    expect(input.getAttribute("aria-describedby")?.split(" ")).toContain("ac-answer-hint-i1");
    type(input, "스테이징");
    fireEvent.click(screen.getByRole("button", { name: "답하기" }));
    await waitFor(() => expect(h.rest["respondInteraction"]).toHaveBeenCalledTimes(1));
    expect(h.rest["respondInteraction"]).toHaveBeenCalledWith("r1", "i1", { response: "스테이징" });
  });

  it("AC2 선택지가 있으면 카드가 입력을 갖고 입력창은 새 메시지(respond 0)", async () => {
    const h = createHarness({ listTurns: async () => [turn({ interactions: [pending({ payload: { questions: [{ question: "?", options: [{ label: "가" }] }] } })] })] });
    mount(h);
    const input = await box();
    await screen.findByLabelText("답변칸");
    expect(screen.queryByTestId("answer-strip")).toBeNull();
    expect(input.getAttribute("placeholder")).toBe("새 메시지 (질문은 위 카드에서 답하세요)");
    type(input, "다른 일");
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    await waitFor(() => expect(h.rest["postMessage"]).toHaveBeenCalledWith("c1", { text: "다른 일" }));
    expect(h.rest["respondInteraction"]).not.toHaveBeenCalled();
  });

  it("AC3 대기 둘: 각 카드가 자기 칸을 갖고 입력창은 일반 새 메시지", async () => {
    const h = createHarness({ listTurns: async () => [turn({ interactions: [pending({ payload: freeAsk }), pending({ id: "i2", created_at: 1001, payload: freeAsk })] })] });
    mount(h);
    await waitFor(() => expect(cards()).toHaveLength(2));
    expect(screen.queryByTestId("answer-strip")).toBeNull();
    for (const c of cards()) expect(c.querySelectorAll("textarea, input").length).toBeGreaterThan(0);
    type(await box(), "x");
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    await waitFor(() => expect(h.rest["postMessage"]).toHaveBeenCalled());
    expect(h.rest["respondInteraction"]).not.toHaveBeenCalled();
  });

  it("AC4 free_text_path가 없는 임의 종류는 카드", async () => {
    const h = createHarness({ listTurns: async () => [turn({ interactions: [pending({ kind: "kind-w" })] })] });
    mount(h);
    await screen.findByLabelText("고르기");
    expect(screen.queryByTestId("answer-strip")).toBeNull();
    expect((await box()).getAttribute("placeholder")).toBe("새 메시지 (질문은 위 카드에서 답하세요)");
  });

  it("AC5 ui_hints.answer_surface=card이면 자유 답도 카드, 모르는 값은 auto", async () => {
    const card = withKinds((k) => [{ ...k[0]!, ui_hints: { renderer: "renderer-x", answer_surface: "card" } }, k[1]!]);
    mount(createHarness({ ...card, listTurns: async () => [turn({ interactions: [pending({ payload: freeAsk })] })] }));
    await screen.findByLabelText("답변칸");
    expect(screen.queryByTestId("answer-strip")).toBeNull();
    cleanup();
    const odd = withKinds((k) => [{ ...k[0]!, ui_hints: { renderer: "renderer-x", answer_surface: "???" } }, k[1]!]);
    mount(createHarness({ ...odd, listTurns: async () => [turn({ interactions: [pending({ payload: freeAsk })] })] }));
    await screen.findByTestId("answer-strip");
  });

  it("AC6 설정 chat.answer_with_composer=false이면 카드", async () => {
    const h = createHarness({
      getSettingsVersioned: async () => ({ value: { chat: { answer_with_composer: false } }, version_hash: "s" }),
      listTurns: async () => [turn({ interactions: [pending({ payload: freeAsk })] })],
    });
    mount(h);
    await screen.findByLabelText("답변칸");
    await waitFor(() => expect(screen.queryByTestId("answer-strip")).toBeNull());
  });

  it("AC8 전환: 대기가 늘면 입력창 내용은 유지되고 토스트가 한 번, 하나 남으면 입력창 쪽으로 돌아온다", async () => {
    const h = createHarness({ listTurns: async () => [turn({ interactions: [pending({ payload: freeAsk })] })] });
    mount(h);
    await screen.findByTestId("answer-strip");
    const input = await box();
    type(input, "쓰던 글");
    act(() => h.ws.emitInteraction(pending({ id: "i2", created_at: 1001, payload: freeAsk })));
    await waitFor(() => expect(screen.queryByTestId("answer-strip")).toBeNull());
    expect(screen.getAllByText("답 입력칸이 카드로 옮겨졌습니다. 입력창의 내용은 새 메시지로 보내집니다.")).toHaveLength(1);
    expect((await box()).value).toBe("쓰던 글");
    for (const c of cards()) expect(c.querySelectorAll("textarea, input").length).toBeLessThanOrEqual(1);
    // 하나 닫히면 다시 입력창이 칸. 카드에 쓰던 초안은 입력창이 비어 있지 않으므로 버려진다
    act(() => h.ws.emitInteraction(pending({ id: "i2", created_at: 1001, status: "answered", closed_at: 1100, payload: freeAsk })));
    await screen.findByTestId("answer-strip");
    expect((await box()).value).toBe("쓰던 글");
    expect(screen.getByText("답 입력칸이 입력창으로 옮겨졌습니다.")).toBeTruthy();
  });

  it("AC8 E→A: 카드 초안이 있고 입력창이 비어 있으면 초안이 입력창으로 옮겨진다", async () => {
    // 초안 이동은 카드가 알려 주는 자유 텍스트(choices 렌더러)일 때 동작한다
    const h = createHarness({ ...withKinds((k) => [{ ...k[0]!, ui_hints: { renderer: "choices" } }, k[1]!]), listTurns: async () => [turn({ interactions: [pending({ payload: freeAsk }), pending({ id: "i2", created_at: 1001, payload: freeAsk })] })] });
    mount(h);
    await waitFor(() => expect(cards()).toHaveLength(2));
    const second = cards()[1]!.querySelector("textarea") as HTMLTextAreaElement;
    fireEvent.change(second, { target: { value: "카드 초안" } });
    act(() => h.ws.emitInteraction(pending({ status: "answered", closed_at: 1100, payload: freeAsk })));
    await screen.findByTestId("answer-strip");
    expect((await box()).value).toBe("카드 초안");
  });

  it("AC9 토글 '새 메시지'면 respond 0·Alt+Shift+A로 전환, Ctrl+Shift+Enter는 모드를 바꾸지 않는다", async () => {
    const h = createHarness({ listTurns: async () => [turn({ interactions: [pending({ payload: freeAsk })] })] });
    mount(h);
    const strip = await screen.findByTestId("answer-strip");
    const input = await box();
    fireEvent.keyDown(input, { key: "A", code: "KeyA", altKey: true, shiftKey: true });
    expect(strip.getAttribute("data-answer-mode")).toBe("message");
    expect(screen.getByText(/아직 기다리는 중/)).toBeTruthy();
    fireEvent.keyDown(input, { key: "A", code: "KeyA", altKey: true, shiftKey: true });
    expect(strip.getAttribute("data-answer-mode")).toBe("answer");
    type(input, "이번만 메시지");
    fireEvent.keyDown(input, { key: "Enter", ctrlKey: true, shiftKey: true });
    await waitFor(() => expect(h.rest["postMessage"]).toHaveBeenCalledWith("c1", { text: "이번만 메시지" }));
    expect(h.rest["respondInteraction"]).not.toHaveBeenCalled();
    expect(screen.getByTestId("answer-strip").getAttribute("data-answer-mode")).toBe("answer");
  });

  it("AC10 헤더의 [응답 대기] 칩은 입력창 답변이면 입력창에, 카드 답변이면 카드에 포커스한다", async () => {
    const h = createHarness({ listTurns: async () => [turn({ interactions: [pending({ payload: freeAsk })] })] });
    mount(h);
    await screen.findByTestId("answer-strip");
    fireEvent.click(await screen.findByRole("button", { name: /응답 대기 1/ }));
    expect(document.activeElement).toBe(await box());
  });
});
