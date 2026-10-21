import { describe, expect, it } from "vitest";
import type { EdgeTypeDescriptor, Graph, Issue, NodeTypeDescriptor } from "@agent-console/contracts";
import {
  addCounterpartAndToggle, attachResource, blockingIssues, definitionKindTitles, descriptorOf, detachResource, entrySourceNodeTypes, incomingInvocations, issueTarget, issuesOfNode, overviewOf,
  pickKeys, replaceKeys, resourceEdgeKinds, resourceLinks, resourceNodeType, sharedAttachments, starterGraph, summarizeEntries, teamSettingKeys, usageCounts, withConfigText, withSharedAttachments,
} from "./teamsLogic";

// 도메인과 무관한 임의 이름의 디스크립터
const nt = (o: Partial<NodeTypeDescriptor> & { id: string }): NodeTypeDescriptor => ({ title: o.id, ...o }) as NodeTypeDescriptor;
const nodeTypes = [
  nt({ id: "t-actor", title: "행위자", role: "r-actor", executable: true, binds: { kind: "k-def", field: "ref" }, static_ports: { inputs: [{ name: "i1" }, { name: "i2" }], outputs: [{ name: "o1" }] } as never }),
  nt({ id: "t-asset", title: "자산", role: "r-asset", executable: false, binds: { kind: "k-asset", field: "asset_ref" }, static_ports: { inputs: [], outputs: [{ name: "provide" }] } as never }),
  nt({ id: "t-human", title: "사람", role: "r-human", executable: true, static_ports: { inputs: [{ name: "hears" }], outputs: [{ name: "says" }] } as never, ui_hints: { badges: [{ label: "점검", when: { config_path: "check" } }] } as never, config_schema: { type: "object", properties: { check: { anyOf: [{ type: "object" }, { type: "null" }], default: null } } } }),
  nt({ id: "t-hidden", role: "r-human", ui_hints: { hidden: true } as never }),
];
const ek = (o: Partial<EdgeTypeDescriptor> & { id: string }): EdgeTypeDescriptor => ({ title: o.id, ...o }) as EdgeTypeDescriptor;
const edgeTypes = [
  ek({ id: "e-in", scheduling: "entry", connects: { source: ["r-human"], target: ["r-actor"] } as never, default_ports: { source: "s", target: "t" } as never }),
  ek({ id: "e-out", scheduling: "exit", connects: { source: ["r-actor"], target: ["r-human"] } as never, config_schema: { type: "object", properties: { final: { type: "boolean", default: true }, label: { anyOf: [{ type: "string" }, { type: "null" }], default: null } } } }),
  ek({ id: "e-call", scheduling: "none", invocation: { strategy: "strat-x" } as never, connects: { source: ["r-actor"], target: ["r-actor"] } as never }),
  ek({ id: "e-attach", scheduling: "none", connects: { source: ["r-asset"], target: ["r-actor"] } as never, default_ports: { source: "provide", target: "i2" } as never }),
];
const graph: Graph = {
  id: "g", name: "팀", nodes: [
    { id: "h", type: "t-human", label: "나", config: { check: { x: 1 } } },
    { id: "a", type: "t-actor", label: "가", config: { ref: "d1", role: null } },
    { id: "b", type: "t-actor", label: "나나", config: { ref: "d1" } },
    { id: "r", type: "t-asset", label: "자료", config: { asset_ref: "x1" } },
  ],
  edges: [
    { id: "e1", source: { node: "h", port: "s" }, target: { node: "a", port: "t" }, kind: "e-in" },
    { id: "e2", source: { node: "a", port: "o" }, target: { node: "h", port: "h" }, kind: "e-out", config: { final: false, label: null } },
    { id: "e3", source: { node: "a", port: "o" }, target: { node: "b", port: "t" }, kind: "e-call", config: { strategy: "strat-y" } },
    { id: "e4", source: { node: "r", port: "provide" }, target: { node: "a", port: "i2" }, kind: "e-attach", config: { mode: "replace" } },
  ],
} as unknown as Graph;

