import { cleanup, configure, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { agents, edgeTypes, nodeTypes, resourceTypes, sampleGraph } from "../../testing/teamFixtures";

// 화면 조각을 lazy 로딩하므로 부하에서 1초 기본 대기로는 흔들린다(5.2R.9)
configure({ asyncUtilTimeout: 10_000 });

afterEach(cleanup);

/** 화면 배치(방향·포트 면) 연결: 3R.23. 노드 타입 이름은 테스트 픽스처의 임의 문자열이다. */
function editorClients(over: Record<string, unknown> = {}) {
  const graph = { ...sampleGraph(), ui: { viewport: { x: 12, y: 34, zoom: 1.5 } } };
  return createFakeClients({
    listNodeTypes: vi.fn(async () => nodeTypes),
    listEdgeTypes: vi.fn(async () => edgeTypes),
    listResourceTypes: vi.fn(async () => resourceTypes),
    listAgents: vi.fn(async () => agents),
    listInteractionKinds: vi.fn(async () => []),
    listDelegationStrategies: vi.fn(async () => []),
    listRuns: vi.fn(async () => []),
    listConversations: vi.fn(async () => []),
    listResources: vi.fn(async () => []),
    listGraphs: vi.fn(async () => [{ id: "tm1", name: "임의 팀", labels: [], version_hash: "h1", saved_at: 1, node_count: 2, edge_count: 1, entry_labels: [] }]),
    getGraph: vi.fn(async () => ({ graph, version_hash: "h1", saved_at: 1 })),
    validateGraph: vi.fn(async () => []),
    updateGraph: vi.fn(async (_id: string, g: unknown) => ({ graph: g, version_hash: "h2" })),
    resolvePorts: vi.fn(async () => ({ inputs: [], outputs: [] })),
    getGraphPlan: vi.fn(async () => ({ entries: [], answers: [], grants: {} })),
    planDraftGraph: vi.fn(async () => ({ entries: [], answers: [], grants: {} })),
    getNodeEffectiveSettings: vi.fn(async () => ({ value: {}, provenance: {}, layers: [] })),
    ...over,
  });
}

type Sent = { nodes: { id: string; layout?: unknown }[]; ui?: Record<string, unknown> };

describe("팀 편집 화면: 노드 [배치] 탭", () => {
  it("탭에서 방향을 고르면 그 노드의 layout만 바뀌고, 저장해도 Graph.ui의 viewport가 그대로다", async () => {
    const { clients, rest: r } = editorClients();
    mountApp(clients, "/teams/tm1");
    fireEvent.click(await screen.findByLabelText(/^노드 일꾼/));
    fireEvent.click(await screen.findByRole("tab", { name: "배치" }));
    fireEvent.click(await screen.findByRole("button", { name: "아래" }));
    expect(screen.getByText("저장 안 됨")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(r.updateGraph).toHaveBeenCalled());
    const sent = r.updateGraph.mock.calls[0]![1] as Sent;
    expect(sent.nodes.find((n) => n.id === "a1")!.layout).toEqual({ direction: "tb" });
    expect(sent.nodes.find((n) => n.id === "h1")).not.toHaveProperty("layout");
    expect(sent.ui).toEqual({ viewport: { x: 12, y: 34, zoom: 1.5 } });
  });

  it("[이 방향을 그래프 기본으로]는 Graph.ui.layout에 병합해 쓰고 viewport를 지우지 않는다", async () => {
    const { clients, rest: r } = editorClients();
    mountApp(clients, "/teams/tm1");
    fireEvent.click(await screen.findByLabelText(/^노드 일꾼/));
    fireEvent.click(await screen.findByRole("tab", { name: "배치" }));
    fireEvent.click(await screen.findByRole("button", { name: "왼쪽" }));
    fireEvent.click(screen.getByRole("button", { name: "이 방향을 그래프 기본으로" }));
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(r.updateGraph).toHaveBeenCalled());
    const sent = r.updateGraph.mock.calls[0]![1] as Sent;
    expect(sent.ui).toEqual({ viewport: { x: 12, y: 34, zoom: 1.5 }, layout: { direction: "rl" } });
  });

  it("설정의 editor.default_direction이 상속 값으로 전달되어 탭에 출처와 함께 보인다", async () => {
    const { clients } = editorClients();
    await clients.rest.putSettingsVersioned({ editor: { default_direction: "bt" } } as never, undefined as never);
    mountApp(clients, "/teams/tm1");
    fireEvent.click(await screen.findByLabelText(/^노드 일꾼/));
    fireEvent.click(await screen.findByRole("tab", { name: "배치" }));
    expect(await screen.findByText("상속 중: 설정의 기본 방향 → 위")).toBeTruthy();
  });

  it("Alt+4는 노드 패널의 배치 탭으로 간다", async () => {
    const { clients } = editorClients();
    mountApp(clients, "/teams/tm1");
    fireEvent.click(await screen.findByLabelText(/^노드 일꾼/));
    await screen.findByRole("tab", { name: "배치" });
    fireEvent.keyDown(document.body, { key: "4", altKey: true });
    await waitFor(() => expect(screen.getByRole("tab", { name: "배치", selected: true })).toBeTruthy());
  });
});

/** 레이아웃이 없는 환경에서 React Flow가 노드 크기를 측정해야 연결선이 그려진다(그래프 편집기 패키지 테스트와 같은 방식). */
async function withLayout(run: () => Promise<void>): Promise<void> {
  const original = globalThis.ResizeObserver;
  const proto = HTMLElement.prototype;
  const offW = Object.getOwnPropertyDescriptor(proto, "offsetWidth");
  const offH = Object.getOwnPropertyDescriptor(proto, "offsetHeight");
  Object.defineProperty(proto, "offsetWidth", { configurable: true, get: () => 160 });
  Object.defineProperty(proto, "offsetHeight", { configurable: true, get: () => 80 });
  globalThis.ResizeObserver = class {
    constructor(private cb: ResizeObserverCallback) {}
    observe(target: Element) {
      this.cb([{ target, contentRect: { width: 1000, height: 600 } } as ResizeObserverEntry], this as unknown as ResizeObserver);
    }
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  try {
    await run();
  } finally {
    globalThis.ResizeObserver = original;
    if (offW) Object.defineProperty(proto, "offsetWidth", offW);
    else delete (proto as unknown as Record<string, unknown>).offsetWidth;
    if (offH) Object.defineProperty(proto, "offsetHeight", offH);
    else delete (proto as unknown as Record<string, unknown>).offsetHeight;
  }
}

describe("팀 편집 화면: 연결 패널 모양·경로", () => {
  it("연결을 고르면 연결 패널에 모양·경로 섹션이 나오고 모양을 바꾸면 그 엣지의 layout.shape이 저장된다", () =>
    withLayout(async () => {
      const { clients, rest: r } = editorClients();
      mountApp(clients, "/teams/tm1");
      const edge = await waitFor(() => {
        const el = document.querySelector<HTMLElement>('.react-flow__edge[data-id="x1"]');
        if (el === null) throw new Error("edge");
        return el;
      });
      fireEvent.click(edge);
      const shape = await screen.findByLabelText("모양");
      fireEvent.change(shape, { target: { value: "step" } });
      fireEvent.click(screen.getByRole("button", { name: "저장" }));
      await waitFor(() => expect(r.updateGraph).toHaveBeenCalled());
      const sent = r.updateGraph.mock.calls[0]![1] as { edges: { id: string; layout?: unknown }[] };
      expect(sent.edges.find((e) => e.id === "x1")!.layout).toEqual({ shape: "step" });
    }));
});
