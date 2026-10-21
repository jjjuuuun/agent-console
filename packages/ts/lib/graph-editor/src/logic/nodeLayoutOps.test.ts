import { describe, expect, it } from "vitest";
import type { Graph } from "@agent-console/contracts";
import {
  applyNodeLayoutPatch,
  cycleDirection,
  moveNodesWithWaypoints,
  nearestSide,
  normalizeNodeLayout,
  orphanPortKeys,
  patchGraphUiLayout,
  patchNodeLayout,
  setNodeLayout,
  withPortSide,
} from "./nodeLayoutOps";

const graph = (): Graph => ({
  id: "g",
  name: "g",
  ui: { viewport: { x: 5, y: 6, zoom: 2 }, custom: 1 },
  nodes: [
    { id: "a", type: "t", position: { x: 0, y: 0 } },
    { id: "b", type: "t", position: { x: 200, y: 0 } },
    { id: "c", type: "t", position: { x: 400, y: 0 } },
  ],
  edges: [
    { id: "ab", kind: "k", source: { node: "a", port: "o" }, target: { node: "b", port: "i" }, layout: { shape: "step", waypoints: [{ x: 100, y: 50 }, { x: 150, y: 50 }] } },
    { id: "bc", kind: "k", source: { node: "b", port: "o" }, target: { node: "c", port: "i" }, layout: { waypoints: [{ x: 300, y: 80 }] } },
  ],
});

describe("normalizeNodeLayout (§5.4)", () => {
  it("빈 ports·null·빈 문자열은 키째 삭제하고 모두 비면 null", () => {
    expect(normalizeNodeLayout({ direction: "", ports: {} })).toBeNull();
    expect(normalizeNodeLayout({ direction: null, ports: null })).toBeNull();
    expect(normalizeNodeLayout(undefined)).toBeNull();
    expect(normalizeNodeLayout({ direction: "tb", ports: { "in:x": "" } })).toEqual({ direction: "tb" });
  });
  it("키 순서는 direction, ports이고 모르는 키는 그대로 통과한다", () => {
    const n = normalizeNodeLayout({ future: { a: 1 }, ports: { "out:r": "right" }, direction: "tb" });
    expect(Object.keys(n!)).toEqual(["direction", "ports", "future"]);
    expect(n!["future"]).toEqual({ a: 1 });
  });
});

describe("노드 layout 패치", () => {
  it("applyNodeLayoutPatch: null은 키 삭제(상속으로 되돌림)", () => {
    expect(applyNodeLayoutPatch({ direction: "tb", ports: { "in:i": "left" } }, { direction: null })).toEqual({ ports: { "in:i": "left" } });
    expect(applyNodeLayoutPatch({ direction: "tb" }, { direction: null })).toBeNull();
  });
  it("patchNodeLayout/setNodeLayout: 노드 하나만 바꾸고 입력은 건드리지 않으며 비면 layout 키를 지운다", () => {
    const g = graph();
    const a = patchNodeLayout(g, "a", { direction: "tb" });
    expect(a.nodes![0]!.layout).toEqual({ direction: "tb" });
    expect(g.nodes![0]!.layout).toBeUndefined();
    const b = setNodeLayout(a, "a", null);
    expect("layout" in b.nodes![0]!).toBe(false);
    expect(patchNodeLayout(g, "nope", { direction: "tb" })).toBe(g);
  });
  it("withPortSide: 포트 키 지정·삭제, 마지막 포트를 지우면 ports 키째 삭제", () => {
    const l = withPortSide(null, "out:r", "right");
    expect(l).toEqual({ ports: { "out:r": "right" } });
    expect(withPortSide(l, "out:r", null)).toBeNull();
    expect(withPortSide({ direction: "tb", ports: { "out:r": "right" } }, "out:r", null)).toEqual({ direction: "tb" });
  });
  it("orphanPortKeys: 사라진 포트의 키를 찾는다(데이터는 보존)", () => {
    expect(orphanPortKeys({ ports: { "in:a": "left", "out:z": "top" } }, new Set(["in:a"]))).toEqual(["out:z"]);
    expect(orphanPortKeys(null, new Set())).toEqual([]);
  });
});

describe("cycleDirection (R 키)", () => {
  const ids = ["lr", "tb", "rl", "bt"];
  it("lr → tb → rl → bt → 상속(null) → lr", () => {
    expect(cycleDirection(ids, null)).toBe("lr");
    expect(cycleDirection(ids, "lr")).toBe("tb");
    expect(cycleDirection(ids, "rl")).toBe("bt");
    expect(cycleDirection(ids, "bt")).toBeNull();
  });
  it("뒤로 돌기와 모르는 값, 빈 목록", () => {
    expect(cycleDirection(ids, null, -1)).toBe("bt");
    expect(cycleDirection(ids, "lr", -1)).toBeNull();
    expect(cycleDirection(ids, "zz")).toBe("lr");
    expect(cycleDirection([], "lr")).toBeNull();
  });
});

