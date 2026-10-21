import { describe, expect, it } from "vitest";
import type { EdgeTypeDescriptor, Graph, NodeTypeDescriptor } from "@agent-console/contracts";
import { defaultMessages } from "../messages";
import { actualNodeSize, buildRouteInput } from "./autoRoute";
import type { RouteNodeGeometry } from "./autoRoute";
import { buildFlowModel } from "./convert";
import { countResettableEdges, patchEdgesLayout } from "./edgeLayoutOps";
import { orderByPeer, placeHandles } from "./handles";
import { isAutoDirection, resolvePortSide } from "./layout";
import { patchNodesLayout } from "./nodeLayoutOps";
import { createAStarRouter } from "./route";
import type { PortView } from "./ports";

// 4R.20 연결선 P2 후속: 노드 방향 auto · 같은 면 핸들 순서 · 다중 선택 연산 · 실제 카드 크기 장애물

describe("isAutoDirection (노드 → 그래프 → 설정 → 힌트, 처음 유효한 값)", () => {
  it("노드가 auto면 그래프가 tb여도 auto다", () => {
    expect(isAutoDirection({ node: { direction: "auto" }, graph: { direction: "tb" } })).toBe(true);
  });
  it("노드가 tb면 그래프가 auto여도 auto가 아니다", () => {
    expect(isAutoDirection({ node: { direction: "tb" }, graph: { direction: "auto" } })).toBe(false);
  });
  it("모르는 값은 건너뛰고 다음 층을 본다(그래프 → 설정 → 힌트)", () => {
    expect(isAutoDirection({ node: { direction: "zz" }, graph: { direction: "auto" } })).toBe(true);
    expect(isAutoDirection({ settings: "auto" })).toBe(true);
    expect(isAutoDirection({ hint: "auto" })).toBe(true);
    expect(isAutoDirection({ node: { direction: "zz" }, graph: { direction: "yy" } })).toBe(false);
  });
  it("아무 층도 없으면 auto가 아니다", () => {
    expect(isAutoDirection({})).toBe(false);
  });
  it("방향 표에 auto가 없어도 auto는 유효한 값이다", () => {
    expect(isAutoDirection({ node: { direction: "auto" }, directions: { only: { in: "top", out: "bottom" } } })).toBe(true);
  });
});

describe("resolvePortSide autoDirection", () => {
  const base = { io: "out" as const, portId: "o", autoSide: "top" as const, autoDirection: true };
  it("포트별 지정이 없으면 파생 면을 쓴다", () => {
    expect(resolvePortSide(base)).toMatchObject({ side: "top", source: "auto" });
  });
  it("포트별로 명시한 면은 그대로다", () => {
    expect(resolvePortSide({ ...base, node: { ports: { "out:o": "left" } } })).toMatchObject({ side: "left", source: "port" });
  });
  it("파생 면이 없으면(연결 없음) 방향 기본값으로 내려간다", () => {
    expect(resolvePortSide({ ...base, autoSide: undefined })).toMatchObject({ side: "right" });
  });
  it("autoDirection이 꺼져 있으면 파생 면을 쓰지 않는다", () => {
    expect(resolvePortSide({ ...base, autoDirection: false })).toMatchObject({ side: "right" });
  });
});

const nodeTypes: NodeTypeDescriptor[] = [
  { id: "t", version: 1, title: "T", category: "c", static_ports: { inputs: [{ name: "a" }, { name: "b" }], outputs: [{ name: "o" }] } },
  { id: "s", version: 1, title: "S", category: "c", static_ports: { inputs: [{ name: "i" }], outputs: [{ name: "o" }] } },
];
const edgeTypes: EdgeTypeDescriptor[] = [{ id: "k", title: "k" }];
const model = (g: Graph) =>
  buildFlowModel({ graph: g, nodeTypes, edgeTypes, resolved: new Map(), nodeStates: {}, edgeStates: {}, selectedNodes: new Set(), selectedEdges: new Set(), positionOverrides: new Map(), readOnly: false, messages: defaultMessages, markerId: "m" });
