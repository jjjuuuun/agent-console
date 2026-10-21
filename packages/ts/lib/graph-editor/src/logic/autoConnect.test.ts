import { describe, expect, it } from "vitest";
import type { Graph } from "@agent-console/contracts";
import { teamEdgeTypes as E, teamNodeTypes as N } from "../testing";
import { planAutoConnect, rankEdgeKinds, withoutEdges } from "./autoConnect";

const base = (nodes: Graph["nodes"], edges: Graph["edges"] = []): Graph => ({ id: "g", name: "g", nodes, edges });
const human = { id: "h1", type: "beta-human", label: "사용자", config: {}, position: { x: 0, y: 0 } };
const actor = (id: string) => ({ id, type: "alpha-actor", label: id, config: {}, position: { x: 300, y: 0 } });
const run = (g: Graph, nodeId: string, extra: Partial<Parameters<typeof planAutoConnect>[0]> = {}) => planAutoConnect({ graph: g, nodeId, nodeTypes: N, edgeTypes: E, ...extra });

describe("planAutoConnect", () => {
  it("사용자 노드 하나 + 첫 에이전트: 입구·답변을 default_ports로 만든다", () => {
    const plan = run(base([human, actor("a1")]), "a1")!;
    expect(plan.addedEdgeIds).toHaveLength(2);
    const [entry, exit] = plan.graph.edges!;
    expect(entry).toMatchObject({ kind: "e-start", source: { node: "h1", port: "says" }, target: { node: "a1", port: "in" } });
    expect(exit).toMatchObject({ kind: "e-end", source: { node: "a1", port: "out" }, target: { node: "h1", port: "hears" } });
  });
  it("입구·답변이 이미 있으면 하지 않는다(두 번째 에이전트)", () => {
    const first = run(base([human, actor("a1")]), "a1")!;
    expect(run({ ...first.graph, nodes: [...first.graph.nodes!, actor("a2")] }, "a2")).toBeNull();
  });
  it("사용자 노드가 없거나 둘이면 하지 않는다", () => {
    expect(run(base([actor("a1")]), "a1")).toBeNull();
    expect(run(base([human, { ...human, id: "h2" }, actor("a1")]), "a1")).toBeNull();
  });
  it("이미 에이전트가 있는 연결 없는 그래프에 또 놓으면 하지 않는다", () => {
    expect(run(base([human, actor("a1"), actor("a2")]), "a2")).toBeNull();
  });
  it("실행 불가 노드(리소스)·사용자 노드 자신은 대상이 아니다", () => {
    const note = { id: "m1", type: "gamma-note", label: "메모", config: {}, position: { x: 0, y: 0 } };
    expect(run(base([human, note]), "m1")).toBeNull();
    expect(run(base([human, actor("a1")]), "h1")).toBeNull();
  });
  it("포트를 정할 수 없으면 null이고 입력은 바뀌지 않는다", () => {
    const noPorts = E.map((k) => ({ ...k, default_ports: null }));
    const g = base([{ ...human, type: "delta-secret" }, actor("a1")]);
    const before = JSON.stringify(g);
    expect(run(g, "a1", { edgeTypes: noPorts })).toBeNull();
    expect(JSON.stringify(g)).toBe(before);
  });
  it("종류가 여럿이면 두 역할을 명시한 종류를 고른다", () => {
    const loose = { id: "e-loose", version: 1, title: "느슨", scheduling: "entry" as const, connects: { source: ["human"] }, default_ports: { source: "says", target: "in" } };
    const plan = run(base([human, actor("a1")]), "a1", { edgeTypes: [loose, ...E] })!;
    expect(plan.graph.edges![0]!.kind).toBe("e-start");
  });
  it("withoutEdges는 지정한 연결만 지운다", () => {
    const plan = run(base([human, actor("a1")], [{ id: "keep", kind: "e-pass", source: { node: "h1", port: "x" }, target: { node: "a1", port: "in" } }]), "a1")!;
    expect(withoutEdges(plan.graph, plan.addedEdgeIds).edges!.map((e) => e.id)).toEqual(["keep"]);
  });
});

describe("rankEdgeKinds: 관련도 순", () => {
  const a = { id: "a", title: "a", connects: { source: ["human"] } };
  const b = { id: "b", title: "b", connects: { source: ["human"], target: ["doer"] } };
  const c = { id: "c", title: "c" };
  it("두 역할 명시 -> 선호 -> 목록 순서", () => {
    const ends = { sourceRole: "human", targetRole: "doer" };
    expect(rankEdgeKinds([a, c, b], ends).map((k) => k.id)).toEqual(["b", "a", "c"]);
    expect(rankEdgeKinds([a, c], ends, "c").map((k) => k.id)).toEqual(["c", "a"]);
    expect(rankEdgeKinds([a, b], ends, "a").map((k) => k.id)).toEqual(["b", "a"]);
  });
});
