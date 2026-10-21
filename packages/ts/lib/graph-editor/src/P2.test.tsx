import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import type { Graph } from "@agent-console/contracts";
import { EdgeContextMenu, GraphEditor, MultiLayoutPanel } from "./index";
import type { ChangeMeta, GraphEditorProps } from "./index";
import { BUILTIN_DIRECTIONS } from "./logic/layout";
import { BUILTIN_EDGE_SHAPES } from "./shapes/registry";
import { descriptors, edgeTypes, sampleGraph } from "./testing";

afterEach(cleanup);

// 4R.20 연결선 P2 후속: 다중 선택 패널 · 엣지 우클릭 메뉴(+ Shift+F10) · 키보드 대안

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
const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 50)); });

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
        renderConfigPanel={(ctx) => (ctx.multiLayout !== undefined ? <MultiLayoutPanel {...ctx.multiLayout} /> : <div>패널</div>)}
        {...over}
      />
    </div>
  );
}
function setup(graph: Graph, over: Partial<GraphEditorProps> = {}) {
  const calls: Array<{ next: Graph; meta: ChangeMeta }> = [];
  return { calls, ...render(<Harness initial={graph} calls={calls} over={over} />) };
}

const edgeEl = (id = "e1") => document.querySelector<HTMLElement>(`.react-flow__edge[data-id="${id}"]`)!;
const canvas = () => document.querySelector<HTMLElement>(".ac-ge-canvas")!;
const live = () => document.querySelector(".ac-ge-sr-only[role='status']")!.textContent;
const shapeOf = (calls: Array<{ next: Graph }>, id: string) => calls.at(-1)!.next.edges!.find((e) => e.id === id)!.layout?.shape;

describe("엣지 우클릭 메뉴", () => {
  it("우클릭하면 메뉴가 열리고 모양을 고르면 layout 이유로 한 번 내보낸다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      fireEvent.contextMenu(edgeEl(), { clientX: 40, clientY: 30 });
      const menu = screen.getByRole("menu", { name: "연결선 메뉴" });
      expect(within(menu).getAllByRole("menuitemradio").length).toBe(6); // 상속 + 내장 5종(레지스트리에서 온다)
      fireEvent.click(within(menu).getByRole("menuitemradio", { name: "직각(둥근 모서리)" }));
      expect(calls).toHaveLength(1);
      expect(calls[0]!.meta.reason).toBe("layout");
      expect(shapeOf(calls, "e1")).toBe("smoothstep");
      expect(screen.queryByRole("menu")).toBeNull();
    }));

  it("Shift+F10으로 선택한 연결선의 메뉴를 열고 Esc로 닫으면 포커스가 연결선으로 돌아간다", () =>
    withLayout(async () => {
      setup(sampleGraph());
      await settle();
      fireEvent.click(edgeEl());
      fireEvent.keyDown(edgeEl(), { key: "F10", shiftKey: true });
      const menu = screen.getByRole("menu", { name: "연결선 메뉴" });
      expect(menu.contains(document.activeElement)).toBe(true); // 첫 항목에 포커스
      fireEvent.keyDown(menu, { key: "ArrowDown" });
      fireEvent.keyDown(menu, { key: "Escape" });
      expect(screen.queryByRole("menu")).toBeNull();
      expect(document.activeElement).toBe(edgeEl());
    }));

  it("ContextMenu 키도 같다. 선택이 없으면 열리지 않는다", () =>
    withLayout(async () => {
      setup(sampleGraph());
      await settle();
      fireEvent.keyDown(canvas(), { key: "ContextMenu" });
      expect(screen.queryByRole("menu")).toBeNull();
      fireEvent.click(edgeEl());
      fireEvent.keyDown(edgeEl(), { key: "ContextMenu" });
      expect(screen.getByRole("menu")).toBeTruthy();
    }));

  it("[경로 초기화]는 경유점·꺾임·라벨 위치만 지우고 모양을 유지한다", () =>
    withLayout(async () => {
      const g = sampleGraph();
      g.edges![0]!.layout = { shape: "step", waypoints: [{ x: 1, y: 2 }], label_t: 0.2 };
      const { calls } = setup(g);
      await settle();
      fireEvent.contextMenu(edgeEl());
      fireEvent.click(screen.getByRole("menuitem", { name: "경로 초기화" }));
      expect(calls.at(-1)!.next.edges![0]!.layout).toEqual({ shape: "step" });
      expect(live()).toBe("경로를 초기화했습니다.");
    }));

  it("[상속]을 고르면 layout.shape 키를 지운다", () =>
    withLayout(async () => {
      const g = sampleGraph();
      g.edges![0]!.layout = { shape: "step" };
      const { calls } = setup(g);
      await settle();
      fireEvent.contextMenu(edgeEl());
      fireEvent.click(screen.getByRole("menuitemradio", { name: "상속" }));
      expect(calls.at(-1)!.next.edges![0]).not.toHaveProperty("layout");
    }));

  it("[삭제]는 토스트 되돌리기를 남긴다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      fireEvent.contextMenu(edgeEl());
      fireEvent.click(screen.getByRole("menuitem", { name: "삭제" }));
      expect(calls.at(-1)!.meta.reason).toBe("remove");
      expect(calls.at(-1)!.next.edges!.map((e) => e.id)).toEqual(["e2", "e3"]);
      expect(screen.getByRole("button", { name: "되돌리기" })).toBeTruthy();
    }));

  it("읽기 전용에서는 열리지 않는다", () =>
    withLayout(async () => {
      setup(sampleGraph(), { readOnly: true });
      await settle();
      fireEvent.contextMenu(edgeEl());
      expect(screen.queryByRole("menu")).toBeNull();
    }));

  it("경로 편집은 경유점을 지원하는 모양일 때만 보인다", () =>
    withLayout(async () => {
      setup(sampleGraph());
      await settle();
      fireEvent.contextMenu(edgeEl());
      expect(screen.getByRole("menuitem", { name: "경로 편집" })).toBeTruthy(); // 내장 곡선은 경유점 지원
    }));
});