describe("nearestSide (핸들 이동)", () => {
  const box = { left: 100, top: 100, width: 200, height: 100 };
  it("상자 중심 기준 더 큰 축이 면을 정한다", () => {
    expect(nearestSide(box, { x: 90, y: 150 })).toBe("left");
    expect(nearestSide(box, { x: 310, y: 150 })).toBe("right");
    expect(nearestSide(box, { x: 200, y: 90 })).toBe("top");
    expect(nearestSide(box, { x: 200, y: 260 })).toBe("bottom");
  });
  it("상자 밖 먼 곳이나 크기 0이어도 결정된다", () => {
    expect(nearestSide(box, { x: 5000, y: 160 })).toBe("right");
    expect(nearestSide({ left: 0, top: 0, width: 0, height: 10 }, { x: 1, y: 1 })).toBeNull();
  });
});

describe("moveNodesWithWaypoints (§2.2)", () => {
  it("두 노드를 함께 옮기면 그 사이 엣지의 경유점도 같은 변위만큼 옮겨진다", () => {
    const g = graph();
    const next = moveNodesWithWaypoints(g, new Map([["a", { x: 16, y: 24 }], ["b", { x: 216, y: 24 }]]));
    expect(next.nodes![0]!.position).toMatchObject({ x: 16, y: 24 });
    expect(next.edges![0]!.layout!.waypoints).toEqual([{ x: 116, y: 74 }, { x: 166, y: 74 }]);
    expect(next.edges![0]!.layout!.shape).toBe("step");
    // 한쪽(b)만 옮겨진 bc 엣지는 제자리
    expect(next.edges![1]!.layout!.waypoints).toEqual([{ x: 300, y: 80 }]);
    expect(g.edges![0]!.layout!.waypoints).toEqual([{ x: 100, y: 50 }, { x: 150, y: 50 }]);
  });
  it("한쪽만 옮기면 경유점은 제자리, 변위 0인 노드는 옮겨진 것으로 치지 않는다", () => {
    const g = graph();
    expect(moveNodesWithWaypoints(g, new Map([["a", { x: 8, y: 0 }]])).edges![0]!.layout!.waypoints).toEqual([{ x: 100, y: 50 }, { x: 150, y: 50 }]);
    expect(moveNodesWithWaypoints(g, new Map([["a", { x: 8, y: 0 }], ["b", { x: 200, y: 0 }]])).edges![0]!.layout!.waypoints).toEqual([{ x: 100, y: 50 }, { x: 150, y: 50 }]);
  });
  it("경유점이 없는 엣지·layout 없는 엣지는 그대로(참조 유지)", () => {
    const g = graph();
    delete g.edges![0]!.layout;
    const next = moveNodesWithWaypoints(g, new Map([["a", { x: 8, y: 8 }], ["b", { x: 208, y: 8 }]]));
    expect(next.edges![0]).toBe(g.edges![0]);
  });
  it("소스 변위를 쓴다(격자 스냅으로 변위가 한 칸 안에서 다를 때)", () => {
    const g = graph();
    const next = moveNodesWithWaypoints(g, new Map([["a", { x: 8, y: 0 }], ["b", { x: 216, y: 0 }]]));
    expect(next.edges![0]!.layout!.waypoints![0]).toEqual({ x: 108, y: 50 });
  });
});

describe("patchGraphUiLayout (S4: Graph.ui 병합 저장)", () => {
  it("viewport 등 다른 ui 키와 layout의 모르는 키를 보존한다", () => {
    const g = graph();
    g.ui = { viewport: { x: 5, y: 6, zoom: 2 }, layout: { edge_shape: "auto", future: 1 } };
    const next = patchGraphUiLayout(g, { direction: "tb" });
    expect(next.ui).toEqual({ viewport: { x: 5, y: 6, zoom: 2 }, layout: { edge_shape: "auto", future: 1, direction: "tb" } });
    expect(g.ui!["layout"]).toEqual({ edge_shape: "auto", future: 1 });
  });
  it("null은 키를 지우고 layout이 비면 layout 키를, ui가 비면 ui 키를 지운다", () => {
    const g = graph();
    const set = patchGraphUiLayout(g, { direction: "tb" });
    const cleared = patchGraphUiLayout(set, { direction: null });
    expect(cleared.ui).toEqual({ viewport: { x: 5, y: 6, zoom: 2 }, custom: 1 });
    const bare: Graph = { id: "x", name: "x" };
    expect(patchGraphUiLayout(patchGraphUiLayout(bare, { direction: "tb" }), { direction: null })).toEqual(bare);
    expect("ui" in patchGraphUiLayout(patchGraphUiLayout(bare, { direction: "tb" }), { direction: null })).toBe(false);
  });
});
