import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import type { Graph } from "@agent-console/contracts";
import { GraphEditor } from "./index";
import { createAStarRouter } from "./index";
import type { ChangeMeta, EdgeRouter, GraphEditorProps } from "./index";
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

const withShape = (shape: string): Graph => {
  const g = sampleGraph();
  return { ...g, edges: g.edges!.map((e) => ({ ...e, layout: { shape } })) };
};
const pathD = (id: string): string => document.querySelector<SVGPathElement>(`.react-flow__edge[data-id="${id}"] path.ac-ge-edge`)?.getAttribute("d") ?? "";

/** route() 호출을 세는 라우터(내부는 실제 A*) */
function countingRouter(): EdgeRouter & { batches: string[][]; created: number } {
  const inner = createAStarRouter();
  const r = {
    id: inner.id,
    batches: [] as string[][],
    created: 1,
    route: (...a: Parameters<typeof inner.route>) => {
      r.batches.push(a[0].map((q) => q.id));
      return inner.route(...a);
    },
  };
  return r;
}

describe("자동 경로 렌더 연결 (3R.27)", () => {
  it("모양 auto인 연결선은 라우터 결과(직각 경로)로 그려지고 모든 엣지를 한 번에 계산한다", async () => {
    await withLayout(async () => {
      const router = countingRouter();
      render(<Harness initial={withShape("auto")} calls={[]} over={{ edgeRouter: router }} />);
      await settle();
      const d = pathD("e1");
      expect(d).not.toBe("");
      expect(d).not.toMatch(/C/); // 곡선이 아니다
      expect(router.batches.length).toBeGreaterThan(0);
      // 한 번의 route() 호출에 보이는 엣지가 함께 들어간다(엣지별 호출 금지)
      expect(router.batches.every((b) => b.length >= 2)).toBe(true);
      expect(document.querySelector('.react-flow__edge[data-id="e1"] [data-route-fallback]')).toBeNull();
    });
  });
  it("모양이 auto가 아니면 라우터를 만들지도 부르지도 않는다(명시한 곡선)", async () => {
    await withLayout(async () => {
      const router = countingRouter();
      render(<Harness initial={withShape("bezier")} calls={[]} over={{ edgeRouter: router }} />);
      await settle();
      expect(router.batches).toEqual([]);
      expect(pathD("e1")).toMatch(/C/);
    });
  });
  it("layout 없는 새 연결은 기본이 자동 경로이고 layout을 쓰지 않는다 (5.2R.23)", async () => {
    await withLayout(async () => {
      const router = countingRouter();
      const calls: Array<{ next: Graph; meta: ChangeMeta }> = [];
      render(<Harness initial={sampleGraph()} calls={calls} over={{ edgeRouter: router }} />);
      await settle();
      expect(router.batches.length).toBeGreaterThan(0);
      expect(pathD("e1")).not.toMatch(/C/);
      expect(calls).toEqual([]);
    });
  });
  it("직접 고친 선(경유점·bend 등)은 shape가 없어도 이전 기본(곡선)으로 읽는다 (5.2R.23)", async () => {
    await withLayout(async () => {
      const router = countingRouter();
      const g = sampleGraph();
      g.edges = g.edges!.map((e) => ({ ...e, layout: { bend: 0.3 } }));
      render(<Harness initial={g} calls={[]} over={{ edgeRouter: router }} />);
      await settle();
      expect(router.batches).toEqual([]);
      expect(pathD("e1")).toMatch(/C/);
    });
  });
  it("탐색 상한을 넘으면 대체 경로로 그리고 data-route-fallback을 단다", async () => {
    await withLayout(async () => {
      const router = createAStarRouter({ maxExpansions: 1 });
      render(<Harness initial={withShape("auto")} calls={[]} over={{ edgeRouter: router }} />);
      await settle();
      expect(document.querySelectorAll("[data-route-fallback='true']").length).toBeGreaterThan(0);
    });
  });
  it("노드를 옮기면(그래프 좌표 변경) 경로를 다시 계산한다", async () => {
    await withLayout(async () => {
      const router = countingRouter();
      const view = (g: Graph) => (
        <div style={{ width: 1000, height: 600 }}>
          <GraphEditor graph={g} nodeTypes={descriptors} edgeTypes={edgeTypes} showMinimap={false} onChange={() => {}} edgeRouter={router} />
        </div>
      );
      const r = render(view(withShape("auto")));
      await settle();
      const before = pathD("e1");
      const n = router.batches.length;
      const moved = withShape("auto");
      moved.nodes = moved.nodes!.map((x) => (x.id === "n2" ? { ...x, position: { x: 300, y: 320 } } : x));
      r.rerender(view(moved));
      await settle(300);
      expect(router.batches.length).toBeGreaterThan(n);
      expect(pathD("e1")).not.toBe(before);
    });
  });
});

