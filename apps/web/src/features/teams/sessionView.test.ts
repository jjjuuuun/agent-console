import { describe, expect, it } from "vitest";
import type { DelegationStrategyDescriptor, EdgeTypeDescriptor, Graph, NodeTypeDescriptor } from "@agent-console/contracts";
import { edgeLeadChips, edgeSessionMap, incomingSessions, nodeFootAnnotations, nodeSessionMode, sessionSummary } from "./sessionView";

/** 임의 id·임의 값. 화면은 디스크립터 속성만 본다. */
const nodeTypes = [
  { id: "n-a", title: "가", role: "ra" },
  { id: "n-u", title: "사용자형", role: "ru", opens_session: false },
] as unknown as NodeTypeDescriptor[];
const edgeTypes = [
  { id: "k-deleg", title: "맡김", scheduling: "none", invocation: { strategy: "m-1" } },
  { id: "k-flow", title: "순서", scheduling: "flow", session: "separate" },
  { id: "k-plain", title: "속성 없음", scheduling: "flow" },
] as unknown as EdgeTypeDescriptor[];
const strategies = [
  { id: "m-1", title: "방식1", session: "same", member_fields: [], max_depth: 1 },
  { id: "m-2", title: "방식2", session: "separate", member_fields: [], max_depth: null },
  { id: "m-3", title: "방식3", session: "zz9", member_fields: [], max_depth: null },
] as unknown as DelegationStrategyDescriptor[];
const g = (edges: Graph["edges"]): Graph => ({
  id: "g", name: "g",
  nodes: [
    { id: "l", type: "n-a", label: "리더" },
    { id: "w1", type: "n-a", label: "일꾼1" },
    { id: "w2", type: "n-a", label: "일꾼2" },
    { id: "u", type: "n-u", label: "사람" },
  ],
  edges,
}) as unknown as Graph;
const e = (id: string, kind: string, s: string, t: string, config?: Record<string, unknown>) => ({ id, kind, source: { node: s, port: "o" }, target: { node: t, port: "i" }, ...(config ? { config } : {}) });

describe("팀 편집기 세션 계산", () => {
  it("연결 세션 값: 위임은 유효 방식, 흐름은 종류 값, 속성 없는 종류는 없음", () => {
    const graph = g([e("a", "k-deleg", "l", "w1"), e("b", "k-deleg", "l", "w2", { strategy: "m-2" }), e("c", "k-flow", "w1", "w2"), e("d", "k-plain", "w1", "w2")] as never);
    expect(edgeSessionMap(graph, edgeTypes, strategies)).toEqual({ a: "same", b: "separate", c: "separate" });
  });
  it("균일 축약: 모든 값이 같으면 아이콘만, 다른 값이 생기면 글자", () => {
    const uniform = edgeLeadChips(g([e("a", "k-flow", "l", "w1"), e("b", "k-flow", "w1", "w2")] as never), edgeTypes, strategies);
    expect(Object.values(uniform).every((c) => c.iconOnly === true)).toBe(true);
    const mixed = edgeLeadChips(g([e("a", "k-flow", "l", "w1"), e("b", "k-deleg", "l", "w2")] as never), edgeTypes, strategies);
    expect(Object.values(mixed).every((c) => c.iconOnly !== true)).toBe(true);
    expect(mixed["b"]!.fullTitle).toContain("리더 세션 안에서 실행됩니다");
  });
  it("노드 카드 칩: 같은 세션 대상만, 위임자 둘이면 외 1곳, 섞이면 세션 N곳, 별도뿐이면 없음", () => {
    const one = nodeFootAnnotations(g([e("a", "k-deleg", "l", "w1")] as never), edgeTypes, strategies);
    expect(one["w1"]!.foot.title).toBe("리더 세션 안");
    expect(one["l"]).toBeUndefined();
    const two = nodeFootAnnotations(g([e("a", "k-deleg", "l", "w2"), e("b", "k-deleg", "w1", "w2")] as never), edgeTypes, strategies);
    expect(two["w2"]!.foot.title).toBe("리더 외 1곳 세션 안");
    const mixed = nodeFootAnnotations(g([e("a", "k-deleg", "l", "w2"), e("b", "k-deleg", "w1", "w2", { strategy: "m-2" })] as never), edgeTypes, strategies);
    expect(mixed["w2"]!.foot.title).toBe("세션 2곳");
    const separate = nodeFootAnnotations(g([e("a", "k-deleg", "l", "w1", { strategy: "m-2" })] as never), edgeTypes, strategies);
    expect(separate).toEqual({});
    expect(nodeSessionMode(incomingSessions("w1", g([e("a", "k-deleg", "l", "w1", { strategy: "m-3" })] as never), edgeTypes, strategies)).mode).toBe("none");
  });
  it("팀 요약: opens_session false 제외, 세션 속성이 하나도 없으면 숨김", () => {
    const graph = g([e("a", "k-deleg", "l", "w1"), e("b", "k-deleg", "l", "w2", { strategy: "m-2" }), e("c", "k-flow", "w2", "u")] as never);
    // 닿은 노드: l, w1, w2, u(제외). w1 = 같은 세션 안(M=1), l·w2 = 나머지(N=2)
    expect(sessionSummary(graph, nodeTypes, edgeTypes, strategies)).toEqual({ separate: 2, same: 1 });
    expect(sessionSummary(g([e("d", "k-plain", "w1", "w2")] as never), nodeTypes, edgeTypes, strategies)).toBeUndefined();
    // 방식 목록을 못 읽으면 위임 연결의 세션 값이 없고, 흐름 연결(종류 값)만 센다(w2만 대상, 사람 노드는 제외)
    expect(sessionSummary(graph, nodeTypes, edgeTypes, [])).toEqual({ separate: 1, same: 0 });
  });
});
