import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Graph } from "@agent-console/contracts";
import { EdgeLayoutPanel, GraphEditor } from "./index";
import type { ChangeMeta, GraphEditorProps } from "./index";
import { descriptors, edgeTypes, sampleGraph } from "./testing";

afterEach(cleanup);

/** 레이아웃이 없는 환경에서 React Flow가 노드/핸들 치수를 측정하게 한다(GraphEditor.test.tsx와 같은 방식). */
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

const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 50)); });

function setup(graph: Graph, over: Partial<GraphEditorProps> = {}) {
  const calls: Array<{ next: Graph; meta: ChangeMeta }> = [];
  const view = (g: Graph) => (
    <div style={{ width: 1000, height: 600 }}>
      <GraphEditor
        graph={g}
        nodeTypes={descriptors}
        edgeTypes={edgeTypes}
        showMinimap={false}
        onChange={(next, meta) => calls.push({ next, meta })}
        renderConfigPanel={(ctx) => (ctx.edgeLayout !== undefined ? <EdgeLayoutPanel {...ctx.edgeLayout} /> : <div>패널</div>)}
        {...over}
      />
    </div>
  );
  const r = render(view(graph));
  return { ...r, calls, rerender: (g: Graph) => r.rerender(view(g)) };
}

const edgeEl = (id = "e1") => document.querySelector<HTMLElement>(`.react-flow__edge[data-id="${id}"]`)!;
const live = () => document.querySelector(".ac-ge-sr-only[role='status']")!.textContent;
const lastLayout = (calls: Array<{ next: Graph }>, id = "e1") => calls.at(-1)!.next.edges!.find((e) => e.id === id)!.layout;

describe("연결선 선택 시 조작 점", () => {
  it("선택한 엣지에만 중점이 나타나고, 선택하지 않으면 없다", () =>
    withLayout(async () => {
      setup(sampleGraph());
      await settle();
      expect(document.querySelector(".ac-ge-wp-mid")).toBeNull();
      fireEvent.click(edgeEl());
      expect(document.querySelectorAll(".ac-ge-wp-mid").length).toBe(1); // 경유점 0개 → 중점 1개
      expect(document.querySelector(".ac-ge-wp")).toBeNull();
    }));

  it("읽기 전용에서는 조작 점이 나타나지 않는다", () =>
    withLayout(async () => {
      setup(sampleGraph(), { readOnly: true });
      await settle();
      fireEvent.click(edgeEl());
      expect(document.querySelector(".ac-ge-wp-mid")).toBeNull();
    }));

  it("경유점이 있는 엣지는 경유점 ■ 와 중점 n+1개를 그린다", () =>
    withLayout(async () => {
      const g = sampleGraph();
      g.edges![0]!.layout = { shape: "straight", waypoints: [{ x: 150, y: 90 }, { x: 250, y: 90 }] };
      setup(g);
      await settle();
      fireEvent.click(edgeEl());
      expect(document.querySelectorAll(".ac-ge-wp").length).toBe(2);
      expect(document.querySelectorAll(".ac-ge-wp-mid").length).toBe(3);
    }));

  it("모양이 경유점을 지원하지 않으면 조작 점을 그리지 않는다", () =>
    withLayout(async () => {
      const plain = { id: "plain", title: "민자", preview: "M1,8 L23,2", supportsWaypoints: false, supportsBend: false, supportsRadius: false, build: (i: { source: { x: number; y: number }; target: { x: number; y: number } }) => ({ d: `M${i.source.x},${i.source.y} L${i.target.x},${i.target.y}`, labelAt: () => ({ x: 0, y: 0, angle: 0 }), segments: [], length: 0 }) };
      const g = sampleGraph();
      g.edges![0]!.layout = { shape: "plain" };
      setup(g, { edgeShapes: [plain as never] });
      await settle();
      fireEvent.click(edgeEl());
      expect(document.querySelector(".ac-ge-wp-mid")).toBeNull();
    }));
});