describe("실행 상세 [연결선 ▾] 보기 전용 덮어쓰기 (graph-edges §7)", () => {
  it("자동 경로로 보기를 고르면 칩이 뜨고 모양만 바뀌며 어떤 onChange도 나가지 않는다", async () => {
    await withLayout(async () => {
      const calls: Array<{ next: Graph; meta: ChangeMeta }> = [];
      render(<Harness initial={withShape("bezier")} calls={calls} over={{ mode: "readonly-run" }} />);
      await settle();
      expect(pathD("e1")).toMatch(/C/);
      fireEvent.change(screen.getByRole("combobox", { name: "연결선" }), { target: { value: "auto" } });
      await settle();
      expect(screen.getByText("임시 보기: 자동 경로")).toBeTruthy();
      expect(pathD("e1")).not.toMatch(/C/);
      // 해제하면 저장된 대로
      fireEvent.click(screen.getByRole("button", { name: "임시 보기 해제" }));
      await settle();
      expect(screen.queryByText("임시 보기: 자동 경로")).toBeNull();
      expect(pathD("e1")).toMatch(/C/);
      expect(calls).toEqual([]);
    });
  });
  it("저장된 경유점이 있는 연결선도 같은 모양으로 그리고(저장된 대로), 곡선으로 보기에서는 경유점을 쓰지 않는다", async () => {
    await withLayout(async () => {
      const g = sampleGraph();
      g.edges = g.edges!.map((e) => (e.id === "e1" ? { ...e, layout: { shape: "straight", waypoints: [{ x: 150, y: 300 }] } } : e));
      render(<Harness initial={g} calls={[]} over={{ mode: "readonly-run" }} />);
      await settle();
      expect(pathD("e1")).toContain("150");
      fireEvent.change(screen.getByRole("combobox", { name: "연결선" }), { target: { value: "bezier" } });
      await settle();
      expect(pathD("e1")).not.toContain("150,300");
      expect(pathD("e1")).toMatch(/C/);
    });
  });
  it("편집 모드에는 [연결선 ▾]이 없고, viewOverrides를 비우면 읽기 전용에서도 없다", async () => {
    await withLayout(async () => {
      render(<Harness initial={sampleGraph()} calls={[]} />);
      await settle();
      expect(screen.queryByRole("combobox", { name: "연결선" })).toBeNull();
      cleanup();
      render(<Harness initial={sampleGraph()} calls={[]} over={{ mode: "readonly-run", viewOverrides: [] }} />);
      await settle();
      expect(screen.queryByRole("combobox", { name: "연결선" })).toBeNull();
    });
  });
  it("읽기 전용에는 [정리]와 경로 편집 점이 없다", async () => {
    await withLayout(async () => {
      render(<Harness initial={withShape("auto")} calls={[]} over={{ mode: "readonly-run" }} />);
      await settle();
      expect(screen.queryByRole("button", { name: "정리" })).toBeNull();
      expect(document.querySelector("[data-wp], [data-mid]")).toBeNull();
    });
  });
});

describe("엉킨 연결 감지와 자동 경로", () => {
  it("라우터가 그리는 자동 경로 엣지는 가로지름 검사에서 빠지고, 대체 경로로 물러난 엣지는 검사한다", async () => {
    const { selfAvoidingOf } = await import("./components/useEdgeTrouble");
    const { BUILTIN_EDGE_SHAPES } = await import("./shapes/registry");
    const auto = BUILTIN_EDGE_SHAPES.find((s) => s.id === "auto")!;
    const bezier = BUILTIN_EDGE_SHAPES.find((s) => s.id === "bezier")!;
    const edge = (id: string, shape: typeof auto) => ({ id, source: "a", target: "b", data: { shape } }) as never;
    const routed = (fallback: boolean) => new Map([["x", { id: "x", fallback, points: [], path: auto.build({ source: { x: 0, y: 0, side: "right" }, target: { x: 50, y: 0, side: "left" }, waypoints: [], radius: 8, bend: 0.5, stub: 10 }) }]]);
    expect(selfAvoidingOf(routed(false))(edge("x", auto))).toBe(true);
    expect(selfAvoidingOf(undefined)(edge("x", auto))).toBe(true); // 계산 전
    expect(selfAvoidingOf(routed(true))(edge("x", auto))).toBe(false);
    expect(selfAvoidingOf(routed(false))(edge("x", bezier))).toBe(false);
  });
});
