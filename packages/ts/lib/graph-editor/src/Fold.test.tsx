import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { EdgeTypeDescriptor, Graph, NodeTypeDescriptor } from "@agent-console/contracts";
import { GraphEditor } from "./index";
import type { GraphEditorProps } from "./index";

afterEach(cleanup);

/** 레이아웃이 없는 환경에서 모든 요소를 160x80으로 보이게 한다(라벨 크기도 160x80이라 노드 사이에 들어가지 않는다). Delegation.test.tsx와 같은 방식. */
async function withLayout(run: () => Promise<void>): Promise<void> {
  const original = globalThis.ResizeObserver;
  const proto = HTMLElement.prototype;
  const offW = Object.getOwnPropertyDescriptor(proto, "offsetWidth");
  const offH = Object.getOwnPropertyDescriptor(proto, "offsetHeight");
  Object.defineProperty(proto, "offsetWidth", { configurable: true, get(this: HTMLElement) { return this.classList.contains("react-flow") ? 1000 : 160; } });
  Object.defineProperty(proto, "offsetHeight", { configurable: true, get(this: HTMLElement) { return this.classList.contains("react-flow") ? 600 : 80; } });
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
const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 80)); });

const nodeTypes: NodeTypeDescriptor[] = [{ id: "q-plain", version: 1, title: "보통 노드", category: "c", static_ports: { inputs: [{ name: "in" }], outputs: [{ name: "out" }] } }];
const edgeTypes: EdgeTypeDescriptor[] = [{ id: "k-hinted", version: 1, title: "반복", scheduling: "flow", cycle: { max_iterations: 2 }, ui_hints: { icon: "★" } }];
const graph = (): Graph => ({
  id: "g",
  name: "g",
  nodes: [
    { id: "w", type: "q-plain", label: "작성자", position: { x: 0, y: 0 } },
    { id: "r", type: "q-plain", label: "검토", position: { x: 20, y: 10 } },
  ],
  edges: [{ id: "b1", kind: "k-hinted", source: { node: "r", port: "out" }, target: { node: "w", port: "in" } }],
});
const setup = (over: Partial<GraphEditorProps> = {}) =>
  render(
    <div style={{ width: 1000, height: 600 }}>
      <GraphEditor graph={graph()} nodeTypes={nodeTypes} edgeTypes={edgeTypes} showMinimap={false} {...over} />
    </div>,
  );
const extra = { b1: [{ key: "a", title: "최대 3회" }, { key: "b", title: "읽기 전용" }] };
const chip = () => document.querySelector<HTMLElement>('.ac-ge-edge-chip[data-badged="true"]')!;

describe("칩 접기(라벨 배치 양보 ③)", () => {
  it("자리가 모자라면 칩이 접히고, 이름·툴팁에 글자가 전부 있고, 초점을 주면 제자리에서 펼쳐진다", () =>
    withLayout(async () => {
      setup({ edgeExtraChips: extra });
      await settle();
      const c = chip();
      expect(c.getAttribute("data-folded")).toBe("true");
      expect(c.getAttribute("tabindex")).toBe("0");
      const name = c.getAttribute("aria-label") ?? "";
      expect(name).toContain("최대 3회");
      expect(name).toContain("읽기 전용");
      expect(c.querySelector(".ac-ge-fold-more")?.textContent).toBe("+2");
      expect(c.getAttribute("title")).toBe(name);
      fireEvent.focus(c);
      expect(c.getAttribute("data-expanded")).toBe("true");
      fireEvent.blur(c);
      expect(c.getAttribute("data-expanded")).toBeNull();
    }));

  it("labelSpacing.fold가 false이면 접지 않는다", () =>
    withLayout(async () => {
      setup({ edgeExtraChips: extra, labelSpacing: { fold: false } });
      await settle();
      expect(chip().getAttribute("data-folded")).toBeNull();
    }));
});
