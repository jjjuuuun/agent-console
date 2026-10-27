import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { ArchitectureView, ModuleInfo, Run } from "@agent-console/contracts";
import { sampleCell } from "@agent-console/arch-view/testing";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";
import { createFakeClients } from "../../testing/fakes";

beforeAll(preloadScreens, 120_000);
afterEach(cleanup);
const LONG = { timeout: 20_000 };

vi.mock("@agent-console/graph-editor", () => ({
  createElkEngine: () => ({ id: "fake", title: "fake", options: [], run: async () => ({ positions: {} }) }),
  GraphEditor: () => <div data-testid="graph" />,
}));

const now = Math.floor(Date.now() / 1000);
const run = (id: string, status: Run["status"]): Run => ({ id, graph_id: "g1", graph_version: "v1", status, input: { text: "x" }, origin: "chat", created_at: now - 120, started_at: now - 100 });
const mod = (roles: string[]): ModuleInfo => ({ id: "m-any", kind: "k-any", version: "0.0.1", status: "active", web_roles: roles });
// 칸 이름은 임의 값이다.
const archView = (n: number): ArchitectureView => ({
  profile: "pf-1",
  title: "임의 프로필",
  event_total: n,
  max_seq: n,
  cells: [sampleCell("zz1", { label: "칸가", x: 100, y: 60, metrics: { count: { status: "observed", value: n } }, selector: { arch: "pf-1:cell:zz1" } })],
  edges: [],
});

function mount(roles: string[], status: Run["status"], children: Run[] = [], archCount = () => 3) {
  const base: Record<string, (...args: never[]) => unknown> = {
    listModules: async () => [mod(["runs", "runs:trace", ...roles])],
    listObserveEventPrefixes: async () => [],
    getRun: async () => ({ run: run("r1", status), node_runs: [], last_seq: 1, children }),
    getGraphVersion: async () => ({ kind: "graph", id: "g1", version_hash: "v1", saved_at: 1, content: { id: "g1", name: "팀", nodes: [], edges: [] } }),
    listNodeTypes: async () => [],
    listEdgeTypes: async () => [],
    listInteractionKinds: async () => [],
    listRunEvents: async () => [],
    getRunTrace: async () => ({ run_id: "r1", spans: [], links: [] }),
    listRunInteractions: async () => [],
    getSettingsVersioned: async () => ({ value: {}, version_hash: "s1" }),
    getLogTaxonomy: async () => ({ categories: {} }),
    listLogSources: async () => [],
    listArchitectureProfiles: async () => ({ profiles: [{ id: "pf-1", title: "임의 프로필", origin: "user" }], default_profile: "pf-1" }),
    getLogArchitecture: async () => archView(archCount()),
    listLogEvents: async () => ({ items: [] }),
  };
  const { clients, rest } = createFakeClients(Object.fromEntries(Object.entries(base).map(([k, f]) => [k, vi.fn(f)])));
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: ["/runs/r1?tab=architecture"] });
  render(<AppRoot createClients={async () => clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
  return { rest, router };
}

describe("실행 상세 [구조도] 탭", () => {
  it("역할 logs:architecture와 logs:runs가 모두 없으면 탭이 없고 구조도를 묻지 않는다", async () => {
    const { rest } = mount(["logs:runs"], "completed");
    await screen.findByRole("tablist", { name: "검사 탭" }, LONG);
    expect(screen.queryByRole("tab", { name: "구조도" })).toBeNull();
    expect(rest["getLogArchitecture"]).not.toHaveBeenCalled();
  });

  it("두 역할이 있으면 마지막 탭으로 보이고 scope=run:<id>로 묻는다", async () => {
    const { rest } = mount(["logs:runs", "logs:architecture"], "completed");
    const tabs = await screen.findAllByRole("tab", {}, LONG);
    expect(tabs.at(-1)?.textContent).toContain("구조도");
    await screen.findByRole("region", { name: "구조도" }, LONG);
    expect(rest["getLogArchitecture"]!.mock.calls[0]![0]).toMatchObject({ scope: "run:r1" });
    expect(screen.queryByRole("switch", { name: /자식 실행 포함/ })).toBeNull();
    expect(screen.queryByText(/실행 중 · 갱신/)).toBeNull();
  });

  it("자식 실행이 있으면 [자식 실행 포함] 스위치가 있고 켜면 run-tree 범위로 바꾼다", async () => {
    const { rest } = mount(["logs:runs", "logs:architecture"], "completed", [{ ...run("c1", "completed"), parent_run_id: "r1" }]);
    const sw = await screen.findByRole("switch", { name: /자식 실행 포함/ }, LONG);
    fireEvent.click(sw);
    await waitFor(() => expect(rest["getLogArchitecture"]!.mock.calls.at(-1)![0]).toMatchObject({ scope: "run-tree:r1" }), LONG);
  });

  it("[크게 보기]는 대화상자를 열고 Esc로 닫으면 단추로 포커스가 돌아온다", async () => {
    mount(["logs:runs", "logs:architecture"], "completed");
    const open = await screen.findByRole("button", { name: /크게 보기/ }, LONG);
    fireEvent.click(open);
    const dialog = await screen.findByRole("dialog", {}, LONG);
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(document.getElementById(dialog.getAttribute("aria-labelledby") ?? "")?.textContent).toContain("임의 프로필");
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull(), LONG);
  });

  it("실행 중이면 '실행 중 · 갱신 시각'을 보인다", async () => {
    mount(["logs:runs", "logs:architecture"], "running");
    expect(await screen.findByText(/^실행 중 · 갱신 /, {}, LONG)).toBeTruthy();
  });
});
