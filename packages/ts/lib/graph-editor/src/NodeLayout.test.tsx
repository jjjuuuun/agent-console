import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Graph } from "@agent-console/contracts";
import { GraphEditor, NodeLayoutPanel } from "./index";
import type { ChangeMeta, GraphEditorProps, LayoutPanels } from "./index";
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

const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 50)); });

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
        renderConfigPanel={(ctx) => (ctx.nodeLayout !== undefined ? <NodeLayoutPanel {...ctx.nodeLayout} /> : <div>패널</div>)}
        {...over}
      />
    </div>
  );
}

const nodeEl = (id = "n1") => document.querySelector<HTMLElement>(`.react-flow__node[data-id="${id}"]`)!;
const live = () => document.querySelector(".ac-ge-sr-only[role='status']")!.textContent;
const last = (calls: Array<{ next: Graph }>) => calls.at(-1)!.next;
const layoutOf = (g: Graph, id = "n1") => g.nodes!.find((n) => n.id === id)!.layout;
const canvas = () => document.querySelector<HTMLElement>(".ac-ge-canvas")!;

function setup(graph: Graph, over: Partial<GraphEditorProps> = {}) {
  const calls: Array<{ next: Graph; meta: ChangeMeta }> = [];
  const view = render(<Harness initial={graph} calls={calls} {...(over ? { over } : {})} />);
  return { calls, ...view };
}

describe("방향 순환 R · 툴바 [방향 바꾸기]", () => {
  it("노드를 선택하고 R을 누르면 lr → tb → rl → bt → 자동 → 상속 순으로 돌고 reason은 layout", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      fireEvent.click(nodeEl());
      const seen: Array<string | null | undefined> = [];
      for (let i = 0; i < 6; i++) {
        fireEvent.keyDown(canvas(), { key: "r" });
        seen.push(layoutOf(last(calls))?.direction);
        expect(calls.at(-1)!.meta.reason).toBe("layout");
      }
      expect(seen).toEqual(["lr", "tb", "rl", "bt", "auto", undefined]);
      expect(last(calls).nodes![0]).not.toHaveProperty("layout");
      expect(live()).toContain("방향: ");
    }));

  it("툴바 버튼도 같은 순환을 한 번에 한 단계 한다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      fireEvent.click(nodeEl());
      fireEvent.click(screen.getByRole("button", { name: /방향 바꾸기/ }));
      expect(layoutOf(last(calls))).toEqual({ direction: "lr" });
      expect(calls).toHaveLength(1);
    }));

  it("읽기 전용·선택 없음·글자 입력 중에는 R이 아무것도 하지 않는다", () =>
    withLayout(async () => {
      const ro = setup(sampleGraph(), { readOnly: true });
      await settle();
      fireEvent.click(nodeEl());
      fireEvent.keyDown(canvas(), { key: "r" });
      expect(ro.calls).toHaveLength(0);
      cleanup();
      const none = setup(sampleGraph());
      await settle();
      fireEvent.keyDown(canvas(), { key: "r" });
      expect(none.calls).toHaveLength(0);
    }));

  it("방향 어휘 표를 바꿔 넘기면 코드 수정 없이 그 어휘로 돈다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph(), { directions: { zz: { in: "top", out: "bottom" }, yy: { in: "left", out: "right" } } });
      await settle();
      fireEvent.click(nodeEl());
      fireEvent.keyDown(canvas(), { key: "r" });
      expect(layoutOf(last(calls))).toEqual({ direction: "zz" });
    }));
});

