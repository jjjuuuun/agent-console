import { cleanup, configure, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";
import { createHarness, type Harness } from "./testing/chatFakes";

beforeAll(preloadScreens, 120_000);
afterEach(cleanup);
configure({ asyncUtilTimeout: 10_000 });
vi.setConfig({ testTimeout: 30_000 });

const MESSAGE = "프로젝트 실행 연동이 꺼져 있습니다";
const serverInfo = (warn: boolean) => ({
  server_version: "9",
  contracts_version: "1",
  plugins: [],
  attributes: {},
  warnings: warn ? [{ severity: "warning", code: "feature_unavailable", message: MESSAGE, details: { module: "m", port: "runs.scopes" } }] : [],
});
const project = {
  project: { id: "p1", name: "프로젝트 p1", folder: "/w/p1", description: "" },
  status: "ready",
  config_writable: true,
  kinds: [],
  config_dir: ".cfg",
  records_state: "ready",
  records_writable: true,
  version_hash: "h",
};

function mount(opts: { warn: boolean; projectId: string | null }): Harness {
  const h = createHarness({
    getServerInfo: vi.fn(async () => serverInfo(opts.warn)),
    listProjects: vi.fn(async () => [project]),
    listTurns: vi.fn(async () => []),
    getConversation: vi.fn(async () => ({ id: "c1", title: "t", graph_id: "g1", updated_at: 1, created_at: 1, pending_interactions: 0, last_status: "completed", ...(opts.projectId === null ? {} : { project_id: opts.projectId }), sessions: {} })),
  });
  const path = opts.projectId === null ? "/chat/c1" : `/chat/c1?prj=${opts.projectId}`;
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: [path] });
  render(<AppRoot createClients={async () => h.clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
  return h;
}
const send = async () => (await screen.findByRole("button", { name: "전송" })) as HTMLButtonElement;

describe("대화 화면: 실행 연동 꺼짐 신호(5.7R.33t1)", () => {
  it("경고 + 프로젝트 대화 → 보내기가 막히고 서버 문구 배너가 보인다", async () => {
    const h = mount({ warn: true, projectId: "p1" });
    fireEvent.change(await screen.findByLabelText("메시지 입력"), { target: { value: "안녕" } });
    expect((await screen.findAllByText(MESSAGE)).length).toBeGreaterThan(0);
    const btn = await send();
    await waitFor(() => expect(btn.disabled || btn.getAttribute("aria-disabled") === "true").toBe(true));
    fireEvent.click(btn);
    expect(h.rest["postMessage"]).not.toHaveBeenCalled();
  });

  it("경고 + 프로젝트 없는 대화 → 보내기 켜짐", async () => {
    mount({ warn: true, projectId: null });
    fireEvent.change(await screen.findByLabelText("메시지 입력"), { target: { value: "안녕" } });
    const btn = await send();
    expect(btn.disabled || btn.getAttribute("aria-disabled") === "true").toBe(false);
    expect(screen.queryByText(MESSAGE)).toBeNull();
  });

  it("경고 없음 + 프로젝트 대화 → 보내기 켜짐", async () => {
    mount({ warn: false, projectId: "p1" });
    fireEvent.change(await screen.findByLabelText("메시지 입력"), { target: { value: "안녕" } });
    const btn = await send();
    expect(btn.disabled || btn.getAttribute("aria-disabled") === "true").toBe(false);
    expect(screen.queryByText(MESSAGE)).toBeNull();
  });
});