describe("S / X 키와 연결 패널", () => {
  it("S는 레지스트리 순서로 모양을 돌리고 마지막 다음은 상속(layout 키 삭제), Shift+S는 거꾸로", () =>
    withLayout(async () => {
      const { calls, rerender } = setup(sampleGraph(), { layoutDefaults: { edgeShape: "bezier" } });
      await settle();
      fireEvent.click(edgeEl());
      fireEvent.keyDown(edgeEl(), { key: "s" });
      expect(calls.at(-1)!.meta.reason).toBe("layout");
      expect(lastLayout(calls)).toEqual({ shape: "bezier" });
      expect(live()).toBe("모양: 곡선");
      // 마지막(auto) 다음은 상속
      const g = sampleGraph();
      g.edges![0]!.layout = { shape: "auto" };
      rerender(g);
      fireEvent.keyDown(edgeEl(), { key: "s" });
      expect(calls.at(-1)!.next.edges![0]).not.toHaveProperty("layout");
      expect(live()).toBe("모양: 상속 (현재: 곡선)");
      fireEvent.keyDown(edgeEl(), { key: "S", shiftKey: true });
      expect(lastLayout(calls)).toEqual({ shape: "straight" }); // auto 이전
    }));

  it("X는 경로(경유점·꺾임·라벨 위치)만 지우고 모양은 유지, 지울 게 없어도 안전", () =>
    withLayout(async () => {
      const g = sampleGraph();
      g.edges![0]!.layout = { shape: "step", bend: 0.3, waypoints: [{ x: 1, y: 2 }], label_t: 0.2, label_offset: { x: 3, y: 4 } };
      const { calls } = setup(g);
      await settle();
      fireEvent.click(edgeEl());
      fireEvent.keyDown(edgeEl(), { key: "x" });
      expect(lastLayout(calls)).toEqual({ shape: "step" });
      expect(live()).toBe("경로를 초기화했습니다.");
    }));

  it("S/X는 읽기 전용에서 무시된다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph(), { readOnly: true });
      await settle();
      fireEvent.click(edgeEl());
      fireEvent.keyDown(edgeEl(), { key: "s" });
      fireEvent.keyDown(edgeEl(), { key: "x" });
      expect(calls.length).toBe(0);
    }));

  it("연결 패널: 엣지를 선택하면 '모양·경로' 섹션이 나오고, 모양 변경은 reason layout 1회, 다른 필드는 보존", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph(), { layoutDefaults: { edgeShape: "bezier" } });
      await settle();
      fireEvent.click(edgeEl("e3"));
      expect(screen.getByText(/모양·경로/)).toBeTruthy();
      expect(screen.getByRole("option", { name: "상속 (현재: 곡선)" })).toBeTruthy();
      fireEvent.change(screen.getByLabelText("모양"), { target: { value: "smoothstep" } });
      expect(calls.length).toBe(1);
      expect(calls[0]!.meta.reason).toBe("layout");
      expect(calls[0]!.next.edges!.find((e) => e.id === "e3")!.layout).toEqual({ shape: "smoothstep" });
      // 그래프의 다른 키 보존(Graph.ui의 viewport 등)
      expect(calls[0]!.next.ui).toEqual({ viewport: { x: 0, y: 0, zoom: 1 } });
      expect((calls[0]!.next as Record<string, unknown>)["custom_field"]).toEqual({ keep: "me" });
    }));

  it("상속 표시는 그래프 층(종류별)과 사용자 설정을 따른다", () =>
    withLayout(async () => {
      const g = sampleGraph();
      g.ui = { ...g.ui, layout: { edge_shape_by_kind: { "flow-b": "step" } } };
      setup(g, { layoutDefaults: { edgeShape: "straight" } });
      await settle();
      fireEvent.click(edgeEl("e3"));
      expect(screen.getByRole("option", { name: "상속 (현재: 직각(각진 모서리))" })).toBeTruthy();
    }));

  it("엣지 접근성 이름에 모양·경유점이 덧붙고, 값이 없으면 기존 문구 그대로", () =>
    withLayout(async () => {
      const g = sampleGraph();
      g.edges![0]!.layout = { shape: "straight", waypoints: [{ x: 1, y: 1 }, { x: 2, y: 2 }] };
      setup(g);
      await settle();
      expect(edgeEl("e1").getAttribute("aria-label")).toBe("시작의 out에서 분기의 in로 연결; 모양 직선; 경유점 2개");
      expect(edgeEl("e3").getAttribute("aria-label")).toBe("유령의 ghost-out에서 끝의 extra로 연결");
    }));
});

describe("경로 편집 모드(키보드)", () => {
  it("Enter로 시작해 중점에서 Enter로 경유점을 추가하고, Esc로 끝낸다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      fireEvent.click(edgeEl());
      fireEvent.keyDown(edgeEl(), { key: "Enter" });
      expect(live()).toContain("경로 편집 모드");
      const mid = document.querySelector<HTMLElement>(".ac-ge-wp-mid")!;
      expect(mid.tabIndex).toBe(0);
      expect(document.activeElement).toBe(mid);
      fireEvent.keyDown(mid, { key: "Enter" });
      expect(calls.length).toBe(1);
      expect(calls[0]!.meta.reason).toBe("layout");
      expect(lastLayout(calls)!.waypoints).toHaveLength(1);
      expect(live()).toMatch(/^경유점 1 추가, x -?\d+ y -?\d+$/);
      fireEvent.keyDown(mid, { key: "Escape" });
      expect(live()).toBe("경로 편집 모드를 끝냈습니다.");
      expect(document.querySelector(".ac-ge-wp-mid")!.getAttribute("tabindex")).toBe("-1");
    }));

  it("경유점에서 Delete는 경유점만 지우고 연결은 지우지 않는다(onChange 1회, 엣지 유지)", () =>
    withLayout(async () => {
      const g = sampleGraph();
      g.edges![0]!.layout = { waypoints: [{ x: 150, y: 90 }] };
      const { calls } = setup(g);
      await settle();
      fireEvent.click(edgeEl());
      const wp = document.querySelector<HTMLElement>(".ac-ge-wp")!;
      wp.focus();
      fireEvent.keyDown(wp, { key: "Delete" });
      expect(calls.length).toBe(1);
      expect(calls[0]!.meta.reason).toBe("layout");
      expect(calls[0]!.next.edges!.length).toBe(3);
      expect(calls[0]!.next.edges![0]).not.toHaveProperty("layout");
    }));

  it("경유점 17번째 추가는 거부되고 안내가 보인다", () =>
    withLayout(async () => {
      const g = sampleGraph();
      g.edges![0]!.layout = { waypoints: Array.from({ length: 16 }, (_, i) => ({ x: 100 + i * 8, y: 90 })) };
      const { calls } = setup(g);
      await settle();
      fireEvent.click(edgeEl());
      fireEvent.keyDown(edgeEl(), { key: "Enter" });
      const mid = document.querySelector<HTMLElement>(".ac-ge-wp-mid")!;
      fireEvent.keyDown(mid, { key: "Enter" });
      expect(calls.length).toBe(0);
      expect(document.querySelector(".ac-ge-toast-text")?.textContent).toBe("경유점은 연결 하나에 16개까지");
    }));
});