const portsOf = (g: Graph, id: string): PortView[] => {
  const n = model(g).nodes.find((x) => x.id === id)!;
  return [...n.data.inputs, ...n.data.outputs];
};

describe("노드 방향 auto (buildFlowModel, 저장 안 함)", () => {
  const graph = (hubLayout: Record<string, unknown> | undefined): Graph => ({
    id: "g", name: "g",
    nodes: [
      { id: "hub", type: "t", config: {}, position: { x: 0, y: 300 }, ...(hubLayout ? { layout: hubLayout } : {}) },
      { id: "up", type: "s", config: {}, position: { x: 0, y: 0 } },
      { id: "right", type: "s", config: {}, position: { x: 700, y: 300 } },
    ],
    edges: [
      { id: "e1", kind: "k", source: { node: "up", port: "o" }, target: { node: "hub", port: "a" } },
      { id: "e2", kind: "k", source: { node: "hub", port: "o" }, target: { node: "right", port: "i" } },
    ],
  });
  it("연결된 상대가 있는 쪽으로 모든 포트의 면이 정해진다", () => {
    const sides = Object.fromEntries(portsOf(graph({ direction: "auto" }), "hub").map((p) => [p.id, p.side]));
    expect(sides).toMatchObject({ a: "top", o: "right" });
    expect(sides["b"]).toBe("left"); // 연결 없음 -> 방향 기본값
  });
  it("포트별로 명시한 면은 auto보다 우선한다", () => {
    const sides = Object.fromEntries(portsOf(graph({ direction: "auto", ports: { "in:a": "bottom" } }), "hub").map((p) => [p.id, p.side]));
    expect(sides["a"]).toBe("bottom");
    expect(sides["o"]).toBe("right");
  });
  it("그래프 방향이 auto면 노드가 따로 정하지 않은 노드에 적용된다", () => {
    const g = graph(undefined);
    g.ui = { layout: { direction: "auto" } };
    expect(Object.fromEntries(portsOf(g, "hub").map((p) => [p.id, p.side]))["a"]).toBe("top");
  });
  it("auto 방향은 파생 값이라 그래프를 바꾸지 않는다", () => {
    const g = graph({ direction: "auto" });
    const before = JSON.stringify(g);
    model(g);
    expect(JSON.stringify(g)).toBe(before);
  });
  it("layout이 없는 그래프는 기본 배치 그대로다(핸들 offset 없음)", () => {
    for (const p of portsOf(graph(undefined), "hub")) expect(p.offset).toBeUndefined();
  });
});

