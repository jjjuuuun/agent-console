import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { agents, edgeTypes, nodeTypes, resourceTypes } from "../../testing/teamFixtures";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

const g = (id: string, name: string, o: Record<string, unknown> = {}) => ({ id, name, labels: [], version_hash: "h", node_count: 1, edge_count: 0, entry_labels: [], ...o });

function teamClients(summaries: unknown[], extra: Record<string, unknown> = {}) {
  return createFakeClients({
    listGraphs: vi.fn(async () => summaries),
    listNodeTypes: vi.fn(async () => nodeTypes),
    listEdgeTypes: vi.fn(async () => edgeTypes),
    listResourceTypes: vi.fn(async () => resourceTypes),
    listAgents: vi.fn(async () => agents),
    listRuns: vi.fn(async () => []),
    ...extra,
  });
}

async function pickNewFolder(name: string) {
  const dialog = await screen.findByRole("dialog", { name: "폴더로 이동" });
  fireEvent.change(within(dialog).getByRole("searchbox", { name: "폴더 찾기 또는 새 이름 입력" }), { target: { value: name } });
  fireEvent.click(within(dialog).getByRole("button", { name: new RegExp(`새 폴더 "${name}" 만들기`) }));
}

describe("팀 구성 목록 폴더·라벨(5.2R.63 후속)", () => {
  it("폴더 값이 있으면 폴더별 묶음이 계층 머리로 보이고 비활성 사유가 없다", async () => {
    const list = [g("t1", "팀 하나", { attributes: { ui: { folder: "개발/백엔드" } } }), g("t2", "팀 둘")];
    mountApp(teamClients(list).clients, "/teams");
    const grid = await screen.findByRole("grid", { name: "팀 구성 목록" });
    expect(Array.from(grid.querySelectorAll(".ac-grouphead")).map((h) => h.textContent)).toEqual(["개발(0)", "백엔드(1)", "(폴더 없음)(1)"]);
    fireEvent.click(screen.getByRole("button", { name: /폴더별/ }));
    expect(screen.getByRole("menuitemradio", { name: /^폴더/ }).getAttribute("aria-disabled")).not.toBe("true");
  });

  it("M으로 이동하면 원문을 읽어 폴더만 바꿔 If-Match로 저장하고 다른 필드를 보존한다", async () => {
    const full = { id: "t1", name: "팀 하나", labels: ["x"], attributes: { keep: 1, ui: { icon: "i" } }, nodes: [{ id: "n" }], edges: [], extra_field: 7 };
    const getGraph = vi.fn(async () => ({ graph: full, version_hash: "E1" }));
    const updateGraph = vi.fn(async (_id: string, graph: unknown) => ({ value: graph, version_hash: "E2" }));
    mountApp(teamClients([g("t1", "팀 하나")], { getGraph, updateGraph }).clients, "/teams");
    const grid = await screen.findByRole("grid", { name: "팀 구성 목록" });
    const row = within(grid).getByText("팀 하나").closest("tr")!;
    fireEvent.focus(row);
    fireEvent.keyDown(row, { key: "m" });
    await pickNewFolder("새폴더");
    await waitFor(() => expect(updateGraph).toHaveBeenCalledTimes(1));
    const [id, body, hash] = updateGraph.mock.calls[0] as unknown as [string, Record<string, unknown>, string];
    expect(id).toBe("t1");
    expect(hash).toBe("E1");
    expect(body).toEqual({ ...full, attributes: { keep: 1, ui: { icon: "i", folder: "새폴더" } } });
  });

  it("L로 라벨을 저장하고, 412이면 충돌 안내와 [다시 시도]를 보이며 다시 시도하면 최신 원문으로 저장한다", async () => {
    const getGraph = vi.fn(async () => ({ graph: { id: "t1", name: "팀 하나", labels: [], nodes: [], edges: [] }, version_hash: "E1" }));
    const updateGraph = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(412, { code: "precondition_failed", message: "버전 충돌" }))
      .mockResolvedValue({ value: {}, version_hash: "E2" });
    mountApp(teamClients([g("t1", "팀 하나")], { getGraph, updateGraph }).clients, "/teams");
    const grid = await screen.findByRole("grid", { name: "팀 구성 목록" });
    const row = within(grid).getByText("팀 하나").closest("tr")!;
    fireEvent.focus(row);
    fireEvent.keyDown(row, { key: "l" });
    const dialog = await screen.findByRole("dialog", { name: "라벨 편집" });
    const input = within(dialog).getByRole("textbox");
    fireEvent.change(input, { target: { value: "핵심" } });
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.click(within(dialog).getByRole("button", { name: "저장" }));
    const retry = await screen.findByRole("button", { name: "다시 시도" });
    expect(screen.getByText(/먼저 바뀌어 저장하지 못했습니다/)).toBeTruthy();
    fireEvent.click(retry);
    await waitFor(() => expect(updateGraph).toHaveBeenCalledTimes(2));
    expect(getGraph).toHaveBeenCalledTimes(2);
    expect((updateGraph.mock.calls[1] as unknown as [string, { labels: string[] }])[1].labels).toEqual(["핵심"]);
  });
});

describe("리소스 목록 폴더·라벨(5.2R.63 후속)", () => {
  const list = [
    { id: "d1", type: "rt-doc", name: "문서 하나", version_hash: "v1", attributes: { ui: { folder: "공통" } } },
    { id: "d2", type: "rt-doc", name: "문서 둘", version_hash: "v2" },
  ];
  const clients = (extra: Record<string, unknown> = {}) =>
    createFakeClients({ listResourceTypes: vi.fn(async () => resourceTypes), listResources: vi.fn(async () => list), listAgents: vi.fn(async () => []), ...extra });

  it("폴더별로 묶으면 폴더 머리가 보인다", async () => {
    mountApp(clients().clients, "/resources");
    const listbox = await screen.findByRole("listbox", { name: "리소스 목록" });
    fireEvent.click(screen.getByRole("button", { name: /종류별/ }));
    fireEvent.click(screen.getByRole("menuitemradio", { name: /^폴더/ }));
    expect(Array.from(listbox.querySelectorAll(".ac-grouphead")).map((h) => h.textContent)).toEqual(["공통(1)", "(폴더 없음)(1)"]);
  });

  it("M으로 이동하면 GET한 원문에서 폴더만 바꿔 If-Match로 PUT한다", async () => {
    const full = { id: "d2", type: "rt-doc", name: "문서 둘", config: { a: 1 }, attributes: { keep: true } };
    const getResource = vi.fn(async () => ({ value: full, version_hash: "R1" }));
    const updateResource = vi.fn(async (_id: string, r: unknown) => ({ value: r, version_hash: "R2" }));
    mountApp(clients({ getResource, updateResource }).clients, "/resources");
    const listbox = await screen.findByRole("listbox", { name: "리소스 목록" });
    const opt = within(listbox).getByText("문서 둘").closest<HTMLElement>("[role=option]")!;
    fireEvent.click(opt);
    fireEvent.keyDown(document.body, { key: "m" });
    await pickNewFolder("보관");
    await waitFor(() => expect(updateResource).toHaveBeenCalledTimes(1));
    const [id, body, hash] = updateResource.mock.calls[0] as unknown as [string, Record<string, unknown>, string];
    expect([id, hash]).toEqual(["d2", "R1"]);
    expect(body).toEqual({ ...full, attributes: { keep: true, ui: { folder: "보관" } } });
  });
});
