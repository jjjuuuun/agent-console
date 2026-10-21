import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import type { Graph } from "@agent-console/contracts";
import { GraphEditor, createAStarRouter } from "./index";
import type { ChangeMeta, GraphEditorProps, KeyValueStorage, LayoutEngineDescriptor } from "./index";
import { descriptors, edgeTypes, sampleGraph } from "./testing";

afterEach(cleanup);

/** 레이아웃이 없는 환경에서 React Flow가 노드/핸들 치수를 측정하게 한다(EdgeEdit.test.tsx와 같은 방식). */
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

const settle = (ms = 50) => act(async () => { await new Promise((r) => setTimeout(r, ms)); });

/** 제어형 편집기: onChange가 올린 그래프를 다시 내려 준다(앱의 draft와 같다). */
function Harness({ initial, calls, over }: { initial: Graph; calls: Array<{ next: Graph; meta: ChangeMeta }>; over?: Partial<GraphEditorProps> }) {
  const [g, setG] = useState(initial);
  return (
    <div style={{ width: 1000, height: 600 }}>
      <GraphEditor
        graph={g}
        nodeTypes={descriptors}
        edgeTypes={edgeTypes}
        showMinimap={false}
        onChange={(next, meta) => {
          calls.push({ next, meta });
          setG(next);
        }}
        {...over}
      />
    </div>
  );
}


const memoryStorage = (): KeyValueStorage & { data: Map<string, string> } => {
  const data = new Map<string, string>();
  return { data, getItem: (k) => data.get(k) ?? null, setItem: (k, v) => void data.set(k, v) };
};

/** 노드를 대각선으로 늘어놓는 가짜 엔진(요청 노드 순서대로 160px 간격). */
const fakeEngine = (run?: LayoutEngineDescriptor["run"]): LayoutEngineDescriptor => ({
  id: "fake",
  title: "가짜",
  options: [{ key: "gap", title: "간격", type: "number", default: 40 }],
  run:
    run ??
    (async (req) => ({ positions: Object.fromEntries(req.nodes.map((n, i) => [n.id, { x: 13 + i * 160, y: 7 + i * 37 }])) })),
});

const nodeEl = (id = "n1") => document.querySelector<HTMLElement>(`.react-flow__node[data-id="${id}"]`)!;
const canvas = () => document.querySelector<HTMLElement>(".ac-ge-canvas")!;
const open = () => fireEvent.click(screen.getByRole("button", { name: "정리" }));

// 기본 라우터의 8ms 시계 상한은 고부하에서 fallback(= 노드 가로지름)을 만들어 엉킴 힌트를 거짓 양성으로 띄운다(5.2R.42).
function setup(graph: Graph, over: Partial<GraphEditorProps> = {}) {
  const calls: Array<{ next: Graph; meta: ChangeMeta }> = [];
  const storage = memoryStorage();
  const view = render(<Harness initial={graph} calls={calls} over={{ layoutEngines: [fakeEngine()], storage, edgeRouter: createAStarRouter({ maxMillis: 60_000 }), ...over }} />);
  return { calls, storage, ...view };
}

