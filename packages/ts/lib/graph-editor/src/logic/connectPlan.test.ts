import type { EdgeTypeDescriptor, Graph } from "@agent-console/contracts";
import { describe, expect, it } from "vitest";
import { planConnection } from "./connectPlan";

const types: EdgeTypeDescriptor[] = [
  { id: "p-flow", title: "흐름", scheduling: "flow" },
  { id: "p-back", title: "되돌림", scheduling: "flow", cycle: { max_iterations: 2 } },
  { id: "p-side", title: "옆", scheduling: "none" },
];
const g: Graph = {
  id: "g",
  name: "g",
  nodes: ["a", "b", "c"].map((id) => ({ id, type: "t" })),
  edges: [
    { id: "1", kind: "p-flow", source: { node: "a", port: "out" }, target: { node: "b", port: "in" } },
    { id: "2", kind: "p-flow", source: { node: "b", port: "out" }, target: { node: "c", port: "in" } },
  ],
};
const conn = (s: string, t: string) => ({ source: { node: s, port: "out" }, target: { node: t, port: "in" } });
const plan = (candidates: EdgeTypeDescriptor[], c = conn("c", "a"), over: { preferredKind?: string } = {}) =>
  planConnection({ graph: g, connection: c, candidates, edgeTypes: types, cycleNeededText: "순환이 됩니다", ...over });
const byId = (...ids: string[]) => types.filter((t) => ids.includes(t.id));

describe("planConnection", () => {
  it("후보가 없으면 none", () => expect(plan([]).mode).toBe("none"));
  it("순환이 아니면 기존 규칙: 후보 하나는 자동, 둘 이상은 선택(기본 종류 미리 선택)", () => {
    expect(plan(byId("p-flow"), conn("a", "c"))).toEqual({ mode: "auto", kind: "p-flow" });
    const ask = plan(byId("p-flow", "p-back"), conn("a", "c"), { preferredKind: "p-back" });
    expect(ask).toMatchObject({ mode: "ask", preselected: "p-back", info: {} });
  });
  it("순환을 닫으면 반복 종류가 기본 선택이고 반복 아닌 흐름 종류는 비활성", () => {
    const r = plan(byId("p-flow", "p-back"));
    expect(r).toMatchObject({ mode: "ask", preselected: "p-back" });
    if (r.mode !== "ask") throw new Error("ask 아님");
    expect(r.info["p-flow"]).toEqual({ disabledReason: "순환이 됩니다" });
    expect(r.info["p-back"]).toEqual({ preferred: true });
  });
  it("반복 종류가 하나만 남아도 이유를 보이려고 선택 UI를 띄운다", () => {
    expect(plan(byId("p-flow", "p-back")).mode).toBe("ask");
  });
  it("순환 검사 대상이 아닌 종류(scheduling none)는 평소대로 고를 수 있다", () => {
    const r = plan(byId("p-flow", "p-side"));
    if (r.mode !== "ask") throw new Error("ask 아님");
    expect(r.info["p-side"]).toBeUndefined();
    expect(r.preselected).toBe("p-side");
  });
  it("반복 종류 후보가 하나도 없으면 연결하지 않는다", () => {
    expect(plan(byId("p-flow"))).toEqual({ mode: "cycle-rejected" });
  });
  it("순환 종류 하나뿐이면 자동으로 만든다", () => {
    expect(plan(byId("p-back"))).toEqual({ mode: "auto", kind: "p-back" });
  });
});
