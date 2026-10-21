import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";
import { conversation, createHarness, turn } from "./testing/chatFakes";

beforeAll(preloadScreens, 120_000);
afterEach(cleanup);

const OPTIONS = [
  { id: "b-real", title: "실제 백엔드", description: "모델을 호출합니다", cost_note: "구독 또는 API 사용량이 소모됩니다" },
  { id: "b-fake", title: "체험 백엔드", description: "모델을 부르지 않습니다", ui_hints: { badge: "체험" } },
];
const unresolved = () =>
  new ApiError(422, {
    code: "backend.unresolved",
    message: "백엔드가 정해지지 않았습니다",
    details: { nodes: [{ id: "n1", label: "안내원" }], options: OPTIONS },
    fix: { actions: [{ label: "기본값으로 지정", target: { role: "settings", section: "common" }, focus: "/backend" }] },
  });

function mount(h: ReturnType<typeof createHarness>) {
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: ["/chat/c1"] });
  render(<AppRoot createClients={async () => h.clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
  return router;
}

describe("백엔드 해결 카드(채팅)", () => {
  it("미지정이면 실패 대신 카드가 뜨고, 고르면 기본값을 저장한 뒤 같은 메시지를 다시 보낸다", async () => {
    let first = true;
    const post = vi.fn(async (...args: unknown[]) => {
      void args;
      if (first) {
        first = false;
        throw unresolved();
      }
      return { run: { id: "r9", status: "running" } };
    });
    const put = vi.fn(async (value: unknown) => ({ value, version_hash: "s2" }));
    const h = createHarness({
      listTurns: async () => [turn({ status: "completed", interactions: [] })],
      getConversation: async () => conversation({ id: "c1" }),
      getSettingsVersioned: async () => ({ value: { chat: { send_key: "enter" } }, version_hash: "s1" }),
      putSettingsVersioned: put,
      postMessage: post,
    });
    mount(h);
    const box = (await screen.findByLabelText("메시지 입력")) as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "안녕" } });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    const card = await screen.findByTestId("backend-chooser");
    expect(within(card).getByText(/'안내원'/)).toBeTruthy();
    expect(within(card).getByText("구독 또는 API 사용량이 소모됩니다")).toBeTruthy();
    expect(within(card).getByText("체험")).toBeTruthy();
    expect(box.value).toBe("안녕");
    const submit = within(card).getByRole("button", { name: "선택하고 계속" }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true); // 기본 선택 없음
    fireEvent.click(within(card).getByRole("radio", { name: /체험 백엔드/ }));
    fireEvent.click(submit);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(put).toHaveBeenCalledWith(expect.objectContaining({ agent_defaults: { backend: "b-fake" } }), "s1");
    expect(post).toHaveBeenLastCalledWith("c1", { text: "안녕" });
    await waitFor(() => expect(screen.queryByTestId("backend-chooser")).toBeNull());
  });

  it("실행을 막는 오류의 해결 버튼이 입력창 위 배너에 달린다", async () => {
    const post = vi.fn(async () => {
      throw new ApiError(422, {
        code: "team.no_entry",
        message: "입구가 없습니다",
        fix: { actions: [{ label: "설정에서 고치기", target: { role: "settings", section: "common" } }] },
      });
    });
    const h = createHarness({
      listTurns: async () => [turn({ status: "completed", interactions: [] })],
      getConversation: async () => conversation({ id: "c1" }),
      getSettingsVersioned: async () => ({ value: { chat: { send_key: "enter" } }, version_hash: "s1" }),
      postMessage: post,
    });
    mount(h);
    const box = await screen.findByLabelText("메시지 입력");
    fireEvent.change(box, { target: { value: "안녕" } });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    expect(await screen.findByText("입구가 없습니다")).toBeTruthy();
    expect(await screen.findByRole("button", { name: "설정에서 고치기" })).toBeTruthy();
  });

  it("디스크립터 배지가 있는 백엔드로 돌면 응답 머리에 칩과 한 줄 안내가 뜨고 [백엔드 바꾸기]가 카드를 연다", async () => {
    const h = createHarness({
      listTurns: async () => [turn({ status: "completed", interactions: [], replies: [{ edge_id: "ed2", node_id: "n1", agent_id: "ag-1", final: true, text: "되돌림" }] })],
      getConversation: async () => conversation({ id: "c1" }),
      getSettingsVersioned: async () => ({ value: { chat: { send_key: "enter" }, agent_defaults: { backend: "b-fake" } }, version_hash: "s1" }),
      listBackends: async () => OPTIONS,
    });
    mount(h);
    expect((await screen.findAllByTestId("reply-badge"))[0]?.textContent).toBe("체험");
    expect((await screen.findByTestId("backend-badge-note")).textContent).toContain("체험 백엔드로 동작 중입니다");
    fireEvent.click(screen.getByRole("button", { name: "백엔드 바꾸기" }));
    const card = await screen.findByTestId("backend-chooser");
    expect(within(card).getByText("지금 쓰는 실행 백엔드를 바꿉니다.")).toBeTruthy();
    expect(card.textContent).not.toContain("정해지지 않았습니다");
  });
});