describe("라벨 칩", () => {
  it("더블클릭은 라벨 위치만 초기화(label_t·label_offset 삭제)", () =>
    withLayout(async () => {
      const g = sampleGraph();
      g.edges![0]!.layout = { shape: "step", label_t: 0.3, label_offset: { x: 5, y: 5 } };
      const { calls } = setup(g);
      await settle();
      fireEvent.click(edgeEl());
      const chip = document.querySelector<HTMLElement>(".ac-ge-edge-chip[data-selected='true']")!;
      fireEvent.doubleClick(chip);
      expect(lastLayout(calls)).toEqual({ shape: "step" });
    }));

  it("경로 편집 모드에서 라벨 칩은 슬라이더이고 ←→ 로 0.05씩 움직인다", () =>
    withLayout(async () => {
      const g = sampleGraph();
      g.edges![0]!.layout = { label_t: 0.3 };
      const { calls } = setup(g);
      await settle();
      fireEvent.click(edgeEl());
      fireEvent.keyDown(edgeEl(), { key: "Enter" });
      const chip = screen.getByRole("slider");
      expect(chip.getAttribute("aria-valuenow")).toBe("30");
      fireEvent.keyDown(chip, { key: "ArrowRight" });
      expect(lastLayout(calls)).toEqual({ label_t: 0.35 });
      fireEvent.keyDown(chip, { key: "ArrowLeft" });
      expect(calls.length).toBe(2);
    }));
});

describe("포인터: 한 번의 조작 = onChange 1회(reason layout)", () => {
  it("선을 더블클릭하면 경로 위에 경유점 1개를 추가한다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      fireEvent.click(edgeEl());
      fireEvent.doubleClick(edgeEl().querySelector(".react-flow__edge-interaction")!, { clientX: 200, clientY: 100 });
      expect(calls.length).toBe(1);
      expect(calls[0]!.meta.reason).toBe("layout");
      expect(lastLayout(calls)!.waypoints).toHaveLength(1);
    }));

  it("라벨 칩을 끌면 중간 값은 내보내지 않고 손을 뗄 때 label_t만 1회 내보낸다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      fireEvent.click(edgeEl());
      const chip = document.querySelector<HTMLElement>(".ac-ge-edge-chip[data-selected='true']")!;
      fireEvent.pointerDown(chip, { clientX: 100, clientY: 100, button: 0, pointerId: 3 });
      fireEvent.pointerMove(chip, { clientX: 120, clientY: 100, pointerId: 3 });
      fireEvent.pointerMove(chip, { clientX: 900, clientY: 100, pointerId: 3 });
      expect(calls.length).toBe(0);
      fireEvent.pointerUp(chip, { clientX: 900, clientY: 100, pointerId: 3 });
      expect(calls.length).toBe(1);
      expect(calls[0]!.meta.reason).toBe("layout");
      const lay = lastLayout(calls)!;
      expect(Object.keys(lay)).toEqual(["label_t"]);
      expect(lay.label_t).toBeGreaterThanOrEqual(0.1);
      expect(lay.label_t).toBeLessThanOrEqual(0.9);
    }));

  it("Shift+드래그는 경로에서 떼어 label_offset을 낸다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      fireEvent.click(edgeEl());
      const chip = document.querySelector<HTMLElement>(".ac-ge-edge-chip[data-selected='true']")!;
      fireEvent.pointerDown(chip, { clientX: 100, clientY: 100, button: 0, pointerId: 4 });
      fireEvent.pointerMove(chip, { clientX: 140, clientY: 160, pointerId: 4, shiftKey: true });
      fireEvent.pointerUp(chip, { clientX: 140, clientY: 160, pointerId: 4 });
      expect(calls.length).toBe(1);
      expect(Object.keys(lastLayout(calls)!)).toEqual(["label_offset"]);
    }));
});

describe("편집이 없을 때 onChange를 내지 않는다", () => {
  it("엣지를 선택만 해서는 onChange가 호출되지 않는다", () =>
    withLayout(async () => {
      const spy = vi.fn();
      setup(sampleGraph(), { onChange: spy });
      await settle();
      fireEvent.click(edgeEl());
      expect(spy).not.toHaveBeenCalled();
    }));
});
