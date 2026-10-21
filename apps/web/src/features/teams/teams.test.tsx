import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import { createFakeClients, versionConflict } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { agents, edgeTypes, nodeTypes, replySuggestion, resourceTypes, sampleGraph } from "../../testing/teamFixtures";

// 화면 조각을 lazy 로딩하므로 부하에서 1초 기본 대기로는 흔들린다(5.2R.9)
configure({ asyncUtilTimeout: 10_000 });

afterEach(() => {
  cleanup();
});

const summary = (o: Record<string, unknown>) => ({ labels: [], version_hash: "h1", saved_at: Math.floor(Date.now() / 1000) - 120, node_count: 2, edge_count: 1, ...o });

/** 두 화면이 함께 쓰는 서버 응답(임의 이름 디스크립터). */
function rest(overrides: Record<string, unknown> = {}) {
  return createFakeClients({
    listNodeTypes: vi.fn(async () => nodeTypes),
    listEdgeTypes: vi.fn(async () => edgeTypes),
    listResourceTypes: vi.fn(async () => resourceTypes),
    listAgents: vi.fn(async () => agents),
    listInteractionKinds: vi.fn(async () => []),
    listDelegationStrategies: vi.fn(async () => []),
    listRuns: vi.fn(async () => []),
    listConversations: vi.fn(async () => []),
    resolvePorts: vi.fn(async () => ({ inputs: [], outputs: [] })),
    // 서버가 계산한 계획 요약(입구 한 곳). 저장본·초안 모두 같은 모양
    getGraphPlan: vi.fn(async () => ({ entries: [{ edge_id: "x1", node_id: "a1" }], answers: [], grants: {} })),
    planDraftGraph: vi.fn(async () => ({ entries: [{ edge_id: "x1", node_id: "a1" }], answers: [], grants: {} })),
    getNodeEffectiveSettings: vi.fn(async () => ({ value: {}, provenance: {}, layers: [{ id: "L0", label: "공통" }, { id: "L1", label: "팀 구성" }, { id: "L2", label: "에이전트" }, { id: "L3", label: "이 팀의 노드" }] })),
    ...overrides,
  });
}