describe("같은 면 핸들 순서를 상대 노드 위치로 정렬 (§3.3)", () => {
  it("orderByPeer: 상대가 있는 항목만 키 순으로 다시 늘어놓고 없는 항목은 제자리다", () => {
    const keys: Record<string, number | undefined> = { a: 30, b: undefined, c: 10, d: 20 };
    expect(orderByPeer(["a", "b", "c", "d"], (x) => keys[x])).toEqual(["c", "b", "d", "a"]);
  });
  it("orderByPeer: 같은 값이면 원래 순서를 지킨다", () => {
    expect(orderByPeer(["x", "y", "z"], () => 5)).toEqual(["x", "y", "z"]);
  });

  const port = (id: string, side: PortView["side"]): PortView => (side === undefined ? { id, label: id } : { id, label: id, side });
  it("위 면 입력 두 개: 상대가 왼쪽에 있는 포트가 왼쪽에 놓인다", () => {
    const peers: Record<string, { x: number; y: number }> = { a: { x: 600, y: 0 }, b: { x: 0, y: 0 } };
    const placed = placeHandles({ inputs: [port("a", "top"), port("b", "top")], outputs: [], width: 200, peerOf: (_io, id) => peers[id] });
    const a = placed.inputs.find((p) => p.id === "a")!.offset!;
    const b = placed.inputs.find((p) => p.id === "b")!.offset!;
    expect(b).toBeLessThan(a);
  });
  it("peerOf가 없으면 포트 목록 순서 그대로다", () => {
    const placed = placeHandles({ inputs: [port("a", "top"), port("b", "top")], outputs: [], width: 200 });
    expect(placed.inputs[0]!.offset!).toBeLessThan(placed.inputs[1]!.offset!);
  });
  it("좌·우 면에 입출력이 섞이면 상대의 세로 위치 순서로 늘어선다", () => {
    const peers: Record<string, { x: number; y: number }> = { i: { x: 0, y: 500 }, o: { x: 0, y: -500 } };
    const placed = placeHandles({ inputs: [port("i", "left")], outputs: [port("o", "left")], width: 200, peerOf: (_io, id) => peers[id] });
    expect(placed.outputs[0]!.offset!).toBeLessThan(placed.inputs[0]!.offset!);
  });
  it("상대를 모르는 포트만 있으면 순서가 바뀌지 않는다", () => {
    const placed = placeHandles({ inputs: [port("a", "top"), port("b", "top")], outputs: [], width: 200, peerOf: () => undefined });
    expect(placed.inputs[0]!.offset!).toBeLessThan(placed.inputs[1]!.offset!);
  });
  it("buildFlowModel: tb 방향에서 입력 포트 순서가 상대 위치를 따라 교차하지 않는다", () => {
    const g: Graph = {
      id: "g", name: "g",
      nodes: [
        { id: "hub", type: "t", config: {}, position: { x: 300, y: 300 }, layout: { direction: "tb" } },
        { id: "l", type: "s", config: {}, position: { x: 0, y: 0 } },
        { id: "r", type: "s", config: {}, position: { x: 700, y: 0 } },
      ],
      // a는 오른쪽 노드, b는 왼쪽 노드에서 온다 -> 목록 순서대로면 선이 교차한다
      edges: [
        { id: "e1", kind: "k", source: { node: "r", port: "o" }, target: { node: "hub", port: "a" } },
        { id: "e2", kind: "k", source: { node: "l", port: "o" }, target: { node: "hub", port: "b" } },
      ],
    };
    const ps = portsOf(g, "hub");
    expect(ps.find((p) => p.id === "b")!.offset!).toBeLessThan(ps.find((p) => p.id === "a")!.offset!);
  });
});

describe("다중 선택 연산", () => {
  const g: Graph = {
    id: "g", name: "g",
    nodes: [
      { id: "n1", type: "s", config: {}, position: { x: 0, y: 0 }, layout: { direction: "tb" } },
      { id: "n2", type: "s", config: {}, position: { x: 0, y: 0 } },
      { id: "n3", type: "s", config: {}, position: { x: 0, y: 0 } },
    ],
    edges: [
      { id: "e1", kind: "k", source: { node: "n1", port: "o" }, target: { node: "n2", port: "i" }, layout: { shape: "smoothstep", waypoints: [{ x: 1, y: 2 }], label_t: 0.3 } },
      { id: "e2", kind: "k", source: { node: "n2", port: "o" }, target: { node: "n3", port: "i" }, layout: { shape: "step" } },
      { id: "e3", kind: "k", source: { node: "n1", port: "o" }, target: { node: "n3", port: "i" } },
    ],
  };
  it("patchEdgesLayout: 고른 엣지 전부에 모양을 쓰고 나머지는 그대로다", () => {
    const next = patchEdgesLayout(g, ["e1", "e3"], { shape: "auto" });
    expect(next.edges!.map((e) => e.layout?.shape)).toEqual(["auto", "step", "auto"]);
    expect(next.edges![0]!.layout!.waypoints).toEqual([{ x: 1, y: 2 }]);
    expect(g.edges![0]!.layout!.shape).toBe("smoothstep"); // 입력은 바꾸지 않는다
  });
  it("patchEdgesLayout: null이면 상속으로 돌리고, 모두 비면 layout 키를 지운다", () => {
    const next = patchEdgesLayout(g, ["e2"], { shape: null });
    expect(next.edges![1]).not.toHaveProperty("layout");
  });
  it("patchEdgesLayout: 바뀔 것이 없으면 같은 그래프를 돌려준다", () => {
    expect(patchEdgesLayout(g, ["e1", "e2"], { waypoints: null, bend: null }) === g).toBe(false); // e1 경유점이 지워진다
    expect(patchEdgesLayout(g, ["e3"], { waypoints: null })).toBe(g);
    expect(patchEdgesLayout(g, ["nope"], { shape: "x" })).toBe(g);
  });
  it("경로 초기화는 경유점·꺾임·라벨 위치만 지우고 모양을 남긴다", () => {
    const next = patchEdgesLayout(g, ["e1", "e2", "e3"], { waypoints: null, bend: null, label_t: null, label_offset: null });
    expect(next.edges![0]!.layout).toEqual({ shape: "smoothstep" });
    expect(next.edges![1]!.layout).toEqual({ shape: "step" });
  });
  it("countResettableEdges: 지울 경로가 있는 엣지만 센다", () => {
    expect(countResettableEdges(g, ["e1", "e2", "e3"])).toBe(1);
    expect(countResettableEdges(g, ["e2", "e3"])).toBe(0);
  });
  it("patchNodesLayout: 여러 노드의 방향을 한 번에 정하고 null이면 지운다", () => {
    const next = patchNodesLayout(g, ["n1", "n2"], { direction: "rl" });
    expect(next.nodes!.map((n) => n.layout?.direction)).toEqual(["rl", "rl", undefined]);
    const cleared = patchNodesLayout(next, ["n1", "n2"], { direction: null });
    expect(cleared.nodes![0]).not.toHaveProperty("layout");
    expect(patchNodesLayout(g, ["n3"], { direction: null })).toBe(g);
  });
});

