import { cleanup, configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";
import { createHarness, turn, type Harness } from "./testing/chatFakes";
import { sessionViewOf } from "./lib/sessions";

beforeAll(preloadScreens, 120_000);
afterEach(cleanup);
configure({ asyncUtilTimeout: 10_000 });
vi.setConfig({ testTimeout: 30_000 });

function mount(h: Harness) {
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: ["/chat/c1"] });
  return render(<AppRoot createClients={async () => h.clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
}
const sessions = (continuable: boolean, states: string[]) => ({ conversation_id: "c1", continuable, items: states.map((state, i) => ({ node_id: `n${i + 1}`, backend: "be-1", state })) });
const composerBox = async () => (await screen.findByLabelText("메시지 입력")) as HTMLTextAreaElement;

describe("세션 상태 해석(순수)", () => {
  it("continuable 하나로 막는다", () => {
    expect(sessionViewOf(undefined).blocked).toBe(false);
    expect(sessionViewOf(sessions(false, ["missing", "available"])).partial).toBe(true);
    expect(sessionViewOf(sessions(false, ["missing"])).partial).toBe(false);
    expect(sessionViewOf(sessions(true, ["archived", "relocatable"])).info).toBe("archived");
    expect(sessionViewOf(sessions(true, ["relocatable"])).info).toBe("relocatable");
    expect(sessionViewOf(sessions(false, ["archived"])).info).toBeUndefined();
  });
});

describe("대화 화면 세션 기록 없음 배너(screen-projects §4.6.4)", () => {
  it("missing이면 배너를 보이고 전송이 막히며, [새 세션으로 계속] 뒤 한 번만 fresh로 보낸다", async () => {
    let continuable = false;
    let turns: ReturnType<typeof turn>[] = [];
    const h = createHarness({ listTurns: vi.fn(async () => turns), postMessage: vi.fn(async () => { turns = [turn({ run_id: "r2", status: "completed", interactions: [] })]; return { run: { id: "r2", status: "completed" } }; }), getConversationSessions: vi.fn(async () => sessions(continuable, [continuable ? "available" : "missing"])) });
    mount(h);
    const banner = await screen.findByRole("region", { name: /이 앱에는 이 대화의 세션 기록이 없습니다/ });
    expect(within(banner).getByRole("button", { name: "새 대화" })).toBeTruthy();
    fireEvent.change(await composerBox(), { target: { value: "이어서" } });
    expect((screen.getByRole("button", { name: "전송" }) as HTMLButtonElement).disabled || screen.getByRole("button", { name: "전송" }).getAttribute("aria-disabled") === "true").toBe(true);
    fireEvent.click(within(banner).getByRole("button", { name: "새 세션으로 계속" }));
    expect(await screen.findByText("다음 메시지는 이전 맥락 없이 새 세션으로 시작합니다.")).toBeTruthy();
    continuable = true;
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    await waitFor(() => expect(h.rest["postMessage"]).toHaveBeenCalledWith("c1", { text: "이어서", on_missing_session: "fresh" }, null));
    await waitFor(() => expect(screen.queryByRole("region", { name: /세션 기록이 없습니다/ })).toBeNull());
    expect(await screen.findByText("이전 맥락 없이 새 세션으로 시작했습니다")).toBeTruthy();
  });

  it("[취소]로 모드를 풀면 다시 막힌다", async () => {
    const h = createHarness({ listTurns: vi.fn(async () => []), getConversationSessions: vi.fn(async () => sessions(false, ["missing"])) });
    mount(h);
    fireEvent.click(await screen.findByRole("button", { name: "새 세션으로 계속" }));
    fireEvent.click(await screen.findByRole("button", { name: "취소" }));
    expect(await screen.findByRole("button", { name: "새 세션으로 계속" })).toBeTruthy();
  });

  it("archived는 배너 없이 info 줄만 보이고 그대로 보낸다", async () => {
    const h = createHarness({ listTurns: vi.fn(async () => []), getConversationSessions: vi.fn(async () => sessions(true, ["archived"])) });
    mount(h);
    expect(await screen.findByText("이 폴더에 보관된 세션 기록으로 이어 갑니다.")).toBeTruthy();
    expect(screen.queryByRole("region", { name: /세션 기록이 없습니다/ })).toBeNull();
    fireEvent.change(await composerBox(), { target: { value: "계속" } });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    await waitFor(() => expect(h.rest["postMessage"]).toHaveBeenCalledWith("c1", { text: "계속" }, null));
  });
});