describe("팀 구성 목록", () => {
  const graphs = [summary({ id: "tm1", name: "임의 팀", description: "첫 설명", entry_labels: ["일꾼"] }), summary({ id: "tm2", name: "입구 없는 팀", entry_labels: [], node_count: 1 })];

  it("입구 요약을 보이고 입구가 없으면 경고로 표시하며, 입구 없는 팀은 대화 시작이 막힌다", async () => {
    const { clients } = rest({ listGraphs: vi.fn(async () => graphs) });
    mountApp(clients, "/teams");
    const grid = await screen.findByRole("grid", { name: "팀 구성 목록" });
    const rows = within(grid).getAllByRole("row");
    expect(within(rows[1]!).getByText("일꾼")).toBeTruthy();
    expect(within(rows[2]!).getByText(/없음/)).toBeTruthy();
    fireEvent.click(within(rows[2]!).getByRole("button", { name: /행 메뉴/ }));
    expect((screen.getByRole("menuitem", { name: "이 팀으로 대화 시작" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("표에서 Enter로 팀 구성을 연다(행과 행 안의 글자 칸 모두)", async () => {
    const { clients, rest: r } = editorClients({ listGraphs: vi.fn(async () => graphs) });
    mountApp(clients, "/teams");
    const grid = await screen.findByRole("grid", { name: "팀 구성 목록" });
    fireEvent.keyDown(within(grid).getAllByRole("row")[1]!, { key: "Enter" });
    await waitFor(() => expect(r.getGraph).toHaveBeenCalledWith("tm1"));
  });

  it("새 팀 구성은 속성으로 찾은 사용자 노드 하나로 시작한다(타입 이름 비교 없음)", async () => {
    const createGraph = vi.fn(async (g: { id: string }) => ({ graph: g, version_hash: "n1" }));
    const { clients } = rest({ listGraphs: vi.fn(async () => graphs), createGraph });
    mountApp(clients, "/teams");
    await screen.findByRole("grid", { name: "팀 구성 목록" });
    fireEvent.click(screen.getByRole("button", { name: /새 팀 구성/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("이름"), { target: { value: "My Team" } });
    expect((within(dialog).getByLabelText("id") as HTMLInputElement).value).toBe("my-team");
    expect((within(dialog).getByRole("radio", { name: "사용자 노드 하나로 시작" }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(within(dialog).getByRole("button", { name: "만들기" }));
    await waitFor(() => expect(createGraph).toHaveBeenCalledTimes(1));
    const sent = createGraph.mock.calls[0]![0] as { id: string; nodes: { type: string }[]; edges: unknown[] };
    expect(sent.id).toBe("my-team");
    expect(sent.nodes).toHaveLength(1);
    expect(sent.nodes[0]!.type).toBe("t-human");
    expect(sent.edges).toEqual([]);
  });

  it("id가 겹치면 즉시 인라인 오류를 보이고 만들 수 없다", async () => {
    const { clients } = rest({ listGraphs: vi.fn(async () => graphs) });
    mountApp(clients, "/teams");
    await screen.findByRole("grid", { name: "팀 구성 목록" });
    fireEvent.click(screen.getByRole("button", { name: /새 팀 구성/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("이름"), { target: { value: "다른 이름" } });
    fireEvent.change(within(dialog).getByLabelText("id"), { target: { value: "tm1" } });
    expect(within(dialog).getByText("이미 있는 id입니다")).toBeTruthy();
    expect((within(dialog).getByRole("button", { name: "만들기" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("복제는 서버 복제 API로, 삭제는 이 팀으로 만든 대화 수를 안내한다", async () => {
    const duplicateGraph = vi.fn(async (_id: string, t: { id: string }) => ({ graph: { id: t.id }, version_hash: "d1" }));
    const deleteGraph = vi.fn(async () => undefined);
    const { clients } = rest({ listGraphs: vi.fn(async () => graphs), duplicateGraph, deleteGraph, listConversations: vi.fn(async () => [{ id: "c1" }, { id: "c2" }]) });
    mountApp(clients, "/teams");
    const grid = await screen.findByRole("grid", { name: "팀 구성 목록" });
    fireEvent.click(within(within(grid).getAllByRole("row")[1]!).getByRole("button", { name: /행 메뉴/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "복제" }));
    const dup = await screen.findByRole("dialog");
    fireEvent.change(within(dup).getByLabelText("이름"), { target: { value: "copy one" } });
    fireEvent.click(within(dup).getByRole("button", { name: "복제" }));
    await waitFor(() => expect(duplicateGraph).toHaveBeenCalledWith("tm1", { id: "copy-one", name: "copy one" }));
    cleanup();
    mountApp(clients, "/teams");
    const grid2 = await screen.findByRole("grid", { name: "팀 구성 목록" });
    fireEvent.click(within(within(grid2).getAllByRole("row")[1]!).getByRole("button", { name: /행 메뉴/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "삭제" }));
    expect(await screen.findByText(/대화 2개의 기록은 남지만/)).toBeTruthy();
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "삭제" }));
    await waitFor(() => expect(deleteGraph).toHaveBeenCalledWith("tm1"));
  });

  it("빈 목록은 안내와 만들기, 공용 시작 단계 안내(옛 에이전트 먼저 문구 없음)", async () => {
    const { clients } = rest({ listGraphs: vi.fn(async () => []), listAgents: vi.fn(async () => []) });
    mountApp(clients, "/teams");
    expect(await screen.findByText("팀 구성이 아직 없습니다")).toBeTruthy();
    expect(await screen.findByRole("list", { name: "시작 순서" })).toBeTruthy();
    expect(screen.queryByText(/먼저 에이전트가 필요합니다/)).toBeNull();
  });
});

function editorClients(extra: Record<string, unknown> = {}, issues: unknown[] = [replySuggestion]) {
  const graph = sampleGraph();
  return rest({
    listGraphs: vi.fn(async () => [summary({ id: "tm1", name: "임의 팀", entry_labels: ["일꾼"] })]),
    getGraph: vi.fn(async () => ({ graph, version_hash: "h1", saved_at: 1 })),
    validateGraph: vi.fn(async () => issues),
    updateGraph: vi.fn(async (_id: string, g: unknown) => ({ graph: g, version_hash: "h2" })),
    listResources: vi.fn(async () => [{ id: "rs1", type: "rt-doc", name: "공용 문서", version_hash: "r1", usage_count: 0 }]),
    ...extra,
  });
}

describe("팀 구성 편집기: 검증 이슈·제안·저장", () => {
  it("서버 이슈를 그대로 보이고 제안 버튼은 초안에만 적용되며 [저장]이 If-Match로 보낸다", async () => {
    const { clients, rest: r } = editorClients();
    mountApp(clients, "/teams/tm1");
    const issues = await screen.findByRole("region", { name: "검증 이슈" });
    expect(await within(issues).findByText("답변으로 이어지는 연결이 없습니다")).toBeTruthy();
    expect(within(issues).getByText("c.no-reply")).toBeTruthy();
    expect(screen.getByText("저장됨")).toBeTruthy();
    fireEvent.click(within(issues).getByRole("button", { name: "일꾼 → 나 답변으로 연결" }));
    await waitFor(() => expect(screen.getByText("저장 안 됨")).toBeTruthy());
    expect(r.updateGraph).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(r.updateGraph).toHaveBeenCalledTimes(1));
    const [, sent, hash] = r.updateGraph.mock.calls[0]!;
    expect(hash).toBe("h1");
    expect((sent as { edges: { id: string; kind: string }[] }).edges.map((e) => e.id)).toEqual(["x1", "x2"]);
    expect(await screen.findByText("저장됨")).toBeTruthy();
  });

  it("버전 충돌(412)이면 충돌 배너가 뜨고 저장이 막힌다", async () => {
    const { clients } = editorClients({ updateGraph: vi.fn(async () => { throw versionConflict(); }) });
    mountApp(clients, "/teams/tm1");
    const issues = await screen.findByRole("region", { name: "검증 이슈" });
    fireEvent.click(await within(issues).findByRole("button", { name: "일꾼 → 나 답변으로 연결" }));
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    expect(await screen.findByText("다른 곳에서 먼저 수정되었습니다")).toBeTruthy();
    expect((screen.getByRole("button", { name: "저장" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("실행을 막는 이슈(blocks_run)가 있으면 대화 시작이 비활성이고 입구가 있으면 활성", async () => {
    const blocked = editorClients({}, [{ severity: "error", code: "c.block", message: "막는 문제", node_id: "a1", blocks_run: true }]);
    mountApp(blocked.clients, "/teams/tm1");
    const start = await screen.findByRole("button", { name: /대화 시작/ });
    await waitFor(() => expect((start as HTMLButtonElement).disabled).toBe(true));
    cleanup();
    // 실행 백엔드가 정해져 있어야 바로 시작한다(비어 있으면 해결 카드: teamsAdd.test)
    const ok = editorClients({ getSettingsVersioned: vi.fn(async () => ({ value: { agent_defaults: { backend: "be-1" } }, version_hash: "s1" })) }, []);
    mountApp(ok.clients, "/teams/tm1");
    const start2 = await screen.findByRole("button", { name: /대화 시작/ });
    await waitFor(() => expect((start2 as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(start2);
    await waitFor(() => expect(ok.rest.createConversation).toHaveBeenCalledWith({ graph_id: "tm1" }));
  });

  it("없는 팀 구성은 안내하고 목록으로 가는 길을 준다", async () => {
    const { ApiError } = await import("@agent-console/api-client");
    const { clients } = editorClients({ getGraph: vi.fn(async () => { throw new ApiError(404, { code: "not_found", message: "없음" }); }) });
    mountApp(clients, "/teams/tm1");
    expect(await screen.findByText("팀 구성을 찾을 수 없습니다")).toBeTruthy();
  });
});

describe("팀 구성 편집기: 노드·연결 패널", () => {
  it("노드를 고르면 역할 탭이 열리고 역할·위임 조건을 비우면 config 키가 지워진다", async () => {
    const { clients, rest: r } = editorClients({}, []);
    mountApp(clients, "/teams/tm1");
    fireEvent.click(await screen.findByLabelText(/^노드 일꾼/));
    const role = await screen.findByLabelText("역할", { selector: "input" });
    fireEvent.change(role, { target: { value: "리더" } });
    expect(screen.getByText("저장 안 됨")).toBeTruthy();
    fireEvent.change(role, { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("이름", { selector: "input" }), { target: { value: "새 이름" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(r.updateGraph).toHaveBeenCalled());
    const sent = r.updateGraph.mock.calls[0]![1] as { nodes: { id: string; label: string; config: Record<string, unknown> }[] };
    const node = sent.nodes.find((n) => n.id === "a1")!;
    expect(node.label).toBe("새 이름");
    expect(node.config).toEqual({ ref: "ag1" });
  });

  it("답변 토글은 디스크립터가 정한 종류·포트로 연결을 만든다", async () => {
    const { clients, rest: r } = editorClients({}, []);
    mountApp(clients, "/teams/tm1");
    fireEvent.click(await screen.findByLabelText(/^노드 일꾼/));
    fireEvent.click(await screen.findByRole("switch", { name: "답변" }));
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(r.updateGraph).toHaveBeenCalled());
    const sent = r.updateGraph.mock.calls[0]![1] as { edges: { kind: string; source: { node: string; port: string }; target: { node: string; port: string } }[] };
    expect(sent.edges.at(-1)).toMatchObject({ kind: "e-out", source: { node: "a1", port: "o1" }, target: { node: "h1", port: "hears" } });
  });

  it("사용자 노드의 검토 섹션은 스키마가 그리고 켜면 시작 값(필수 목록 항목 하나)이 들어간다", async () => {
    const { clients, rest: r } = editorClients({}, []);
    mountApp(clients, "/teams/tm1");
    fireEvent.click(await screen.findByLabelText(/^노드 나/));
    fireEvent.click(await screen.findByRole("tab", { name: "설정" }));
    expect(await screen.findByText("점검")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "검토 사용" }));
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(r.updateGraph).toHaveBeenCalled());
    const sent = r.updateGraph.mock.calls[0]![1] as { nodes: { id: string; config: { check: { options: { id: string }[] } } }[] };
    expect(sent.nodes.find((n) => n.id === "h1")!.config.check.options).toEqual([{ id: "d1" }]);
  });

  it("리소스 탭: 공통·팀 공용·에이전트·이 노드 층이 나오고, 붙이면 리소스 노드와 연결이 그래프에 생긴다", async () => {
    const { clients, rest: r } = editorClients({}, []);
    mountApp(clients, "/teams/tm1");
    fireEvent.click(await screen.findByLabelText(/^노드 일꾼/));
    fireEvent.click(await screen.findByRole("tab", { name: "리소스" }));
    const panel = await screen.findByRole("complementary", { name: "팀 구성 패널" });
    for (const layer of ["공통", "팀 공용", "에이전트", "이 노드"]) expect(within(panel).getAllByLabelText(layer).length).toBeGreaterThan(0);
    const nodeLayer = within(panel).getByLabelText("이 노드", { selector: "section" });
    fireEvent.click(within(nodeLayer).getByRole("button", { name: "+ 리소스 붙이기" }));
    fireEvent.click(await screen.findByRole("button", { name: "공용 문서 붙이기" }));
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(r.updateGraph).toHaveBeenCalled());
    const sent = r.updateGraph.mock.calls[0]![1] as { nodes: { id: string; type: string; config: Record<string, unknown> }[]; edges: { kind: string; source: { port: string }; target: { node: string; port: string } }[] };
    const asset = sent.nodes.find((n) => n.type === "t-asset")!;
    expect(asset.config).toEqual({ asset_ref: "rs1" });
    expect(sent.edges.at(-1)).toMatchObject({ kind: "e-attach", source: { port: "provide" }, target: { node: "a1", port: "i2" } });
  });

  it("리소스를 붙일 때 연결 종류 후보가 여럿이면 사용자가 고른다", async () => {
    const second = { ...edgeTypes.find((k) => k.id === "e-attach")!, id: "e-attach-b", title: "붙임 둘째" };
    const { clients, rest: r } = editorClients({ listEdgeTypes: vi.fn(async () => [...edgeTypes, second]) }, []);
    mountApp(clients, "/teams/tm1");
    fireEvent.click(await screen.findByLabelText(/^노드 일꾼/));
    fireEvent.click(await screen.findByRole("tab", { name: "리소스" }));
    const panel = await screen.findByRole("complementary", { name: "팀 구성 패널" });
    fireEvent.click(within(within(panel).getByLabelText("이 노드", { selector: "section" })).getByRole("button", { name: "+ 리소스 붙이기" }));
    fireEvent.click(await screen.findByRole("button", { name: "공용 문서 붙이기" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("radio", { name: /붙임 둘째/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "연결" }));
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(r.updateGraph).toHaveBeenCalled());
    const sent = r.updateGraph.mock.calls[0]![1] as { edges: { kind: string }[] };
    expect(sent.edges.at(-1)?.kind).toBe("e-attach-b");
  });
});


describe("묶음 미리보기·초안 미리보기(계약 v3)", () => {
  // 칸·코드 이름은 임의 값이다. 경고 문장은 서버가 준 그대로 보여야 한다.
  const preview = {
    bundle: { slots: { "slot-q": ["내용 에이"], "slot-r": ["내용 비"] }, sources: {} },
    warnings: [
      { severity: "warning", code: "x.unit", message: "서버가 쓴 문장 ***", path: "/slot-q/0" },
      { severity: "warning", code: "y.free", message: "칸에 안 붙는 경고" },
    ],
  };

  async function openBundle() {
    fireEvent.click(await screen.findByLabelText(/^노드 일꾼/));
    fireEvent.click(await screen.findByRole("tab", { name: "리소스" }));
    fireEvent.click(await screen.findByRole("button", { name: "번들 미리보기" }));
    return screen.findByRole("dialog");
  }

  it("저장본이면 GET으로 BundlePreview를 읽고 경고 영역과 칸 칩을 보인다", async () => {
    const { clients, rest: r } = editorClients({ getNodeBundlePreview: vi.fn(async () => preview) }, []);
    mountApp(clients, "/teams/tm1");
    const dialog = await openBundle();
    const warnings = await within(dialog).findByRole("region", { name: "묶음 경고" });
    expect(within(warnings).getByText("적용되지 않거나 제한되는 항목 2건", { exact: false })).toBeTruthy();
    expect(within(warnings).getByText("서버가 쓴 문장 ***")).toBeTruthy();
    expect(within(warnings).getByText("/slot-q/0")).toBeTruthy();
    expect(within(warnings).getByText("y.free")).toBeTruthy();
    // path가 칸 키로 시작하는 경고만 그 칸 머리에 칩
    expect(within(within(dialog).getByRole("region", { name: "칸 slot-q" })).getByText("경고 1건")).toBeTruthy();
    expect(within(within(dialog).getByRole("region", { name: "칸 slot-r" })).queryByText(/경고/)).toBeNull();
    expect(r.getNodeBundlePreview).toHaveBeenCalledWith("tm1", "a1");
    expect(within(dialog).queryByText("저장 전 초안 기준")).toBeNull();
  });

  it("경고가 없으면 경고 영역 자체가 없다", async () => {
    const { clients } = editorClients({ getNodeBundlePreview: vi.fn(async () => ({ bundle: preview.bundle, warnings: [] })) }, []);
    mountApp(clients, "/teams/tm1");
    const dialog = await openBundle();
    await within(dialog).findByRole("region", { name: "칸 slot-q" });
    expect(within(dialog).queryByRole("region", { name: "묶음 경고" })).toBeNull();
  });

  it("저장 전 변경이 있으면 초안 POST로 계산하고 `저장 전 초안 기준` 칩을 단다", async () => {
    const draftPreview = vi.fn(async () => preview);
    const { clients, rest: r } = editorClients({ previewDraftBundle: draftPreview, getNodeBundlePreview: vi.fn(async () => ({ bundle: {} })) }, []);
    mountApp(clients, "/teams/tm1");
    fireEvent.click(await screen.findByLabelText(/^노드 일꾼/));
    fireEvent.change(await screen.findByLabelText("이름", { selector: "input" }), { target: { value: "새 이름" } });
    fireEvent.click(await screen.findByRole("tab", { name: "리소스" }));
    fireEvent.click(await screen.findByRole("button", { name: "번들 미리보기" }));
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(draftPreview).toHaveBeenCalled(), { timeout: 4000 });
    const [req] = draftPreview.mock.calls[0] as unknown as [{ graph: { nodes: { id: string; label: string }[] }; node_id: string }];
    expect(req.node_id).toBe("a1");
    expect(req.graph.nodes.find((n) => n.id === "a1")?.label).toBe("새 이름");
    expect(await within(dialog).findByText("저장 전 초안 기준")).toBeTruthy();
    expect(await within(dialog).findByText("서버가 쓴 문장 ***")).toBeTruthy();
    expect(r.getNodeBundlePreview).not.toHaveBeenCalled();
  });

  it("서버가 초안 경로를 모르면(404) 저장 후 미리보기 안내로 폴백한다", async () => {
    const { clients } = editorClients({ previewDraftBundle: vi.fn(async () => { throw new ApiError(404, { code: "not_found", message: "없음" }); }) }, []);
    mountApp(clients, "/teams/tm1");
    fireEvent.click(await screen.findByLabelText(/^노드 일꾼/));
    fireEvent.change(await screen.findByLabelText("이름", { selector: "input" }), { target: { value: "새 이름" } });
    fireEvent.click(await screen.findByRole("tab", { name: "리소스" }));
    fireEvent.click(await screen.findByRole("button", { name: "번들 미리보기" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("저장 후 미리보기가 가능합니다", {}, { timeout: 4000 })).toBeTruthy();
  });

  it("초안 미리보기 연동 부분이 꺼져 있으면 초안을 묻지 않고 저장 후 미리보기 안내로 폴백한다(모듈 전역 기억 없음)", async () => {
    const draftPreview = vi.fn(async () => preview);
    const roles = ["conversations", "runs", "settings", "definitions:agent", "definitions:graph", "definitions:resource", "presets", "versions", "exports", "imports"];
    const { clients } = editorClients(
      { previewDraftBundle: draftPreview, previewDraftEffectiveSettings: vi.fn(async () => ({})), listModules: vi.fn(async () => [{ id: "base-mod", kind: "k", version: "1", status: "active", web_roles: roles }]) },
      [],
    );
    mountApp(clients, "/teams/tm1"); // 기본 연동 부분 데이터: definitions:teams 역할이 없다
    fireEvent.click(await screen.findByLabelText(/^노드 일꾼/));
    fireEvent.change(await screen.findByLabelText("이름", { selector: "input" }), { target: { value: "새 이름" } });
    fireEvent.click(await screen.findByRole("tab", { name: "리소스" }));
    fireEvent.click(await screen.findByRole("button", { name: "번들 미리보기" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("저장 후 미리보기가 가능합니다", {}, { timeout: 4000 })).toBeTruthy();
    expect(draftPreview).not.toHaveBeenCalled();
  });

  it("개요 탭은 입구·답변·되묻기 노드를 계획 요약에서 읽는다(연결 config의 final은 무시)", async () => {
    const { clients, rest: r } = editorClients({
      getGraphPlan: vi.fn(async () => ({ entries: [{ edge_id: "x1", node_id: "a1" }], answers: [{ edge_id: "z", node_id: "a1", final: false }], grants: { h1: {} } })),
    }, []);
    mountApp(clients, "/teams/tm1");
    const exits = await screen.findByRole("region", { name: "답변 노드" });
    expect(await within(exits).findByText("일꾼 · 중간")).toBeTruthy();
    expect(within(await screen.findByRole("region", { name: "되묻기 허용 노드" })).getByText("나")).toBeTruthy();
    expect(r.getGraphPlan).toHaveBeenCalledWith("tm1");
  });

  it("유효 설정의 필드 경고(limits.not_enforced 등)는 path로 필드에 붙고 서버 문장·코드가 그대로 보이며 값은 막지 않는다", async () => {
    // 경고 코드·문장은 임의 값이다: 화면은 코드를 해석하지 않고 path(JSON Pointer)만 폼 필드와 비교한다.
    const graph = sampleGraph();
    (graph.nodes as { id: string; config?: Record<string, unknown> }[])[1]!.config = { ref: "ag1", settings: { limits: { directories: ["/x"] } } };
    const warning = { severity: "warning", code: "limits.not_enforced", message: "선택한 백엔드가 이 제한을 강제하지 않습니다", path: "/limits/directories" };
    const { clients } = editorClients({
      getGraph: vi.fn(async () => ({ graph, version_hash: "h1", saved_at: 1 })),
      getNodeEffectiveSettings: vi.fn(async () => ({ value: { limits: { directories: ["/x"] } }, provenance: {}, layers: [{ id: "L0", label: "공통" }, { id: "L1", label: "팀 구성" }, { id: "L2", label: "에이전트" }, { id: "L3", label: "이 팀의 노드" }], warnings: [warning] })),
    }, []);
    mountApp(clients, "/teams/tm1");
    fireEvent.click(await screen.findByLabelText(/^노드 일꾼/));
    fireEvent.click(await screen.findByRole("tab", { name: "설정" }));
    expect(await screen.findByText(/선택한 백엔드가 이 제한을 강제하지 않습니다 \(limits\.not_enforced\)/)).toBeTruthy();
    expect(screen.getByText(/이 설정 중 1개에 서버 경고가 있습니다/)).toBeTruthy();
  });
});
