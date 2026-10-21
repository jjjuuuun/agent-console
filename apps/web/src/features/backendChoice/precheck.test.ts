import { describe, expect, it } from "vitest";
import type { Agent, BackendDescriptor, Graph, NodeTypeDescriptor } from "@agent-console/contracts";
import { precheckBackends } from "./precheck";

const nodeTypes = [
  { id: "t-actor", version: 1, title: "행위자", executable: true, binds: { kind: "agent", field: "ref" } },
  { id: "t-asset", version: 1, title: "자산", executable: false, binds: { kind: "resource", field: "ref" } },
  { id: "t-human", version: 1, title: "사람", executable: true },
] as unknown as NodeTypeDescriptor[];
const options = [{ id: "be-1", title: "하나" }] as unknown as BackendDescriptor[];
const agents = [
  { kind: "agent", id: "a1", name: "일꾼" },
  { kind: "agent", id: "a2", name: "지정됨", backend: "be-1" },
] as unknown as Agent[];
const graph = (over: Record<string, unknown> = {}): Graph =>
  ({
    kind: "graph", id: "g", name: "g",
    nodes: [
      { id: "h", type: "t-human", label: "나" },
      { id: "n1", type: "t-actor", label: "일꾼 노드", config: { ref: "a1" } },
      { id: "n2", type: "t-actor", config: { ref: "a2" } },
      { id: "r", type: "t-asset", config: { ref: "a1" } },
    ],
    ...over,
  }) as unknown as Graph;

describe("precheckBackends", () => {
  it("백엔드가 비어 있는 에이전트 노드의 이름과 고를 수 있는 목록을 돌려준다(사람·리소스 노드는 보지 않는다)", () => {
    const res = precheckBackends({ graph: graph(), nodeTypes, agents, defaultBackend: undefined, options });
    expect(res).toEqual({ labels: ["일꾼 노드"], options });
  });

  it("공통 기본값·팀 설정·노드 설정 중 하나라도 있으면 통과", () => {
    expect(precheckBackends({ graph: graph(), nodeTypes, agents, defaultBackend: "be-1", options })).toBeUndefined();
    expect(precheckBackends({ graph: graph({ settings: { backend: "be-1" } }), nodeTypes, agents, defaultBackend: null, options })).toBeUndefined();
    const g = graph();
    g.nodes![1]!.config = { ref: "a1", backend: "be-1" };
    expect(precheckBackends({ graph: g, nodeTypes, agents, defaultBackend: "", options })).toBeUndefined();
  });

  it("에이전트 목록에 없는 정의를 가리키는 노드는 점검하지 않는다", () => {
    const g = graph();
    g.nodes![1]!.config = { ref: "missing" };
    expect(precheckBackends({ graph: g, nodeTypes, agents, defaultBackend: undefined, options })).toBeUndefined();
  });
});