describe("디스크립터 속성만으로 판단한다", () => {
  it("사용자 노드 후보 = 입구 연결의 출발 역할을 가진 숨김 아닌 타입", () => {
    expect(entrySourceNodeTypes(nodeTypes, edgeTypes).map((t) => t.id)).toEqual(["t-human"]);
    expect(entrySourceNodeTypes(nodeTypes, [])).toEqual([]);
  });

  it("새 팀 구성: 시작 노드 하나, 또는 빈 그래프", () => {
    const human = nodeTypes[2]!;
    const g = starterGraph({ id: "n1", name: "새", description: "설명", startNode: human });
    expect(g.nodes).toHaveLength(1);
    expect(g.nodes?.[0]).toMatchObject({ type: "t-human", label: "사람" });
    expect(g.edges).toEqual([]);
    expect(starterGraph({ id: "n2", name: "빈" }).nodes).toEqual([]);
    // 새 그래프의 노드 방향 기본은 auto(5.2R.23)
    expect(g.ui).toEqual({ layout: { direction: "auto" } });
  });

  it("팔레트 구역 이름은 binds 종류에 묶인 노드 타입 제목, 사용 횟수는 binds 필드 값으로", () => {
    expect(definitionKindTitles(nodeTypes)).toEqual({ "k-def": "행위자", "k-asset": "자료".replace("자료", "자산") });
    expect([...usageCounts(graph, nodeTypes)]).toEqual([["k-def:d1", 2], ["k-asset:x1", 1]]);
  });

  it("개요: 입구·답변 노드·선언형 배지 노드(마지막 답변 여부는 계획 요약에서)", () => {
    const o = overviewOf(graph, nodeTypes, edgeTypes);
    expect(o.entries.map((n) => n.id)).toEqual(["a"]);
    expect(o.exits.map((n) => n.id)).toEqual(["a"]);
    expect(o.declared.get("점검")?.map((n) => n.id)).toEqual(["h"]);
  });
});

describe("설정 키", () => {
  it("팀 설정 키는 스키마에서: 에이전트 설정과 규칙으로 나뉘고 서로 겹치지 않는다", () => {
    const keys = teamSettingKeys();
    expect(keys.agent.length).toBeGreaterThan(3);
    expect(keys.user.length).toBeGreaterThan(0);
    expect(keys.agent.filter((k) => keys.user.includes(k))).toEqual([]);
    const settings = { [keys.agent[0]!]: "x", [keys.user[0]!]: { y: 1 } } as never;
    expect(Object.keys(pickKeys(settings, keys.user))).toEqual([keys.user[0]]);
    expect(replaceKeys(settings, keys.user, {})).toEqual({ [keys.agent[0]!]: "x" });
    expect(replaceKeys(undefined, keys.user, {})).toBeUndefined();
  });

  it("팀 공용 첨부는 settings.resources에서 읽고 비우면 키를 지운다", () => {
    const g1 = withSharedAttachments(graph, [{ ref: "x" }]);
    expect(sharedAttachments(g1)).toEqual([{ ref: "x" }]);
    expect(withSharedAttachments(g1, []).settings).toBeUndefined();
  });

  it("역할·위임 조건 입력을 비우면 config 키를 지운다", () => {
    const n = withConfigText({ id: "a", type: "t", config: { ref: "d", role: "x" } }, "role", "");
    expect(n.config).toEqual({ ref: "d" });
    expect(withConfigText({ id: "a", type: "t", config: { role: "x" } }, "role", "").config).toBeUndefined();
    expect(withConfigText({ id: "a", type: "t" }, "delegate_when", "언제").config).toEqual({ delegate_when: "언제" });
  });
});

describe("위임·이슈", () => {
  it("위임받는 노드와 위임 방식(연결 설정 > 종류 기본)", () => {
    const inc = incomingInvocations("b", graph, edgeTypes);
    expect(inc.map((x) => x.edge.id)).toEqual(["e3"]);
    expect(incomingInvocations("a", graph, edgeTypes)).toEqual([]);
  });

  it("이슈 대상 이름과 노드별 이슈, 실행 차단 이슈", () => {
    const issues = [{ severity: "error", code: "c1", message: "m", edge_id: "e3", blocks_run: true }, { severity: "warning", code: "c2", message: "n", node_id: "h" }] as Issue[];
    expect(issueTarget(issues[0]!, graph).label).toBe("가 → 나나");
    expect(issueTarget(issues[1]!, graph)).toMatchObject({ kind: "node", label: "나" });
    expect(issuesOfNode(issues, "b", graph).map((i) => i.code)).toEqual(["c1"]);
    expect(blockingIssues(issues).map((i) => i.code)).toEqual(["c1"]);
    expect(descriptorOf({ id: "q", type: "없는" }, nodeTypes)).toBeUndefined();
  });
});