describe("정리 [정리 ▾] 연결 (graph-edges §4.1)", () => {
  it("엔진이 없거나 읽기 전용이면 버튼이 없다", () =>
    withLayout(async () => {
      setup(sampleGraph(), { layoutEngines: undefined });
      await settle();
      expect(screen.queryByRole("button", { name: "정리" })).toBeNull();
      cleanup();
      setup(sampleGraph(), { readOnly: true });
      await settle();
      expect(screen.queryByRole("button", { name: "정리" })).toBeNull();
    }));

  it("적용은 onChange 한 번(reason auto-layout): 좌표(격자·좌상단 맞춤), ui.layout 기록, viewport 보존", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      open();
      expect(screen.getByRole("dialog", { name: "정리" })).toBeTruthy();
      fireEvent.click(screen.getByRole("radio", { name: "아래" }));
      expect(calls).toHaveLength(0);
      await act(async () => fireEvent.click(screen.getByRole("button", { name: "적용" })));
      await settle();
      expect(calls).toHaveLength(1);
      expect(calls[0]!.meta.reason).toBe("auto-layout");
      const next = calls[0]!.next;
      // 가짜 엔진 결과(13,7)가 원래 좌상단(0,0)에 맞춰지고 8px 격자에 스냅: n1은 (0,0)
      expect(next.nodes![0]!.position).toEqual({ x: 0, y: 0 });
      expect(next.nodes![1]!.position).toEqual({ x: 160, y: 40 });
      expect(next.ui).toEqual({ viewport: { x: 0, y: 0, zoom: 1 }, layout: { direction: "tb" } });
      expect(next.custom_field).toEqual({ keep: "me" });
      expect(screen.queryByRole("dialog", { name: "정리" })).toBeNull();
      expect(screen.getAllByText("정리했습니다").length).toBeGreaterThan(0);
    }));

  it("정리 뒤 Ctrl+Z는 좌표와 ui.layout을 함께 되돌리고 viewport는 현재 값을 유지한다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      open();
      await act(async () => fireEvent.click(screen.getByRole("button", { name: "적용" })));
      await settle();
      fireEvent.keyDown(canvas(), { key: "z", ctrlKey: true });
      expect(calls.at(-1)!.meta.reason).toBe("undo");
      const back = calls.at(-1)!.next;
      expect(back.nodes![1]!.position).toEqual({ x: 300, y: 0 });
      expect(back.ui).toEqual({ viewport: { x: 0, y: 0, zoom: 1 } });
    }));

  it("토스트 [되돌리기]도 한 번에 되돌린다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      open();
      await act(async () => fireEvent.click(screen.getByRole("button", { name: "적용" })));
      await settle();
      fireEvent.click(screen.getByRole("button", { name: "되돌리기" }));
      expect(calls.at(-1)!.meta.reason).toBe("undo");
      expect(calls.at(-1)!.next.nodes![1]!.position).toEqual({ x: 300, y: 0 });
    }));

  it("미리보기는 반투명 윤곽만 그리고 onChange를 내보내지 않는다. 취소하면 윤곽도 사라진다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      open();
      await act(async () => fireEvent.click(screen.getByRole("button", { name: "미리보기" })));
      await settle();
      expect(document.querySelectorAll("[data-ghost-for]").length).toBe(4);
      // 연결 중심선은 라우터 경로(직각 꺾은선)로 그려진다(3R.27)
      const routed = document.querySelectorAll("path[data-ghost-route]");
      expect(routed.length).toBe(3);
      expect(routed[0]!.getAttribute("d")).toMatch(/^M/);
      expect(document.querySelectorAll("line.ac-ge-ghost-line").length).toBe(0);
      expect(calls).toHaveLength(0);
      fireEvent.click(within(screen.getByRole("dialog", { name: "정리" })).getByRole("button", { name: "취소" }));
      expect(screen.queryByRole("dialog", { name: "정리" })).toBeNull();
      expect(document.querySelectorAll("[data-ghost-for]").length).toBe(0);
      expect(calls).toHaveLength(0);
    }));

  it("엔진 실패는 팝오버에 오류 줄을 보이고 그래프를 바꾸지 않는다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph(), { layoutEngines: [fakeEngine(async () => Promise.reject(new Error("엔진을 불러오지 못했습니다")))] });
      await settle();
      open();
      await act(async () => fireEvent.click(screen.getByRole("button", { name: "적용" })));
      expect(screen.getByRole("alert").textContent).toContain("엔진을 불러오지 못했습니다");
      expect(calls).toHaveLength(0);
    }));

  it("L 키로 열고, Esc로 닫으면 캔버스에 포커스가 남아 있다", () =>
    withLayout(async () => {
      setup(sampleGraph());
      await settle();
      fireEvent.keyDown(canvas(), { key: "l" });
      expect(screen.getByRole("dialog", { name: "정리" })).toBeTruthy();
      fireEvent.keyDown(screen.getByRole("dialog", { name: "정리" }), { key: "Escape" });
      expect(screen.queryByRole("dialog", { name: "정리" })).toBeNull();
    }));

  it("선택이 한 개면 범위는 전체이고 [선택한 노드] 범위는 고를 수 있어도 계산은 막힌다(둘 이상 필요)", () =>
    withLayout(async () => {
      setup(sampleGraph());
      await settle();
      fireEvent.click(nodeEl("n1"));
      open();
      expect(screen.getByRole("radio", { name: "전체" })).toHaveProperty("checked", true);
      fireEvent.click(screen.getByRole("radio", { name: /선택한 노드\(1\)/ }));
      expect(screen.getByRole("button", { name: "적용" })).toHaveProperty("disabled", true);
    }));

  it("마지막 사용 옵션은 저장소에 기억되고 그래프 데이터는 더럽히지 않는다", () =>
    withLayout(async () => {
      const { storage, calls } = setup(sampleGraph());
      await settle();
      open();
      fireEvent.change(screen.getByLabelText("간격"), { target: { value: "72" } });
      expect(JSON.parse(storage.data.get("agent-console.graph-editor.tidy")!).optionsByEngine.fake.gap).toBe(72);
      expect(calls).toHaveLength(0);
      fireEvent.click(screen.getByRole("button", { name: "닫기" }));
      open();
      expect((screen.getByLabelText("간격") as HTMLInputElement).value).toBe("72");
    }));

  it("엔진이 권장 모양을 선언하면 '연결선도 자동 경로로'가 기본 선택이고 적용하면 ui.layout.edge_shape에 기록된다 (4R.20)", () =>
    withLayout(async () => {
      const engine: LayoutEngineDescriptor = { ...fakeEngine(), edgeShapeOption: { shapeId: "auto", default: true } };
      const { calls, storage } = setup(sampleGraph(), { layoutEngines: [engine] });
      await settle();
      open();
      const box = screen.getByRole("checkbox", { name: "연결선도 자동 경로로" }) as HTMLInputElement;
      expect(box.checked).toBe(true);
      await act(async () => fireEvent.click(screen.getByRole("button", { name: "적용" })));
      await settle();
      expect((calls.at(-1)!.next.ui!["layout"] as { edge_shape?: string }).edge_shape).toBe("auto");
      expect(calls.at(-1)!.next.ui!["viewport"]).toEqual({ x: 0, y: 0, zoom: 1 }); // 다른 ui 키는 보존
      // 끄면 그 선택을 기억하고(엔진 선언의 기본값보다 우선) 다음에 열 때도 꺼져 있다
      open();
      fireEvent.click(screen.getByRole("checkbox", { name: "연결선도 자동 경로로" }));
      expect(JSON.parse(storage.data.get("agent-console.graph-editor.tidy")!).autoShape).toEqual({ fake: false });
    }));

  it("선언이 없는 엔진은 모양 선택지를 만들지 않고 기본 모양을 건드리지 않는다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      open();
      expect(screen.queryByRole("checkbox", { name: "연결선도 자동 경로로" })).toBeNull();
      await act(async () => fireEvent.click(screen.getByRole("button", { name: "적용" })));
      await settle();
      expect(calls.at(-1)!.next.ui!["layout"]).not.toHaveProperty("edge_shape", "auto");
    }));

  it("모든 연결선 경로 초기화: 확인 뒤 onChange 한 번(reason layout), 모양은 유지", () =>
    withLayout(async () => {
      const g = sampleGraph();
      g.edges![0] = { ...g.edges![0]!, layout: { shape: "step", waypoints: [{ x: 10, y: 10 }] } };
      const { calls } = setup(g);
      await settle();
      open();
      fireEvent.click(screen.getByRole("button", { name: "모든 연결선 경로 초기화" }));
      expect(calls).toHaveLength(0);
      fireEvent.click(screen.getByRole("button", { name: "초기화" }));
      expect(calls).toHaveLength(1);
      expect(calls[0]!.meta.reason).toBe("layout");
      expect(calls[0]!.next.edges![0]!.layout).toEqual({ shape: "step" });
    }));
});