describe("실제 렌더된 카드 크기를 장애물로 쓴다 (D13, 7px 스침)", () => {
  it("actualNodeSize: 그려진 크기 → 측정값 → 추정값 순이고 가로·세로를 따로 고른다", () => {
    expect(actualNodeSize({ rendered: { width: 200, height: 120 }, measured: { width: 160, height: 80 }, declared: { width: 150, height: 70 } })).toEqual({ width: 200, height: 120 });
    expect(actualNodeSize({ measured: { width: 160, height: 80 }, declared: { width: 150, height: 70 } })).toEqual({ width: 160, height: 80 });
    expect(actualNodeSize({ measured: { width: 0, height: undefined }, declared: { width: 150, height: 70 } })).toEqual({ width: 150, height: 70 });
    expect(actualNodeSize({})).toEqual({ width: 0, height: 0 });
  });

  const geo = (id: string, x: number, y: number, w: number, h: number): RouteNodeGeometry => ({
    id, x, y, width: w, height: h,
    source: [{ id: "out:o", x: w, y: h / 2 - 5, width: 10, height: 10, position: "right" }],
    target: [{ id: "in:i", x: -10, y: h / 2 - 5, width: 10, height: 10, position: "left" }],
  });
  /** 경로 점들에서 사각형까지의 최소 거리(축 정렬 선분) */
  const clearance = (pts: readonly { x: number; y: number }[], r: { x: number; y: number; width: number; height: number }): number => {
    let best = Number.POSITIVE_INFINITY;
    for (let i = 1; i < pts.length; i += 1) {
      const a = pts[i - 1]!, b = pts[i]!;
      const lx = Math.min(a.x, b.x), hx = Math.max(a.x, b.x), ly = Math.min(a.y, b.y), hy = Math.max(a.y, b.y);
      const dx = Math.max(r.x - hx, 0, lx - (r.x + r.width));
      const dy = Math.max(r.y - hy, 0, ly - (r.y + r.height));
      best = Math.min(best, Math.hypot(dx, dy));
    }
    return best;
  };

  it("추정보다 큰 실제 카드(요약 줄 등)를 장애물로 쓰면 경로가 카드에서 패딩 16px 이상 떨어진다", () => {
    // 실행 상세의 가운데 카드는 편집기 추정(높이 72)보다 키가 크다(실제 120).
    const estimated = { id: "mid", x: 240, y: 0, width: 160, height: 72 };
    const rendered = { id: "mid", x: 240, y: 0, width: 160, height: 120 };
    const run = (mid: typeof rendered) => {
      const nodes = new Map([["a", geo("a", 0, 40, 160, 72)], ["b", geo("b", 640, 40, 160, 72)], ["mid", geo("mid", mid.x, mid.y, mid.width, mid.height)]]);
      const { requests, obstacles } = buildRouteInput([{ id: "e", source: "a", target: "b", sourceHandle: "out:o", targetHandle: "in:i" }], nodes);
      // 시간 상한(기본 8ms)은 고부하에서 fallback을 낳으므로 시계 대신 확장 수 상한만 쓴다(5.2R.42).
      return createAStarRouter({ maxMillis: 60_000 }).route(requests, obstacles).get("e")!;
    };
    const sized = actualNodeSize({ rendered: { width: 160, height: 120 }, measured: { width: 160, height: 72 } });
    expect(sized.height).toBe(120);
    // 추정 크기로 계산한 경로는 실제 카드에 16px보다 가깝게 붙는다(문제), 실제 크기로 계산하면 16px 이상 떨어진다(해결)
    expect(clearance(run(estimated).points, rendered)).toBeLessThan(16);
    expect(clearance(run({ ...rendered, ...sized }).points, rendered)).toBeGreaterThanOrEqual(16);
  });
});

