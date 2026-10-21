/** 테스트 전용 픽스처(공개 API 아님). 노드 타입 이름은 임의 문자열이며 코드의 어떤 분기에도 쓰이지 않는다. */
import type { EdgeTypeDescriptor, Graph, NodeTypeDescriptor } from "@agent-console/contracts";

export const descriptors: NodeTypeDescriptor[] = [
  {
    id: "zeta-source",
    version: 1,
    title: "원천 노드",
    description: "값을 내보낸다",
    category: "흐름-가",
    config_schema: { type: "object", properties: { greeting: { type: "string", default: "안녕" } } },
    static_ports: { inputs: [], outputs: [{ name: "out", label: "출력" }] },
    ui_hints: { icon: "Z", color: "#3b82f6" },
  },
  {
    id: "omega-splitter",
    version: 2,
    title: "갈래 나누기",
    description: "config에 따라 출력 포트가 바뀐다",
    category: "분기",
    config_schema: { type: "object" },
    dynamic_ports: true,
    ui_hints: { icon: "way-too-long-icon", color: "url(javascript:alert(1))" },
  },
  {
    id: "kappa-sink",
    version: 1,
    title: "Sink with a very long title that should be truncated safely and not overflow the box",
    category: "",
    static_ports: { inputs: [{ name: "in", label: "입력", schema: { type: "string" } }, { name: "extra" }], outputs: [] },
  },
];

export const edgeTypes: EdgeTypeDescriptor[] = [
  { id: "flow-a", title: "흐름 A", ui_hints: { color: "#22aa88", dashed: true } },
  { id: "flow-b", title: "흐름 B" },
];

export function sampleGraph(): Graph {
  return {
    id: "g1",
    name: "샘플",
    custom_field: { keep: "me" },
    groups: [{ id: "grp" }],
    ui: { viewport: { x: 0, y: 0, zoom: 1 } },
    nodes: [
      { id: "n1", type: "zeta-source", label: "시작", config: {}, position: { x: 0, y: 0 }, extra_node_field: 1 },
      { id: "n2", type: "omega-splitter", label: "분기", config: { branches: ["a", "b"] }, position: { x: 300, y: 0 } },
      { id: "n3", type: "kappa-sink", label: "끝", config: {}, position: { x: 600, y: 0 } },
      { id: "n4", type: "ghost-type-not-registered", label: "유령", config: {}, position: { x: 0, y: 200 } },
    ],
    edges: [
      { id: "e1", kind: "flow-a", source: { node: "n1", port: "out" }, target: { node: "n2", port: "in" } },
      { id: "e2", kind: "flow-b", source: { node: "n2", port: "a" }, target: { node: "n3", port: "in" } },
      { id: "e3", kind: "flow-b", source: { node: "n4", port: "ghost-out" }, target: { node: "n3", port: "extra" } },
    ],
  };
}

/**
 * 팀 구성 모드 테스트용 임의 디스크립터. 이름·역할 문자열은 코드의 어떤 분기에도 쓰이지 않는다.
 * (역할 doer = 실행되는 정의 노드, human = 사용자 쪽 노드, note = 실행되지 않는 첨부 노드)
 */
export const teamNodeTypes: NodeTypeDescriptor[] = [
  {
    id: "alpha-actor",
    version: 1,
    title: "행위자",
    description: "정의에서 만든다",
    category: "일꾼",
    role: "doer",
    binds: { kind: "things", field: "thing_ref" },
    config_schema: { type: "object", properties: { mood: { type: "string", default: "calm" } } },
    static_ports: { inputs: [{ name: "in", label: "받기" }], outputs: [{ name: "out", label: "내기" }] },
    ui_hints: { icon: "A", color: "#10b981" },
  },
  {
    id: "beta-human",
    version: 1,
    title: "사람 자리",
    description: "정의 없이 바로 놓는 기본 노드",
    category: "사람",
    role: "human",
    dynamic_ports: true,
  },
  {
    id: "gamma-note",
    version: 1,
    title: "메모",
    role: "note",
    executable: false,
    binds: { kind: "docs", field: "doc_id" },
    static_ports: { inputs: [], outputs: [{ name: "o", label: "붙이기" }] },
    ui_hints: { icon: "M" },
  },
  { id: "delta-secret", version: 1, title: "숨김 타입", role: "doer", ui_hints: { hidden: true } },
];

export const teamEdgeTypes: EdgeTypeDescriptor[] = [
  { id: "e-start", version: 1, title: "시작선", scheduling: "entry", connects: { source: ["human"], target: ["doer"] }, default_ports: { source: "says", target: "in" } },
  { id: "e-end", version: 1, title: "끝선", scheduling: "exit", connects: { source: ["doer"], target: ["human"] }, default_ports: { source: "out", target: "hears" }, config_schema: { type: "object", properties: { tag: { type: "string", default: "t" } } } },
  { id: "e-ask", version: 1, title: "묻는선", scheduling: "none", interaction: { kinds: ["q"] }, connects: { source: ["doer"], target: ["human"] }, default_ports: { source: "out", target: "asks" }, ui_hints: { dashed: true } },
  { id: "e-pass", version: 1, title: "넘김선", scheduling: "flow", connects: { source: ["doer", "human"], target: ["doer", "human"] } },
  { id: "e-attach", version: 1, title: "붙임선", scheduling: "none", connects: { source: ["note"], target: ["doer"] } },
];

/** 사람 자리(h1)와 행위자 둘(a1, a2), 메모(m1)가 있는 그래프. 연결은 없다. */
export function teamGraph(): Graph {
  return {
    id: "tg",
    name: "팀",
    nodes: [
      { id: "h1", type: "beta-human", label: "사용자", config: {}, position: { x: 0, y: 0 } },
      { id: "a1", type: "alpha-actor", label: "일꾼 하나", config: { thing_ref: "t1" }, position: { x: 300, y: 0 } },
      { id: "a2", type: "alpha-actor", label: "일꾼 둘", config: { thing_ref: "t2" }, position: { x: 600, y: 0 } },
      { id: "m1", type: "gamma-note", label: "지침", config: { doc_id: "d1" }, position: { x: 300, y: 200 } },
    ],
    edges: [{ id: "x1", kind: "e-attach", source: { node: "m1", port: "o" }, target: { node: "a1", port: "in" } }],
  };
}