describe("노드 패널 리소스 연결(그래프가 진실)", () => {
  it("리소스 연결 목록은 실행되지 않는 노드에서 들어오는 연결, 방식은 연결 설정", () => {
    expect(resourceLinks("a", graph, nodeTypes, "add").map((l) => [l.resourceId, l.mode])).toEqual([["x1", "replace"]]);
    expect(resourceLinks("b", graph, nodeTypes, "add")).toEqual([]);
  });

  it("붙이기: 같은 리소스 노드가 있으면 새로 만들지 않고, 지울 때 남은 연결이 없으면 노드도 지운다", () => {
    const type = resourceNodeType(nodeTypes)!;
    const kinds = resourceEdgeKinds(graph.nodes![2]!, type, nodeTypes, edgeTypes);
    expect(kinds.map((k) => k.id)).toEqual(["e-attach"]);
    const r1 = attachResource(graph, graph.nodes![2]!, { id: "x1", name: "자료" }, type, kinds[0]!, nodeTypes, { node: "nn", edge: "ee" })!;
    expect(r1.createdNode).toBe(false);
    expect(r1.graph.nodes).toHaveLength(4);
    const r2 = attachResource(graph, graph.nodes![2]!, { id: "x2", name: "새 자료" }, type, kinds[0]!, nodeTypes, { node: "nn", edge: "ee" })!;
    expect(r2.createdNode).toBe(true);
    expect(r2.graph.edges?.at(-1)).toMatchObject({ kind: "e-attach", source: { node: "nn", port: "provide" }, target: { node: "b", port: "i2" } });
    const removed = detachResource(r2.graph, "ee");
    expect(removed.nodes?.some((n) => n.id === "nn")).toBe(false);
    expect(detachResource(graph, "e4").nodes?.some((n) => n.id === "r")).toBe(false);
  });
});

describe("목록 표시", () => {
  it("입구 요약", () => {
    const more = (f: string, n: number) => `${f} 외 ${n}`;
    expect(summarizeEntries(undefined, more)).toBeUndefined();
    expect(summarizeEntries([], more)).toBeUndefined();
    expect(summarizeEntries(["가"], more)).toBe("가");
    expect(summarizeEntries(["가", "나", "다"], more)).toBe("가 외 2");
  });
});

describe("상대 노드가 없으면 만들어서 켠다", () => {
  const lonely: Graph = { id: "g2", name: "혼자", nodes: [{ id: "a", type: "t-actor", label: "가", config: { ref: "d1" }, position: { x: 500, y: 40 } }], edges: [] } as unknown as Graph;
  it("입구: 상대 역할의 기본 노드 타입을 왼쪽에 놓고 연결한다(타입 id는 속성으로만 찾는다)", () => {
    const res = addCounterpartAndToggle(lonely, "a", "entry", "e-in", { nodeTypes, edgeTypes })!;
    expect(res.graph.nodes).toHaveLength(2);
    expect(res.graph.nodes![1]).toMatchObject({ type: "t-human", position: { x: 200, y: 40 } });
    expect(res.graph.edges).toHaveLength(1);
    expect(res.graph.edges![0]).toMatchObject({ kind: "e-in", source: { node: res.nodeId, port: "s" }, target: { node: "a", port: "t" } });
  });
  it("답변은 오른쪽, 상대 타입이 없으면 만들지 않는다", () => {
    expect(addCounterpartAndToggle(lonely, "a", "exit", "e-out", { nodeTypes, edgeTypes })!.graph.nodes![1]!.position?.x).toBe(800);
    expect(addCounterpartAndToggle(lonely, "a", "entry", "e-in", { nodeTypes: nodeTypes.filter((t) => t.id !== "t-human"), edgeTypes })).toBeUndefined();
  });
});
