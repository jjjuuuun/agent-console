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

describe("실행 목록 서버 질의(6R.19 잔여)", () => {
  it("자식 숨김은 root_only 서버 질의, 자식 포함·에이전트·대화 거르기도 같은 페이지 경로로 보낸다", async () => {
    const runsPage = vi.fn(async (p: Record<string, unknown>) => ({ items: [run(p["root_only"] === true ? "r1" : "r1")], next_cursor: null, source: "project" }));
    const listRuns = vi.fn(async () => []);
    mount({ runsPage, listRuns }, "/runs?children=1&conv=c1");
    await screen.findByRole("grid", { name: "실행 목록" });
    expect(runsPage.mock.calls[0]![0]).toMatchObject({ conversation_id: "c1" });
    expect(runsPage.mock.calls[0]![0]).not.toHaveProperty("root_only");
    expect(listRuns).not.toHaveBeenCalled();
  });

  it("기본은 root_only=true로 첫 페이지를 읽는다", async () => {
    const runsPage = vi.fn(async (p: Record<string, unknown>) => ({ items: [run(p["root_only"] === true ? "r1" : "r1")], next_cursor: null, source: "project" }));
    mount({ runsPage });
    await screen.findByRole("grid", { name: "실행 목록" });
    expect(runsPage.mock.calls[0]![0]).toMatchObject({ root_only: true });
  });

  it("거르기를 바꾸면 이어 붙인 페이지를 버리고 첫 페이지부터 다시 읽는다", async () => {
    const runsPage = vi.fn(async (p: Record<string, unknown>) =>
      p["cursor"] === undefined
        ? { items: [run(p["root_only"] === true ? "r1" : "x1")], next_cursor: "project.AAA", source: "project" }
        : { items: [run("r2")], next_cursor: null, source: "project" },
    );
    mount({ runsPage });
    await screen.findByRole("grid", { name: "실행 목록" });
    fireEvent.click(screen.getByRole("button", { name: "더 불러오기" }));
    await waitFor(() => expect(document.querySelector("[data-run-id='r2']")).not.toBeNull());
    fireEvent.click(screen.getByRole("checkbox", { name: "자식 실행 포함" }));
    await waitFor(() => expect(document.querySelector("[data-run-id='x1']")).not.toBeNull());
    expect(document.querySelector("[data-run-id='r2']")).toBeNull();
    expect(runsPage.mock.calls.at(-1)![0]).not.toHaveProperty("cursor");
  });

  it("기본 기간(7일)은 since로, 검색어는 q로 서버에 보내고, 바꾸면 첫 페이지부터 다시 읽는다", async () => {
    const runsPage = vi.fn(async (p: Record<string, unknown>) =>
      p["cursor"] === undefined
        ? { items: [run(p["q"] === "스펙" ? "m1" : "r1")], next_cursor: "project.AAA", source: "project" }
        : { items: [run("r2")], next_cursor: null, source: "project" },
    );
    mount({ runsPage });
    await screen.findByRole("grid", { name: "실행 목록" });
    const first = runsPage.mock.calls[0]![0] as { since?: number };
    expect(first).not.toHaveProperty("q");
    expect(Math.abs((first.since ?? 0) - (Date.now() / 1000 - 7 * 86400))).toBeLessThan(60);
    fireEvent.click(screen.getByRole("button", { name: "더 불러오기" }));
    await waitFor(() => expect(document.querySelector("[data-run-id='r2']")).not.toBeNull());
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "스펙" } });
    await waitFor(() => expect(document.querySelector("[data-run-id='m1']")).not.toBeNull());
    expect(document.querySelector("[data-run-id='r2']")).toBeNull();
    const last = runsPage.mock.calls.at(-1)![0];
    expect(last).toMatchObject({ q: "스펙" });
    expect(last).not.toHaveProperty("cursor");
    fireEvent.change(screen.getByLabelText("시작"), { target: { value: "all" } });
    await waitFor(() => expect(runsPage.mock.calls.at(-1)![0]).not.toHaveProperty("since"));
  });
});
