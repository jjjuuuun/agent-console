import type { EdgeTypeDescriptor, Graph } from "@agent-console/contracts";
import { describe, expect, it } from "vitest";
import { inferKindPorts, resolveEnds } from "./inferPorts";
import type { PortLookup } from "./ops";

// 포트 이름·종류 id는 모두 이 테스트가 만든 데이터다(구현은 이름을 비교하지 않는다).
const kinds: EdgeTypeDescriptor[] = [
  { id: "k-main", title: "주", scheduling: "flow", default_ports: { source: "done", target: "recv" } },
  { id: "k-plain", title: "기본 포트 없음", scheduling: "none" },
  { id: "k-ghost", title: "없는 포트를 기본으로", scheduling: "none", default_ports: { source: "nope", target: "nope" } },
];
const ports: Record<string, { inputs: string[]; outputs: string[] }> = {
  a: { inputs: ["in1", "recv"], outputs: ["first", "done"] },
  b: { inputs: ["in1", "recv"], outputs: ["first", "done"] },
};
const portsOf: PortLookup = (id) => ports[id];
const g = (edges: Graph["edges"] = []): Graph => ({ id: "g", name: "g", nodes: [{ id: "a", type: "t" }, { id: "b", type: "t" }], edges });

describe("resolveEnds", () => {
  it("핸들 방향이 없으면 시작 쪽이 출발", () => {
    expect(resolveEnds({ node: "a" }, { node: "b" })).toEqual({ source: { node: "a" }, target: { node: "b" } });
  });
  it("입력 핸들에서 시작하면 시작 노드가 도착이고 그 포트는 고정", () => {
    expect(resolveEnds({ node: "a", port: { side: "in", port: "recv" } }, { node: "b" })).toEqual({ source: { node: "b" }, target: { node: "a", port: "recv" } });
  });
  it("띠에서 시작해 출력 핸들에 놓으면 놓은 쪽이 출발", () => {
    expect(resolveEnds({ node: "a" }, { node: "b", port: { side: "out", port: "first" } })).toEqual({ source: { node: "b", port: "first" }, target: { node: "a" } });
  });
  it("같은 방향 핸들끼리는 연결할 수 없다", () => {
    expect(resolveEnds({ node: "a", port: { side: "out", port: "x" } }, { node: "b", port: { side: "out", port: "y" } })).toBeUndefined();
  });
});

describe("inferKindPorts", () => {
  const ends = { source: { node: "a" }, target: { node: "b" } };
  it("default_ports가 있으면 그 포트, 없으면 목록의 첫 포트", () => {
    const r = inferKindPorts(g(), ends, kinds.slice(0, 2), kinds, portsOf);
    expect(r.items).toEqual([
      { kind: "k-main", connection: { source: { node: "a", port: "done" }, target: { node: "b", port: "recv" } } },
      { kind: "k-plain", connection: { source: { node: "a", port: "first" }, target: { node: "b", port: "in1" } } },
    ]);
  });
  it("default_ports가 노드에 없는 포트면 첫 포트로 넘어간다", () => {
    const r = inferKindPorts(g(), ends, [kinds[2] as EdgeTypeDescriptor], kinds, portsOf);
    expect(r.items[0]?.connection).toEqual({ source: { node: "a", port: "first" }, target: { node: "b", port: "in1" } });
  });
  it("핸들이 정한 포트는 고정하고 나머지만 추론한다", () => {
    const r = inferKindPorts(g(), { source: { node: "a", port: "first" }, target: { node: "b" } }, [kinds[0] as EdgeTypeDescriptor], kinds, portsOf);
    expect(r.items[0]?.connection).toEqual({ source: { node: "a", port: "first" }, target: { node: "b", port: "recv" } });
  });
  it("고정한 포트가 노드에 없으면 그 종류는 빠진다", () => {
    const r = inferKindPorts(g(), { source: { node: "a", port: "ghost" }, target: { node: "b" } }, kinds, kinds, portsOf);
    expect(r.items).toEqual([]);
  });
  it("기본 포트 쌍이 이미 있으면 다음 호환 포트로 간다", () => {
    const dup: Graph["edges"] = [{ id: "e", kind: "k-main", source: { node: "a", port: "done" }, target: { node: "b", port: "recv" } }];
    const r = inferKindPorts(g(dup), ends, [kinds[0] as EdgeTypeDescriptor], kinds, portsOf);
    expect(r.items[0]?.connection).toEqual({ source: { node: "a", port: "done" }, target: { node: "b", port: "in1" } });
  });
  it("모든 쌍이 중복이면 빈 목록과 기존 연결 id", () => {
    const all: Graph["edges"] = [];
    for (const o of ports["a"]!.outputs) for (const i of ports["b"]!.inputs) all.push({ id: `${o}-${i}`, kind: "k-main", source: { node: "a", port: o }, target: { node: "b", port: i } });
    const r = inferKindPorts(g(all), ends, [kinds[0] as EdgeTypeDescriptor], kinds, portsOf);
    expect(r.items).toEqual([]);
    expect(r.duplicateEdgeId).toBeDefined();
  });
  it("포트 목록을 모르는 노드는 default_ports만 쓴다", () => {
    const r = inferKindPorts(g(), ends, kinds.slice(0, 2), kinds, () => undefined);
    expect(r.items.map((i) => i.kind)).toEqual(["k-main"]);
  });
});
