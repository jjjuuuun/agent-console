import { describe, expect, it } from "vitest";
import type { EdgeTypeDescriptor, Graph, NodeTypeDescriptor } from "@agent-console/contracts";
import { defaultMessages } from "../messages";
import { buildFlowModel } from "./convert";
import { deriveAutoSides } from "./autoSide";
import type { AutoSideBox, AutoSideEdge } from "./autoSide";

const box = (x: number, y: number): AutoSideBox => ({ x, y, width: 100, height: 60 });
const E = (a: string, ap: string, b: string, bp: string): AutoSideEdge => ({ source: { node: a, port: ap }, target: { node: b, port: bp } });
const want = (m: Record<string, string[]>) => new Map(Object.entries(m).map(([k, v]) => [k, new Set(v)]));

describe("deriveAutoSides (graph-edges §4.3)", () => {
  const boxes = new Map([["a", box(0, 0)], ["b", box(300, 0)], ["c", box(0, 300)], ["d", box(-300, 0)]]);

  it("상대가 가로로 크게 떨어져 있으면 좌/우, 세로면 상/하(출력·입력 모두 상대가 있는 쪽)", () => {
    const r = deriveAutoSides(boxes, [E("a", "o", "b", "i"), E("a", "o2", "c", "i"), E("d", "o", "a", "i")], want({ a: ["out:o", "out:o2", "in:i"], b: ["in:i"], c: ["in:i"] }));
    expect(r.get("a")?.get("out:o")).toBe("right");
    expect(r.get("a")?.get("out:o2")).toBe("bottom");
    expect(r.get("a")?.get("in:i")).toBe("left");
    expect(r.get("b")?.get("in:i")).toBe("left");
    expect(r.get("c")?.get("in:i")).toBe("top");
  });

  it("연결이 없거나 요청하지 않은 포트는 결과에 없다(방향 기본값은 호출 쪽)", () => {
    const r = deriveAutoSides(boxes, [E("a", "o", "b", "i")], want({ a: ["out:none"] }));
    expect(r.get("a")?.has("out:none")).not.toBe(true);
    expect(r.get("b")).toBeUndefined();
  });

  it("여러 연결은 상대 방향(단위 벡터)의 합으로 정하고 상쇄되면 남은 성분으로 정한다", () => {
    const two = deriveAutoSides(boxes, [E("a", "o", "b", "i"), E("a", "o", "c", "i"), E("a", "o", "d", "i")], want({ a: ["out:o"] }));
    expect(two.get("a")?.get("out:o")).toBe("bottom"); // 오른쪽·왼쪽 상쇄, 아래만 남음
    const zero = deriveAutoSides(boxes, [E("a", "o", "b", "i"), E("a", "o", "d", "i")], want({ a: ["out:o"] }));
    expect(zero.get("a")?.has("out:o")).not.toBe(true); // 완전 상쇄면 정하지 않음
  });

  it("가로·세로가 같으면 가로, 같은 위치·모르는 노드는 무시한다", () => {
    const tie = deriveAutoSides(new Map([["a", box(0, 0)], ["b", box(100, 100)]]), [E("a", "o", "b", "i")], want({ a: ["out:o"] }));
    expect(tie.get("a")?.get("out:o")).toBe("right");
    const none = deriveAutoSides(new Map([["a", box(0, 0)], ["b", box(0, 0)]]), [E("a", "o", "b", "i"), E("a", "o", "zz", "i")], want({ a: ["out:o"] }));
    expect(none.get("a")?.has("out:o")).not.toBe(true);
  });

  it("결정적이다(같은 입력 → 같은 결과)", () => {
    const edges = [E("a", "o", "b", "i"), E("a", "o", "c", "i")];
    const w = want({ a: ["out:o"] });
    expect([...deriveAutoSides(boxes, edges, w).get("a")!]).toEqual([...deriveAutoSides(boxes, edges, w).get("a")!]);
  });
});

describe("스크린샷 사례: 포트 면 auto만으로 풀린다 (graph-edges §3.5)", () => {
  const nodeTypes: NodeTypeDescriptor[] = [
    { id: "user", version: 1, title: "사용자", category: "c", static_ports: { inputs: [{ name: "in" }], outputs: [{ name: "out" }] } },
    { id: "agent", version: 1, title: "에이전트", category: "c", static_ports: { inputs: [{ name: "task" }], outputs: [{ name: "result" }] } },
  ];
  const edgeTypes: EdgeTypeDescriptor[] = [{ id: "k", title: "k" }];
  const autoAll = (io: "in" | "out", ids: string[]) => Object.fromEntries(ids.map((p) => [`${io}:${p}`, "auto"]));
  const graph = (agentY: number, auto = true): Graph => ({
    id: "g", name: "g",
    nodes: [
      { id: "u", type: "user", label: "U", config: {}, position: { x: 0, y: 0 }, ...(auto ? { layout: { ports: { ...autoAll("in", ["in"]), ...autoAll("out", ["out"]) } } } : {}) },
      { id: "a", type: "agent", label: "A", config: {}, position: { x: 0, y: agentY }, ...(auto ? { layout: { ports: { ...autoAll("in", ["task"]), ...autoAll("out", ["result"]) } } } : {}) },
    ],
    edges: [
      { id: "e1", kind: "k", source: { node: "u", port: "out" }, target: { node: "a", port: "task" } },
      { id: "e2", kind: "k", source: { node: "a", port: "result" }, target: { node: "u", port: "in" } },
    ],
  });
  const sides = (g: Graph, over = new Map<string, { x: number; y: number }>()) => {
    const m = buildFlowModel({
      graph: g, nodeTypes, edgeTypes, resolved: new Map(), nodeStates: {}, edgeStates: {},
      selectedNodes: new Set(), selectedEdges: new Set(), positionOverrides: over, readOnly: false,
      messages: defaultMessages, markerId: "m",
    });
    const out: Record<string, string> = {};
    for (const n of m.nodes) for (const p of [...n.data.inputs, ...n.data.outputs]) out[`${n.id}.${p.id}`] = p.side ?? "";
    return out;
  };

  it("사용자가 위, 에이전트가 아래면 서로 마주 보는 면이 된다", () => {
    expect(sides(graph(300))).toEqual({ "u.in": "bottom", "u.out": "bottom", "a.task": "top", "a.result": "top" });
  });
  it("에이전트가 오른쪽 아래로 옮겨져도(드롭 후 위치) 다시 계산된다", () => {
    const g = graph(0);
    g.nodes![1]!.position = { x: 500, y: 0 };
    expect(sides(g)).toEqual({ "u.in": "right", "u.out": "right", "a.task": "left", "a.result": "left" });
  });
  it("드래그 중 임시 위치는 면을 바꾸지 않는다(드롭 시점에만 갱신)", () => {
    expect(sides(graph(300), new Map([["a", { x: 800, y: 0 }]]))).toEqual(sides(graph(300)));
  });
  it("auto가 지정되지 않은 그래프는 방향 기본값 그대로다", () => {
    expect(sides(graph(300, false))).toEqual({ "u.in": "left", "u.out": "right", "a.task": "left", "a.result": "right" });
  });
  it("연결이 없는 auto 포트는 방향 기본값으로 둔다", () => {
    const g = graph(300);
    g.edges = [];
    expect(sides(g)).toEqual({ "u.in": "left", "u.out": "right", "a.task": "left", "a.result": "right" });
  });
});
