import { describe, expect, it } from "vitest";
import type { EdgeSpec, Graph } from "@agent-console/contracts";
import { anchorPositions, applyTidy, buildLayoutRequest, countEdgePaths, flowSideOf, resetAllEdgePaths } from "./tidy";
import type { TidyNodeView } from "./tidy";
import { BUILTIN_DIRECTIONS } from "./layout";

const view = (id: string, x: number, y: number): TidyNodeView => ({
  id,
  x,
  y,
  width: 100,
  height: 40,
  inputs: [{ id: "in", label: "in", side: "left" }],
  outputs: [{ id: "out", label: "out" }],
});
const edge = (id: string, a: string, b: string, kind = "k", layout?: EdgeSpec["layout"]): EdgeSpec =>
  ({ id, kind, source: { node: a, port: "out" }, target: { node: b, port: "in" }, ...(layout ? { layout } : {}) }) as EdgeSpec;

describe("buildLayoutRequest", () => {
  const nodes = [view("a", 0, 0), view("b", 200, 0), view("c", 400, 0)];
  const edges = [edge("e1", "a", "b"), edge("e2", "b", "c", "other")];
  it("범위가 전체면 모든 노드·엣지, 면은 해결된 값(없으면 입력=left·출력=right)", () => {
    const r = buildLayoutRequest({ nodes, edges, scope: null, excludedKinds: new Set(), flow: "right", options: { x: 1 } });
    expect(r.nodes.map((n) => n.id)).toEqual(["a", "b", "c"]);
    expect(r.edges.map((e) => e.id)).toEqual(["e1", "e2"]);
    expect(r.nodes[0]?.ports).toEqual([{ id: "in", io: "in", side: "left" }, { id: "out", io: "out", side: "right" }]);
    expect(r.options).toEqual({ x: 1 });
  });
  it("선택 범위는 범위 안 노드와 그 사이 엣지만, 제외한 종류는 엣지에서 빠진다", () => {
    const r = buildLayoutRequest({ nodes, edges, scope: new Set(["a", "b"]), excludedKinds: new Set(), flow: "right", options: {} });
    expect(r.nodes.map((n) => n.id)).toEqual(["a", "b"]);
    expect(r.edges.map((e) => e.id)).toEqual(["e1"]);
    const r2 = buildLayoutRequest({ nodes, edges, scope: null, excludedKinds: new Set(["other"]), flow: "right", options: {} });
    expect(r2.edges.map((e) => e.id)).toEqual(["e1"]);
    expect(r2.nodes).toHaveLength(3); // 제외한 종류의 노드는 그려지되 층 계산에서 엣지만 빠진다
  });
});

describe("anchorPositions", () => {
  it("결과 묶음의 좌상단을 계산 전 좌상단에 맞추고 격자에 맞춘다", () => {
    const out = anchorPositions({ positions: { a: { x: 10, y: 5 }, b: { x: 110, y: 5 } } }, [{ id: "a", x: 203, y: 101 }, { id: "b", x: 500, y: 300 }], 8);
    expect(out.get("a")).toEqual({ x: 200, y: 104 });
    expect(out.get("b")).toEqual({ x: 304, y: 104 });
  });
  it("결과에 없는 노드는 제외, 비면 빈 맵", () => {
    expect(anchorPositions({ positions: {} }, [{ id: "a", x: 0, y: 0 }], 8).size).toBe(0);
  });
});

describe("applyTidy", () => {
  const g = (): Graph => ({
    id: "g",
    name: "g",
    ui: { viewport: { zoom: 2 }, layout: { custom: 1 } },
    nodes: [
      { id: "a", type: "t", position: { x: 0, y: 0 }, layout: { direction: "tb" } },
      { id: "b", type: "t", position: { x: 0, y: 0 }, layout: { direction: "rl" } },
      { id: "c", type: "t", position: { x: 9, y: 9 }, layout: { direction: "bt" } },
    ],
    edges: [edge("e1", "a", "b", "k", { shape: "step", waypoints: [{ x: 1, y: 1 }], label_t: 0.3 }), edge("e2", "b", "c", "k", { waypoints: [{ x: 5, y: 5 }] })],
  });
  it("노드 이동 + 경로 지움 + 방향 정리 + ui.layout 기록을 한 그래프로 묶고 ui의 다른 키를 보존한다", () => {
    const next = applyTidy(g(), {
      positions: new Map([["a", { x: 8, y: 16 }], ["b", { x: 160, y: 16 }]]),
      direction: "lr",
      edgeShape: "smoothstep",
      edgeShapeByKind: { k: "bezier" },
      resetRoutes: true,
      alignNodeDirection: true,
      scope: new Set(["a", "b"]),
    });
    expect(next.nodes![0]!.position).toEqual({ x: 8, y: 16 });
    expect(next.nodes![0]!.layout?.direction).toBeUndefined();
    expect(next.nodes![2]!.layout?.direction).toBe("bt"); // 범위 밖
    expect(next.edges![0]!.layout).toEqual({ shape: "step" }); // 경로 키만 지움, 모양 유지
    expect(next.edges![1]!.layout?.waypoints).toHaveLength(1); // 범위 밖 엣지
    expect(next.ui).toEqual({ viewport: { zoom: 2 }, layout: { custom: 1, direction: "lr", edge_shape: "smoothstep", edge_shape_by_kind: { k: "bezier" } } });
  });
  it("옵션을 끄면 경로·노드 방향을 건드리지 않고, 모양 null은 키를 지운다", () => {
    const base = g();
    const withShape = applyTidy(base, { positions: new Map(), edgeShape: "x", resetRoutes: false, alignNodeDirection: false, scope: null });
    const next = applyTidy(withShape, { positions: new Map(), edgeShape: null, resetRoutes: false, alignNodeDirection: false, scope: null });
    expect(next.edges).toEqual(base.edges);
    expect(next.nodes![0]!.layout?.direction).toBe("tb");
    expect(next.ui).toEqual(base.ui);
  });
  it("아무 ui도 안 바꾸면 ui 객체를 만들지 않는다", () => {
    const base: Graph = { id: "g", name: "g", nodes: [{ id: "a", type: "t" }] };
    expect(applyTidy(base, { positions: new Map(), resetRoutes: true, alignNodeDirection: true, scope: null }).ui).toBeUndefined();
  });
});

describe("resetAllEdgePaths", () => {
  it("모든 엣지의 경로 키를 지우고 모양은 두며, 바뀐 게 없으면 같은 참조", () => {
    const g: Graph = { id: "g", name: "g", edges: [edge("e1", "a", "b", "k", { shape: "step", waypoints: [{ x: 1, y: 1 }], bend: 0.2 }), edge("e2", "a", "b", "k", { label_offset: { x: 1, y: 1 } }), edge("e3", "a", "b")] };
    expect(countEdgePaths(g)).toBe(2);
    const next = resetAllEdgePaths(g);
    expect(next.edges![0]!.layout).toEqual({ shape: "step" });
    expect(next.edges![1]!.layout).toBeUndefined();
    expect(countEdgePaths(next)).toBe(0);
    expect(resetAllEdgePaths(next)).toBe(next);
  });
});

describe("flowSideOf", () => {
  it("방향 표의 출력 면", () => {
    expect(flowSideOf(BUILTIN_DIRECTIONS, "tb")).toBe("bottom");
    expect(flowSideOf(BUILTIN_DIRECTIONS, "nope")).toBeNull();
    expect(flowSideOf({ diag: { in: "top", out: "right" } }, "diag")).toBe("right");
  });
});