import { pushOutOfRects, pushWaypointsOut } from "./waypointClearance";

describe("읽기 전용 경유점 밀어내기 (4R.20 결정)", () => {
  const card = { x: 100, y: 100, width: 200, height: 120 };
  it("카드 밖(여백 밖)의 점은 그대로다", () => {
    const p = { x: 40, y: 50 };
    expect(pushOutOfRects(p, [card])).toBe(p);
  });
  it("카드 안의 점은 가장 가까운 면 바깥(여백 16px)으로 밀린다", () => {
    expect(pushOutOfRects({ x: 110, y: 160 }, [card])).toEqual({ x: 84, y: 160 }); // 왼쪽 면이 가장 가깝다
    expect(pushOutOfRects({ x: 200, y: 105 }, [card])).toEqual({ x: 200, y: 84 }); // 위
    expect(pushOutOfRects({ x: 290, y: 160 }, [card])).toEqual({ x: 316, y: 160 }); // 오른쪽
  });
  it("여백 안쪽(카드 밖이지만 16px 이내)도 밀린다", () => {
    expect(pushOutOfRects({ x: 90, y: 160 }, [card])).toEqual({ x: 84, y: 160 });
  });
  it("밀린 점이 다른 카드에 들어가면 다시 밀고, 두 카드 사이 틈이 좁아 갈 곳이 없어도 끝난다", () => {
    const wide = { x: 100, y: 100, width: 200, height: 120 };
    const above = { x: 100, y: 0, width: 200, height: 40 }; // 여백을 합쳐도 wide와 겹치지 않는 위쪽 카드
    const r = pushOutOfRects({ x: 200, y: 105 }, [wide, above]);
    expect(r).toEqual({ x: 200, y: 84 });
    const narrow = { x: 20, y: 100, width: 50, height: 120 }; // wide와의 틈이 2*여백보다 좁다
    const stuck = pushOutOfRects({ x: 110, y: 160 }, [wide, narrow]);
    expect(Number.isFinite(stuck.x) && Number.isFinite(stuck.y)).toBe(true);
  });
  it("pushWaypointsOut: 바뀐 점이 없으면 같은 배열, 입력은 바꾸지 않는다", () => {
    const outside = [{ x: 0, y: 0 }];
    expect(pushWaypointsOut(outside, [card])).toBe(outside);
    const inside = [{ x: 200, y: 160 }];
    const out = pushWaypointsOut(inside, [card]);
    expect(out).not.toBe(inside);
    expect(inside).toEqual([{ x: 200, y: 160 }]);
  });
});