describe("EdgeContextMenu (표현 컴포넌트)", () => {
  const base = { at: { x: 0, y: 0 }, shapes: BUILTIN_EDGE_SHAPES, shape: "", canEditPath: false, onShape: () => {}, onResetPaths: () => {}, onEditPath: () => {}, onDelete: () => {}, onClose: () => {} };
  it("여러 연결선이면 [경로 초기화]가 확인 단계를 거치고 확인해야 호출된다", () => {
    let reset = 0;
    render(<EdgeContextMenu {...base} count={3} resettable={2} onResetPaths={() => (reset += 1)} />);
    fireEvent.click(screen.getByRole("menuitem", { name: "경로 초기화" }));
    expect(reset).toBe(0);
    const confirm = screen.getByRole("alertdialog");
    expect(confirm.textContent).toContain("연결선 2개");
    fireEvent.click(within(confirm).getByRole("button", { name: "취소" }));
    expect(reset).toBe(0);
    fireEvent.click(screen.getByRole("menuitem", { name: "경로 초기화" }));
    fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "초기화" }));
    expect(reset).toBe(1);
  });
  it("대상이 하나면 확인 없이 바로 호출된다", () => {
    let reset = 0;
    render(<EdgeContextMenu {...base} count={1} resettable={1} onResetPaths={() => (reset += 1)} />);
    fireEvent.click(screen.getByRole("menuitem", { name: "경로 초기화" }));
    expect(reset).toBe(1);
  });
  it("모양이 섞여 있으면 어떤 라디오도 체크되지 않는다", () => {
    render(<EdgeContextMenu {...base} count={2} resettable={0} shape={null} />);
    expect(screen.getAllByRole("menuitemradio").every((r) => r.getAttribute("aria-checked") === "false")).toBe(true);
  });
  it("모양 목록은 shapes props에서 온다(코드에 고정된 목록 없음)", () => {
    render(<EdgeContextMenu {...base} count={1} resettable={0} shapes={[{ ...BUILTIN_EDGE_SHAPES[0]!, id: "zz", title: "내 모양" }]} />);
    expect(screen.getAllByRole("menuitemradio").map((r) => r.textContent)).toEqual(["상속", "내 모양"]);
  });
});