describe("연결선 경고 칩 (ux-overhaul §10.2 규칙 5)", () => {
  const HINT = "연결선 1개가 노드를 지납니다";
  /** 기본 설정이면 자동 경로라 노드를 피한다. 칩은 직접 비-자동 모양을 고른 선이 노드를 지날 때만 뜬다 */
  const tangled = (shape: string | null = "bezier"): Graph => ({
    id: "tangle",
    name: "t",
    nodes: [
      { id: "n1", type: "zeta-source", label: "시작", config: {}, position: { x: 0, y: 0 } },
      { id: "n2", type: "kappa-sink", label: "가운데", config: {}, position: { x: 300, y: 0 } },
      { id: "n3", type: "kappa-sink", label: "끝", config: {}, position: { x: 600, y: 0 } },
    ],
    edges: [{ id: "e1", kind: "flow-a", source: { node: "n1", port: "out" }, target: { node: "n3", port: "in" }, ...(shape !== null ? { layout: { shape } } : {}) }],
  });

  it("800ms 안정 뒤 칩이 뜨고 [자동 경로로]가 layout.shape를 지우는 onChange 한 번을 낸다", () =>
    withLayout(async () => {
      const { calls } = setup(tangled());
      await settle(300);
      expect(screen.queryByText(HINT)).toBeNull();
      await settle(700);
      expect(screen.getByText(HINT)).toBeTruthy();
      expect(calls).toHaveLength(0);
      fireEvent.click(screen.getByRole("button", { name: "자동 경로로" }));
      expect(calls).toHaveLength(1);
      expect(calls[0]!.meta.reason).toBe("layout");
      expect(calls[0]!.next.edges![0]!.layout).toBeUndefined();
      expect(screen.queryByText(HINT)).toBeNull();
    }));

  it("직접 고친 선(경유점)은 shape를 지우지 않고 auto를 적으며 경유점은 보존한다", () =>
    withLayout(async () => {
      const g = tangled();
      g.edges![0] = { ...g.edges![0]!, layout: { shape: "straight", waypoints: [{ x: 450, y: 20 }] } };
      const { calls } = setup(g);
      await settle(900);
      fireEvent.click(screen.getByRole("button", { name: "자동 경로로" }));
      expect(calls).toHaveLength(1);
      expect(calls[0]!.next.edges![0]!.layout).toEqual({ shape: "auto", waypoints: [{ x: 450, y: 20 }] });
    }));

  it("기본 설정(자동 경로)에서는 같은 배치에도 칩이 없다", () =>
    withLayout(async () => {
      setup(tangled(null));
      await settle(900);
      expect(screen.queryByText(HINT)).toBeNull();
    }));

  it("닫으면 그래프 id별로 기억해 다시 띄우지 않는다", () =>
    withLayout(async () => {
      const { storage } = setup(tangled());
      await settle(900);
      fireEvent.click(screen.getByRole("button", { name: "닫기" }));
      expect(screen.queryByText(HINT)).toBeNull();
      expect(storage.data.get("agent-console.graph-editor.trouble-dismissed.tangle")).toBe("true");
      cleanup();
      render(<Harness initial={tangled()} calls={[]} over={{ layoutEngines: [fakeEngine()], storage }} />);
      await settle(900);
      expect(screen.queryByText(HINT)).toBeNull();
    }));

  it("정리 엔진이 없어도 뜨고, 읽기 전용이거나 troubleHint=false면 띄우지 않으며, 깨끗한 그래프에도 없다", () =>
    withLayout(async () => {
      setup(tangled(), { layoutEngines: undefined });
      await settle(900);
      expect(screen.getByText(HINT)).toBeTruthy();
      cleanup();
      setup(tangled(), { readOnly: true });
      await settle(900);
      expect(screen.queryByText(HINT)).toBeNull();
      cleanup();
      setup(tangled(), { troubleHint: false });
      await settle(900);
      expect(screen.queryByText(HINT)).toBeNull();
      cleanup();
      setup(sampleGraph());
      await settle(900);
      expect(screen.queryByText(HINT)).toBeNull();
    }));
});
