import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { Run } from "@agent-console/contracts";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";
import { createFakeClients } from "../../testing/fakes";

beforeAll(preloadScreens, 120_000);
afterEach(cleanup);

const now = Math.floor(Date.now() / 1000);
const run = (id: string, status: Run["status"] = "completed"): Run => ({ id, graph_id: "g1", graph_version: "v1", status, input: { text: `입력 ${id}` }, origin: "chat", created_at: now - 120, started_at: now - 100 });

function mount(overrides: Record<string, unknown>, path = "/runs") {
  const { clients } = createFakeClients({ listGraphs: async () => [{ id: "g1", name: "개발 팀", version_hash: "v1", node_count: 1, edge_count: 0 }], ...overrides });
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: [path] });
  render(<AppRoot createClients={async () => clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
  return { router, clients };
}

describe("실행 목록 서버 페이지", () => {
  it("[더 불러오기]가 커서로 다음 페이지를 이어 붙이고, 출처가 바뀌면 구분선을 그린다", async () => {
    const runsPage = vi.fn(async (p: { cursor?: string }) =>
      p.cursor === undefined
        ? { items: [run("r1"), run("r2")], next_cursor: "project.AAA", source: "project" }
        : { items: [run("r3")], next_cursor: null, source: "app" },
    );
    mount({ runsPage });
    const table = await screen.findByRole("grid", { name: "실행 목록" });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "더 불러오기" }));
    await waitFor(() => expect(within(screen.getByRole("grid")).getAllByRole("row").filter((r) => r.getAttribute("data-run-id") !== null)).toHaveLength(3));
    expect(runsPage.mock.calls[1]![0]).toMatchObject({ cursor: "project.AAA" });
    expect(screen.getByText("앱에 남은 옛 기록")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "더 불러오기" })).toBeNull();
  });

  it("상태 거르기는 서버 status 질의로 보낸다(클라이언트 거르기 아님)", async () => {
    const runsPage = vi.fn(async () => ({ items: [run("r1", "waiting")], next_cursor: null, source: "project" }));
    mount({ runsPage });
    await screen.findByRole("grid", { name: "실행 목록" });
    fireEvent.click(screen.getByRole("button", { name: "응답 대기만" }));
    await waitFor(() => expect(runsPage.mock.calls.some((c) => (c as unknown as [{ status?: string[] }])[0].status?.join() === "waiting")).toBe(true));
  });
});