describe("다중 선택 패널 (MultiLayoutPanel)", () => {
  it("연결선: 모양을 고르면 콜백 한 번, 섞인 값은 '여러 값'으로 보인다", () => {
    const shapes: Array<string | null> = [];
    render(<MultiLayoutPanel edges={{ count: 3, shapes: BUILTIN_EDGE_SHAPES, shape: null, resettable: 1, onShape: (s) => shapes.push(s), onResetPaths: () => {} }} />);
    expect(screen.getByText("3개 선택됨")).toBeTruthy();
    const select = screen.getByLabelText("모양") as HTMLSelectElement;
    expect(within(select).getByText("여러 값")).toBeTruthy();
    fireEvent.change(select, { target: { value: "step" } });
    expect(shapes).toEqual(["step"]);
    fireEvent.change(select, { target: { value: "" } });
    expect(shapes).toEqual(["step", null]);
  });
  it("[경로 초기화]는 확인 뒤에만 호출되고, 지울 것이 없으면 안내만 한다", () => {
    let reset = 0;
    const { rerender } = render(<MultiLayoutPanel edges={{ count: 2, shapes: BUILTIN_EDGE_SHAPES, shape: "", resettable: 2, onShape: () => {}, onResetPaths: () => (reset += 1) }} />);
    fireEvent.click(screen.getByRole("button", { name: "경로 초기화" }));
    expect(reset).toBe(0);
    fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "초기화" }));
    expect(reset).toBe(1);
    rerender(<MultiLayoutPanel edges={{ count: 2, shapes: BUILTIN_EDGE_SHAPES, shape: "", resettable: 0, onShape: () => {}, onResetPaths: () => (reset += 1) }} />);
    fireEvent.click(screen.getByRole("button", { name: "경로 초기화" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(reset).toBe(1);
    expect(screen.getAllByText("초기화할 연결선 경로가 없습니다.").length).toBeGreaterThan(0);
  });
  it("노드: 방향 버튼은 방향 어휘 표 + 자동 + 상속에서 만든다", () => {
    const picked: Array<string | null> = [];
    render(<MultiLayoutPanel nodes={{ count: 2, directions: BUILTIN_DIRECTIONS, direction: "tb", onDirection: (d) => picked.push(d) }} />);
    const group = screen.getByRole("group", { name: "방향" });
    expect(within(group).getAllByRole("button").length).toBe(Object.keys(BUILTIN_DIRECTIONS).length + 2);
    expect(within(group).getByRole("button", { name: "아래" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(within(group).getByRole("button", { name: "자동" }));
    fireEvent.click(within(group).getByRole("button", { name: "상속" }));
    expect(picked).toEqual(["auto", null]);
  });
  it("읽기 전용이면 모두 비활성이다", () => {
    render(<MultiLayoutPanel readOnly edges={{ count: 2, shapes: BUILTIN_EDGE_SHAPES, shape: "", resettable: 1, onShape: () => {}, onResetPaths: () => {} }} />);
    expect((screen.getByLabelText("모양") as HTMLSelectElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "경로 초기화" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("아무 구역도 없으면 아무것도 그리지 않는다", () => {
    const { container } = render(<MultiLayoutPanel />);
    expect(container.firstChild).toBeNull();
  });
});

describe("편집기 다중 선택 -> 패널", () => {
  const twoEdges = (): Graph => ({
    id: "g", name: "g",
    nodes: [
      { id: "n1", type: "zeta-source", config: {}, position: { x: 0, y: 0 } },
      { id: "n3", type: "kappa-sink", config: {}, position: { x: 400, y: 0 } },
    ],
    edges: [
      { id: "ea", kind: "flow-a", source: { node: "n1", port: "out" }, target: { node: "n3", port: "in" } },
      { id: "eb", kind: "flow-b", source: { node: "n1", port: "out" }, target: { node: "n3", port: "extra" } },
      { id: "ec", kind: "flow-b", source: { node: "n1", port: "out" }, target: { node: "n3", port: "in" } },
    ],
  });
  /** 두 연결선을 선택한다(Shift를 누른 채 클릭). */
  const selectTwoEdges = async () => {
    fireEvent.keyDown(document.body, { key: "Shift", code: "ShiftLeft", shiftKey: true });
    fireEvent.click(edgeEl("ea"), { shiftKey: true });
    fireEvent.click(edgeEl("eb"), { shiftKey: true });
    fireEvent.keyUp(document.body, { key: "Shift", code: "ShiftLeft" });
    await settle();
  };
  it("연결선 둘을 선택하면 multiLayout이 오고 모양을 한 번의 onChange로 모두에 쓴다", () =>
    withLayout(async () => {
      const { calls } = setup(twoEdges());
      await settle();
      await selectTwoEdges();
      const select = screen.getByLabelText("모양") as HTMLSelectElement;
      expect(screen.getAllByText("2개 선택됨").length).toBeGreaterThan(0);
      fireEvent.change(select, { target: { value: "smoothstep" } });
      expect(calls).toHaveLength(1);
      expect(calls[0]!.meta.reason).toBe("layout");
      expect(shapeOf(calls, "ea")).toBe("smoothstep");
      expect(shapeOf(calls, "eb")).toBe("smoothstep");
      expect(shapeOf(calls, "ec")).toBeUndefined();
    }));

  it("선택한 연결선 중 하나를 우클릭하면 메뉴가 선택 전체에 적용된다", () =>
    withLayout(async () => {
      const { calls } = setup(twoEdges());
      await settle();
      await selectTwoEdges();
      fireEvent.contextMenu(edgeEl("eb"));
      expect(screen.getByRole("menu").textContent).toContain("2개 선택됨");
      fireEvent.click(screen.getByRole("menuitemradio", { name: "직선" }));
      expect(shapeOf(calls, "ea")).toBe("straight");
      expect(shapeOf(calls, "eb")).toBe("straight");
      expect(shapeOf(calls, "ec")).toBeUndefined();
    }));
});

describe("첫 맞춤은 컨테이너 크기가 정해진 뒤에도 한다 (4R.21 보고)", () => {
  it("크기가 늦게 확정되면 그때 화면에 맞춘다(onlyRenderVisibleElements로 노드가 빠지지 않게)", async () => {
    const original = globalThis.ResizeObserver;
    const proto = HTMLElement.prototype;
    Object.defineProperty(proto, "offsetWidth", { configurable: true, get: () => 160 });
    Object.defineProperty(proto, "offsetHeight", { configurable: true, get: () => 80 });
    const watchers: Array<() => void> = [];
    globalThis.ResizeObserver = class {
      constructor(private cb: ResizeObserverCallback) {}
      observe(target: Element) {
        watchers.push(() => this.cb([{ target, contentRect: { width: 1000, height: 600 } } as ResizeObserverEntry], this as unknown as ResizeObserver));
      }
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver;
    try {
      setup(sampleGraph());
      await settle();
      const viewport = () => document.querySelector<HTMLElement>(".react-flow__viewport")!.style.transform;
      const before = viewport();
      await act(async () => {
        for (const w of watchers) w();
        await new Promise((r) => setTimeout(r, 100));
      });
      expect(viewport()).not.toBe(before);
      expect(viewport()).toMatch(/scale\(/);
    } finally {
      globalThis.ResizeObserver = original;
      delete (proto as unknown as Record<string, unknown>).offsetWidth;
      delete (proto as unknown as Record<string, unknown>).offsetHeight;
    }
  });
});