describe("레이아웃 되돌리기 스택 Ctrl+Z", () => {
  it("방향 변경을 Ctrl+Z로 되돌리고 Ctrl+Shift+Z로 다시 적용한다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      fireEvent.click(nodeEl());
      fireEvent.keyDown(canvas(), { key: "r" });
      fireEvent.keyDown(canvas(), { key: "r" });
      expect(layoutOf(last(calls))).toEqual({ direction: "tb" });
      fireEvent.keyDown(canvas(), { key: "z", ctrlKey: true });
      expect(layoutOf(last(calls))).toEqual({ direction: "lr" });
      expect(calls.at(-1)!.meta.reason).toBe("undo");
      expect(live()).toBe("레이아웃 변경을 되돌렸습니다.");
      fireEvent.keyDown(canvas(), { key: "z", ctrlKey: true });
      expect(last(calls).nodes![0]).not.toHaveProperty("layout");
      fireEvent.keyDown(canvas(), { key: "Z", ctrlKey: true, shiftKey: true });
      expect(layoutOf(last(calls))).toEqual({ direction: "lr" });
      expect(live()).toBe("레이아웃 변경을 다시 적용했습니다.");
    }));

  it("되돌릴 것이 없으면 아무 것도 내보내지 않는다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      fireEvent.keyDown(canvas(), { key: "z", ctrlKey: true });
      expect(calls).toHaveLength(0);
    }));

  it("레이아웃이 아닌 편집(노드 삭제)은 스택에 섞이지 않고, 그 뒤 Ctrl+Z는 낡은 스택을 비운다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      fireEvent.click(nodeEl());
      fireEvent.keyDown(canvas(), { key: "r" });
      fireEvent.keyDown(canvas(), { key: "Delete" });
      const n = calls.length;
      expect(calls.at(-1)!.meta.reason).toBe("remove");
      fireEvent.keyDown(canvas(), { key: "z", ctrlKey: true });
      expect(calls).toHaveLength(n);
    }));

  it("30단계까지만 쌓인다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      fireEvent.click(nodeEl());
      for (let i = 0; i < 35; i++) fireEvent.keyDown(canvas(), { key: "r" });
      let undone = 0;
      for (let i = 0; i < 40; i++) {
        const before = calls.length;
        fireEvent.keyDown(canvas(), { key: "z", ctrlKey: true });
        if (calls.length > before) undone += 1;
      }
      expect(undone).toBe(30);
    }));

  it("연결선 모양 변경(S)도 같은 스택에 쌓인다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      const edge = () => document.querySelector<HTMLElement>('.react-flow__edge[data-id="e1"]')!;
      fireEvent.click(edge());
      fireEvent.keyDown(edge(), { key: "s" });
      expect(last(calls).edges![0]!.layout).toEqual({ shape: "bezier" });
      fireEvent.keyDown(canvas(), { key: "z", ctrlKey: true });
      expect(last(calls).edges![0]).not.toHaveProperty("layout");
    }));
});

describe("[배치] 패널 값과 그래프 기본", () => {
  it("renderConfigPanel의 nodeLayout으로 포트 면을 바꾸면 해당 포트 키만 기록하고 reason은 layout", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      fireEvent.click(nodeEl());
      const sel = screen.getByRole("combobox", { name: "출력 출력의 면" });
      fireEvent.change(sel, { target: { value: "bottom" } });
      expect(layoutOf(last(calls))).toEqual({ ports: { "out:out": "bottom" } });
      expect(calls.at(-1)!.meta.reason).toBe("layout");
      // 핸들 위치가 바뀌었다 -> 글리프가 보인다
      expect(document.querySelector(".ac-ge-port-glyph")?.textContent).toBe("↓");
    }));

  it("[이 방향을 그래프 기본으로]는 Graph.ui를 병합 저장해 viewport 등 다른 키를 보존한다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      fireEvent.click(nodeEl());
      fireEvent.click(screen.getByRole("button", { name: "아래" }));
      fireEvent.click(screen.getByRole("button", { name: "이 방향을 그래프 기본으로" }));
      const ui = last(calls).ui as Record<string, unknown>;
      expect(ui["viewport"]).toEqual({ x: 0, y: 0, zoom: 1 });
      expect(ui["layout"]).toEqual({ direction: "tb" });
      expect(last(calls).custom_field).toEqual({ keep: "me" });
    }));

  it("onLayoutPanelsChange: 노드 1개 선택이면 node, 엣지 1개면 edge, 아니면 null이고 변경은 reason layout", () =>
    withLayout(async () => {
      const seen: Array<LayoutPanels | null> = [];
      const onLayoutPanelsChange = vi.fn((p: LayoutPanels | null) => seen.push(p));
      const { calls } = setup(sampleGraph(), { onLayoutPanelsChange });
      await settle();
      expect(seen.at(-1)).toBeNull();
      fireEvent.click(nodeEl("n1"));
      expect(seen.at(-1)?.node?.nodeId).toBe("n1");
      act(() => seen.at(-1)!.node!.props.onChange({ direction: "bt" }));
      expect(layoutOf(last(calls), "n1")).toEqual({ direction: "bt" });
      expect(calls.at(-1)!.meta.reason).toBe("layout");
      fireEvent.click(document.querySelector<HTMLElement>('.react-flow__edge[data-id="e1"]')!);
      expect(seen.at(-1)?.edge?.edgeId).toBe("e1");
      // 같은 선택·같은 그래프에서는 반복 호출하지 않는다(렌더가 흔들려도 값이 같으면 한 번)
      const n = onLayoutPanelsChange.mock.calls.length;
      await settle();
      expect(onLayoutPanelsChange.mock.calls.length).toBe(n);
    }));
});

