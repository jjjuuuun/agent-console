import type { EdgeSpec, EdgeTypeDescriptor, Graph } from "@agent-console/contracts";
import { describe, expect, it } from "vitest";
import { checkConnection } from "./ops";
import { closesFlowLoop, loopRegion } from "./loops";

/** 임의 이름의 종류만 쓴다. flow = 일반 흐름, back = `cycle` 속성이 있는 흐름, side = scheduling 없음. */
const types: EdgeTypeDescriptor[] = [
  { id: "k-flow", title: "흐름", scheduling: "flow" },
  { id: "k-back", title: "되돌림", scheduling: "flow", cycle: { max_iterations: 3 } },
  { id: "k-none", title: "위임", scheduling: "none" },
  { id: "k-entry", title: "입구", scheduling: "entry" },
  { id: "k-exit", title: "답변", scheduling: "exit" },
];
const node = (id: string) => ({ id, type: "t", position: { x: 0, y: 0 } });
const edge = (id: string, kind: string, s: string, t: string): EdgeSpec => ({ id, kind, source: { node: s, port: "out" }, target: { node: t, port: "in" } });
const graph = (ids: string[], edges: EdgeSpec[]): Graph => ({ id: "g", name: "g", nodes: ids.map(node), edges });

describe("loopRegion", () => {
  it("직선 흐름의 되돌림: 도착에서 출발까지 경로 위 노드(그래프 노드 순서)", () => {
    const g = graph(["a", "b", "c", "d"], [edge("e1", "k-flow", "a", "b"), edge("e2", "k-flow", "b", "c"), edge("e3", "k-flow", "c", "d"), edge("r", "k-back", "c", "b")]);
    expect(loopRegion(g, types, "r")).toEqual(["b", "c"]);
  });
  it("다중 경로: 갈래 둘 다 영역에 든다, 경로 밖 가지는 빠진다", () => {
    const g = graph(["s", "x", "y", "z", "o"], [edge("1", "k-flow", "s", "x"), edge("2", "k-flow", "s", "y"), edge("3", "k-flow", "x", "z"), edge("4", "k-flow", "y", "z"), edge("5", "k-flow", "x", "o"), edge("r", "k-back", "z", "s")]);
    expect(loopRegion(g, types, "r")).toEqual(["s", "x", "y", "z"]);
  });
  it("자기 자신으로의 반복은 그 노드 하나", () => {
    const g = graph(["a", "b"], [edge("1", "k-flow", "a", "b"), edge("r", "k-back", "b", "b")]);
    expect(loopRegion(g, types, "r")).toEqual(["b"]);
  });
  it("선택한 연결뿐 아니라 모든 사이클 연결을 경로에서 뺀다(중첩 반복의 안쪽은 바깥의 부분집합)", () => {
    const g = graph(["a", "b", "c", "d"], [edge("1", "k-flow", "a", "b"), edge("2", "k-flow", "b", "c"), edge("3", "k-flow", "c", "d"), edge("inner", "k-back", "c", "b"), edge("outer", "k-back", "d", "a")]);
    expect(loopRegion(g, types, "inner")).toEqual(["b", "c"]);
    expect(loopRegion(g, types, "outer")).toEqual(["a", "b", "c", "d"]);
  });
  it("닫는 경로가 없거나 사이클 연결이 아니거나 없는 연결이면 빈 배열", () => {
    const g = graph(["a", "b"], [edge("fwd", "k-back", "a", "b"), edge("1", "k-flow", "a", "b")]);
    expect(loopRegion(g, types, "fwd")).toEqual([]);
    expect(loopRegion(g, types, "1")).toEqual([]);
    expect(loopRegion(g, types, "nope")).toEqual([]);
  });
  it("흐름이 아닌 종류(scheduling none)는 경로를 잇지 않는다, 모르는 종류는 흐름으로 본다", () => {
    const g = graph(["a", "b", "c"], [edge("1", "k-none", "a", "b"), edge("2", "k-flow", "b", "c"), edge("r", "k-back", "c", "a")]);
    expect(loopRegion(g, types, "r")).toEqual([]);
    const g2 = graph(["a", "b", "c"], [edge("1", "ghost", "a", "b"), edge("2", "k-flow", "b", "c"), edge("r", "k-back", "c", "a")]);
    expect(loopRegion(g2, types, "r")).toEqual(["a", "b", "c"]);
  });
  it("종류 id를 바꿔도(x1·y2) 같은 결과, 입력 그래프는 바뀌지 않는다", () => {
    const renamed = types.map((t) => ({ ...t, id: t.id.replace("k-", "z9-") }));
    const g = graph(["a", "b", "c"], [edge("1", "z9-flow", "a", "b"), edge("2", "z9-flow", "b", "c"), edge("r", "z9-back", "c", "a")]);
    const before = JSON.stringify(g);
    expect(loopRegion(g, renamed, "r")).toEqual(["a", "b", "c"]);
    expect(JSON.stringify(g)).toBe(before);
  });
});

describe("closesFlowLoop", () => {
  const g = graph(["a", "b", "c"], [edge("1", "k-flow", "a", "b"), edge("2", "k-flow", "b", "c")]);
  const neu = (kind: string, s: string, t: string) => ({ kind, source: { node: s }, target: { node: t } });
  it("flow 종류가 도착에서 출발로 가는 경로를 닫으면 참", () => {
    expect(closesFlowLoop(g, neu("k-flow", "c", "a"), types)).toBe(true);
    expect(closesFlowLoop(g, neu("k-back", "c", "a"), types)).toBe(true); // 사이클 종류도 닫는 것 자체는 참(허용 여부는 호출자)
  });
  it("앞으로 가는 연결·무관한 노드는 거짓", () => {
    expect(closesFlowLoop(g, neu("k-flow", "a", "c"), types)).toBe(false);
    expect(closesFlowLoop(graph(["a", "b", "z"], []), neu("k-flow", "z", "a"), types)).toBe(false);
  });
  it("none/entry/exit 종류는 순환 검사 대상이 아니다", () => {
    for (const k of ["k-none", "k-entry", "k-exit"]) expect(closesFlowLoop(g, neu(k, "c", "a"), types)).toBe(false);
  });
  it("기존 사이클 연결은 경로로 세지 않는다", () => {
    const withBack = graph(["a", "b", "c"], [edge("1", "k-flow", "a", "b"), edge("2", "k-flow", "b", "c"), edge("r", "k-back", "c", "a")]);
    expect(closesFlowLoop(withBack, neu("k-flow", "a", "c"), types)).toBe(false);
  });
});

describe("checkConnection + 사이클 종류", () => {
  const g = graph(["a", "b"], [edge("1", "k-flow", "a", "b")]);
  const c = { source: { node: "b", port: "out" }, target: { node: "a", port: "in" } };
  it("흐름 종류는 순환을 거부하고 사이클 종류·비흐름 종류는 허용한다", () => {
    expect(checkConnection(g, c, undefined, { edgeTypes: types, kind: "k-flow" })).toEqual({ ok: false, reason: "cycle" });
    expect(checkConnection(g, c, undefined, { edgeTypes: types, kind: "k-back" })).toEqual({ ok: true });
    expect(checkConnection(g, c, undefined, { edgeTypes: types, kind: "k-none" })).toEqual({ ok: true });
  });
});
