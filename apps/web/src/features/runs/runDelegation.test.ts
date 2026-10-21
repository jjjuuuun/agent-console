import { describe, expect, it, vi } from "vitest";
import type { EdgeSpec, EdgeTypeDescriptor, NodeRun, NodeSpec, NodeTypeDescriptor, Run } from "@agent-console/contracts";
import { buildEdgeBadges, childForNodeRun, childNodeText, exhaustedLines, nestedRunSummaries } from "./runDelegation";

const edge = (id: string, kind: string): EdgeSpec => ({ id, kind, source: { node: "a", port: "o" }, target: { node: "b", port: "i" } });
const kinds = [{ id: "k-loop", title: "반복", cycle: { max_iterations: 3 } }, { id: "k-flow", title: "순서" }] as EdgeTypeDescriptor[];
const run = (id: string, extra: Partial<Run> = {}): Run => ({ id, graph_id: "g2", graph_version: "v", status: "running", input: {}, origin: "chat", created_at: 1, ...extra });

describe("연결 배지", () => {
  const graph = { edges: [edge("e1", "k-loop"), edge("e2", "k-flow")] };
  it("반복 연결 통과 횟수 ↻×k, 일반 연결에는 붙이지 않는다", () => {
    const out = buildEdgeBadges(graph, kinds, { edgeTraversals: { e1: 2, e2: 5 }, exhausted: {}, conditionSkipped: {} });
    expect(out["e1"]).toEqual([{ text: "↻×2", ariaLabel: "반복 연결 2번 지나감", tone: "neutral" }]);
    expect(out["e2"]).toBeUndefined();
  });
  it("한도 도달은 경고 배지와 한도를 보이고, 한도를 모르면 한도 숫자 없이", () => {
    const out = buildEdgeBadges(graph, kinds, { edgeTraversals: { e1: 3 }, exhausted: { e1: 3 }, conditionSkipped: {} });
    expect(out["e1"]?.[0]).toMatchObject({ text: "↻×3 한도 3회 도달", tone: "warning" });
    const unknown = buildEdgeBadges(graph, kinds, { edgeTraversals: { e1: 1 }, exhausted: { e1: undefined }, conditionSkipped: {} });
    expect(unknown["e1"]?.[0]?.text).toBe("↻×1 ▲");
  });
  it("조건이 맞지 않아 건너뛴 연결은 ✕", () => {
    const out = buildEdgeBadges(graph, kinds, { edgeTraversals: {}, exhausted: {}, conditionSkipped: { e2: true } });
    expect(out["e2"]?.[0]).toMatchObject({ text: "✕", ariaLabel: "조건이 맞지 않아 지나가지 않음" });
  });
  it("한도 도달 줄은 출발 노드에", () => {
    expect(exhaustedLines(graph, { exhausted: { e1: 3 } })).toEqual({ a: "반복 한도에 도달했습니다 (한도 3회)" });
    expect(exhaustedLines(graph, { exhausted: {} })).toEqual({});
  });
});

describe("노드의 보이는 실행에 속한 자식 실행", () => {
  const runs = (n: number): NodeRun[] => Array.from({ length: n }, (_, i) => ({ run_id: "r", node_id: "t", status: "succeeded", iteration: i }) as NodeRun);
  const kid = (id: string, at: number) => run(id, { parent_node_id: "t", created_at: at });
  it("NodeRun 수와 자식 수가 같으면 순서대로 짝짓는다", () => {
    const kids = [kid("c2", 2), kid("c1", 1)];
    expect(childForNodeRun("t", runs(2), 0, kids).child?.id).toBe("c1");
    expect(childForNodeRun("t", runs(2), 1, kids).child?.id).toBe("c2");
  });
  it("하나뿐이면 그 자식, 수가 다르면 모호", () => {
    expect(childForNodeRun("t", runs(1), 0, [kid("c1", 1)])).toMatchObject({ ambiguous: false });
    expect(childForNodeRun("t", runs(3), 0, [kid("c1", 1), kid("c2", 2)])).toMatchObject({ ambiguous: true, child: undefined });
    expect(childForNodeRun("t", runs(1), 0, [])).toMatchObject({ ambiguous: false, all: [] });
  });
  it("부모 노드 문구는 같은 노드에서 여럿일 때 N회차를 붙인다", () => {
    const kids = [kid("c1", 1), kid("c2", 2)];
    expect(childNodeText(kids, kids[1]!, () => "검토")).toBe("검토 · 2회차");
    expect(childNodeText([kids[0]!], kids[0]!, () => "검토")).toBe("검토");
  });
  it("중첩 노드 카드: binds.kind가 현재 정의 종류와 같을 때만 자식 실행 줄과 열기", () => {
    const nodes = [{ id: "t", type: "t-n", label: "검토", config: { ref: "g2" } }, { id: "x", type: "t-other" }] as NodeSpec[];
    const types = [{ id: "t-n", title: "N", binds: { kind: "kind-q", field: "ref" } }, { id: "t-other", title: "O", binds: { kind: "kind-z", field: "ref" } }] as NodeTypeDescriptor[];
    const open = vi.fn();
    const out = nestedRunSummaries({
      nodes,
      nodeTypes: types,
      currentKind: "kind-q",
      children: [kid("c1abcdef", 1)],
      nodeRunsOf: () => runs(1),
      visibleIndexOf: () => 0,
      teamName: () => "자식 팀",
      statusLabel: (s) => `상태:${s}`,
      shortId: (id) => id.slice(0, 4),
      onOpen: open,
    });
    expect(Object.keys(out)).toEqual(["t"]);
    expect(out["t"]).toMatchObject({ title: "자식 팀", subtitle: "자식 실행 c1ab · 상태:running" });
    out["t"]!.open?.onOpen();
    expect(open).toHaveBeenCalledWith("c1abcdef");
  });
});
