import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Graph } from "@agent-console/contracts";
import { GraphEditor } from "./index";

const created = vi.hoisted(() => ({ n: 0 }));
vi.mock("./logic/route", async (orig) => {
  const m = await orig<typeof import("./logic/route")>();
  return { ...m, createAStarRouter: (...a: Parameters<typeof m.createAStarRouter>) => { created.n += 1; return m.createAStarRouter(...a); } };
});
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

const settle = (ms = 120) => act(async () => { await new Promise((r) => setTimeout(r, ms)); });
const view = (g: Graph) => (
  <div style={{ width: 1000, height: 600 }}>
    <GraphEditor graph={g} nodeTypes={descriptors} edgeTypes={edgeTypes} showMinimap={false} onChange={() => {}} />
  </div>
);
const withShape = (shape: string): Graph => {
  const g = sampleGraph();
  return { ...g, edges: g.edges!.map((e) => ({ ...e, layout: { shape } })) };
};

describe("기본 라우터 수명 (3R.27 QA)", () => {
  it("auto 엣지가 없으면 라우터를 만들지 않는다", async () => {
    await withLayout(async () => {
      created.n = 0;
      render(view(withShape("bezier")));
      await settle();
      expect(created.n).toBe(0);
    });
  });
  it("auto 엣지가 있으면 인스턴스당 1개만 만들고 재렌더·노드 이동에도 다시 만들지 않는다", async () => {
    await withLayout(async () => {
      created.n = 0;
      const r = render(view(withShape("auto")));
      await settle();
      expect(created.n).toBe(1);
      for (const y of [200, 260, 320]) {
        const g = withShape("auto");
        g.nodes = g.nodes!.map((x) => (x.id === "n2" ? { ...x, position: { x: 300, y } } : x));
        r.rerender(view(g));
        await settle(120);
      }
      expect(created.n).toBe(1);
    });
  });
});