describe("핸들 이동 (Alt+드래그 · 롱프레스)", () => {
  const boxOf = (el: HTMLElement) => {
    el.getBoundingClientRect = () => ({ left: 100, top: 100, width: 200, height: 100, right: 300, bottom: 200, x: 100, y: 100, toJSON() {} }) as DOMRect;
  };
  const handleEl = (nodeId: string, handleId: string) => nodeEl(nodeId).querySelector<HTMLElement>(`.react-flow__handle[data-handleid="${handleId}"]`)!;

  it("Alt+드래그로 노드 아래쪽에 놓으면 그 포트의 면이 bottom으로 저장된다(onChange 1회, reason layout)", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      const cardEl = nodeEl("n1").querySelector<HTMLElement>(".ac-ge-node")!;
      boxOf(cardEl);
      const h = handleEl("n1", "out:out");
      expect(h).toBeTruthy();
      fireEvent.pointerDown(h, { button: 0, altKey: true, pointerId: 1, clientX: 300, clientY: 150 });
      expect(cardEl.getAttribute("data-port-move")).toBe("true");
      fireEvent.pointerMove(window, { pointerId: 1, clientX: 200, clientY: 260 });
      expect(cardEl.getAttribute("data-port-move-side")).toBe("bottom");
      expect(calls).toHaveLength(0); // 드래그 중에는 내보내지 않는다
      fireEvent.pointerUp(window, { pointerId: 1, clientX: 200, clientY: 260 });
      expect(calls).toHaveLength(1);
      expect(calls[0]!.meta.reason).toBe("layout");
      expect(layoutOf(last(calls))).toEqual({ ports: { "out:out": "bottom" } });
      expect(cardEl.hasAttribute("data-port-move")).toBe(false);
      expect(live()).toBe("포트 출력을 아래으로 이동");
    }));

  it("원래 면에 놓거나 Esc로 취소하면 아무것도 바뀌지 않는다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      const cardEl = nodeEl("n1").querySelector<HTMLElement>(".ac-ge-node")!;
      boxOf(cardEl);
      const h = handleEl("n1", "out:out");
      fireEvent.pointerDown(h, { button: 0, altKey: true, pointerId: 1, clientX: 300, clientY: 150 });
      fireEvent.pointerUp(window, { pointerId: 1, clientX: 320, clientY: 150 }); // 여전히 오른쪽
      expect(calls).toHaveLength(0);
      fireEvent.pointerDown(h, { button: 0, altKey: true, pointerId: 2, clientX: 300, clientY: 150 });
      fireEvent.pointerMove(window, { pointerId: 2, clientX: 200, clientY: 20 });
      fireEvent.keyDown(window, { key: "Escape" });
      fireEvent.pointerUp(window, { pointerId: 2, clientX: 200, clientY: 20 });
      expect(calls).toHaveLength(0);
      expect(live()).toBe("포트 이동을 취소했습니다.");
    }));

  it("롱프레스 400ms 뒤에 이동 모드가 되고, 그 전에 움직이면 이동 모드가 되지 않는다(연결 드래그)", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph());
      await settle();
      const cardEl = nodeEl("n1").querySelector<HTMLElement>(".ac-ge-node")!;
      boxOf(cardEl);
      const h = handleEl("n1", "out:out");
      fireEvent.pointerDown(h, { button: 0, pointerId: 1, clientX: 300, clientY: 150 });
      fireEvent.pointerMove(window, { pointerId: 1, clientX: 330, clientY: 150 }); // 4px 넘게 움직임
      await act(async () => { await new Promise((r) => setTimeout(r, 450)); });
      expect(cardEl.hasAttribute("data-port-move")).toBe(false);
      fireEvent.pointerUp(window, { pointerId: 1 });

      fireEvent.pointerDown(h, { button: 0, pointerId: 3, clientX: 300, clientY: 150 });
      await act(async () => { await new Promise((r) => setTimeout(r, 450)); });
      expect(cardEl.getAttribute("data-port-move")).toBe("true");
      fireEvent.pointerMove(window, { pointerId: 3, clientX: 90, clientY: 150 });
      fireEvent.pointerUp(window, { pointerId: 3 });
      expect(layoutOf(last(calls))).toEqual({ ports: { "out:out": "left" } });
    }));

  it("읽기 전용에서는 이동 모드에 들어가지 않는다", () =>
    withLayout(async () => {
      const { calls } = setup(sampleGraph(), { readOnly: true });
      await settle();
      const cardEl = nodeEl("n1").querySelector<HTMLElement>(".ac-ge-node")!;
      const h = handleEl("n1", "out:out");
      fireEvent.pointerDown(h, { button: 0, altKey: true, pointerId: 1, clientX: 300, clientY: 150 });
      expect(cardEl.hasAttribute("data-port-move")).toBe(false);
      expect(calls).toHaveLength(0);
    }));
});
