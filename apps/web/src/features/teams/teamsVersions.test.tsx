import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { agents, edgeTypes, nodeTypes, resourceTypes, sampleGraph } from "../../testing/teamFixtures";

afterEach(cleanup);
configure({ asyncUtilTimeout: 10_000 });
vi.setConfig({ testTimeout: 40_000 });

const NOW = Math.floor(Date.now() / 1000);
const versions = [
  { kind: "k", id: "tm1", version_hash: "cur00000aaaa", saved_at: NOW - 60 },
  { kind: "k", id: "tm1", version_hash: "prev1111bbbb", saved_at: NOW - 600, message: "이전 저장" },
];

function clients(extra: Record<string, unknown> = {}) {
  const graph = sampleGraph();
  return createFakeClients({
    listNodeTypes: vi.fn(async () => nodeTypes),
    listEdgeTypes: vi.fn(async () => edgeTypes),
    listResourceTypes: vi.fn(async () => resourceTypes),
    listAgents: vi.fn(async () => agents),
    listResources: vi.fn(async () => []),
    listInteractionKinds: vi.fn(async () => []),
    listDelegationStrategies: vi.fn(async () => []),
    listRuns: vi.fn(async () => []),
    listConversations: vi.fn(async () => []),
    resolvePorts: vi.fn(async () => ({ inputs: [], outputs: [] })),
    getGraphPlan: vi.fn(async () => ({ entries: [], answers: [], grants: {} })),
    planDraftGraph: vi.fn(async () => ({ entries: [], answers: [], grants: {} })),
    validateGraph: vi.fn(async () => []),
    listGraphs: vi.fn(async () => [{ id: "tm1", name: "임의 팀", labels: [], version_hash: "cur00000aaaa", saved_at: NOW, node_count: 2, edge_count: 1, entry_labels: [] }]),
    getGraph: vi.fn(async () => ({ graph, version_hash: "cur00000aaaa", saved_at: 1 })),
    listDefinitionVersions: vi.fn(async () => versions),
    getDefinitionVersion: vi.fn(async (_b: string, hash: string) => ({ ...versions.find((v) => v.version_hash === hash), content: {} })),
    diffDefinitionVersions: vi.fn(async () => ({ kind: "k", id: "tm1", from_hash: "prev1111bbbb", to_hash: "cur00000aaaa", changes: [{ op: "replace", path: "/name", before: "옛", after: "새" }], content_changes: [] })),
    restoreDefinitionVersion: vi.fn(async () => ({ value: { kind: "k", id: "tm1", version_hash: "new99999dddd", saved_at: NOW }, version_hash: "new99999dddd" })),
    listExporters: vi.fn(async () => [{ id: "fmt", title: "임의 형식", kinds: ["graph"], config_schema: { type: "object", properties: {} } }]),
    listExportRoots: vi.fn(async () => []),
    ...extra,
  });
}

describe("팀 구성: 버전 탭과 내보내기", () => {
  it("목록 행 메뉴의 [버전 목록]은 편집기의 버전 탭으로 이동한다(읽기 전용 다이얼로그 없음)", async () => {
    const { clients: c, rest } = clients();
    mountApp(c, "/teams");
    const grid = await screen.findByRole("grid", { name: "팀 구성 목록" });
    fireEvent.click(within(grid).getByRole("button", { name: /행 메뉴/ }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "버전 목록" }));
    expect(await screen.findByRole("listbox", { name: "버전 목록" })).toBeTruthy();
    expect(rest.listDefinitionVersions).toHaveBeenCalledWith("/graphs/tm1");
    expect(screen.getAllByRole("tab", { name: "버전" })[0]!.getAttribute("aria-selected")).toBe("true");
  });

  it("편집기 헤더 탭 [버전]: 되돌리기 뒤 초안을 버리고 팀 구성을 다시 읽는다", async () => {
    const { clients: c, rest } = clients();
    mountApp(c, "/teams/tm1?tab=versions");
    await screen.findByRole("listbox", { name: "버전 목록" });
    fireEvent.click(await screen.findByRole("button", { name: "되돌리기…" }));
    const dialog = await screen.findByRole("dialog", { name: "버전 prev1111로 되돌리기" });
    const before = rest.getGraph.mock.calls.length;
    fireEvent.click(within(dialog).getByRole("button", { name: "되돌리기" }));
    await waitFor(() => expect(rest.restoreDefinitionVersion).toHaveBeenCalledWith("/graphs/tm1", "prev1111bbbb", {}, "cur00000aaaa"));
    await waitFor(() => expect(rest.getGraph.mock.calls.length).toBeGreaterThan(before));
  });

  it("편집기 ⋯ 메뉴의 [내보내기…]는 현재 팀 구성이 담긴 다이얼로그를 연다", async () => {
    const { clients: c } = clients();
    mountApp(c, "/teams/tm1");
    fireEvent.click(await screen.findByRole("button", { name: /메뉴/ }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "내보내기…" }));
    const dialog = await screen.findByRole("dialog", { name: "내보내기" });
    const card = await within(dialog).findByRole("radio", { name: /임의 형식/ });
    expect(card.getAttribute("aria-checked")).toBe("true");
    fireEvent.click(within(dialog).getByRole("button", { name: /^다음$/ }));
    const items = await within(dialog).findByRole("region", { name: "내보낼 정의" });
    expect(within(items).getByText(/임의 팀|tm1/)).toBeTruthy();
  });
});

describe("설정: 버전 기록 섹션", () => {
  it("섹션 목록(데이터 묶음)에 있고 열면 /settings 버전을 보인다", async () => {
    const { clients: c, rest } = clients();
    mountApp(c, "/settings#versions");
    const nav = await screen.findByRole("navigation", { name: /섹션/ });
    // 서버 모듈 목록을 받은 뒤에야 섹션이 정해진다
    await waitFor(() => {
      expect(within(nav).getByRole("link", { name: "버전 기록" }).getAttribute("aria-current")).toBe("location");
    });
    expect(await screen.findByRole("listbox", { name: "버전 목록" })).toBeTruthy();
    expect(rest.listDefinitionVersions).toHaveBeenCalledWith("/settings");
  });
});
