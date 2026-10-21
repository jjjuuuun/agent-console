/** 팀 구성·에이전트·리소스 화면 테스트용 임의 이름 디스크립터와 응답 픽스처. */
import type { Agent, EdgeTypeDescriptor, Graph, NodeTypeDescriptor, ResourceTypeDescriptor } from "@agent-console/contracts";

export const KIND_DEF = "k-def";
export const KIND_ASSET = "k-asset";

export const nodeTypes = [
  { id: "t-actor", version: 1, title: "행위자", role: "r-actor", executable: true, binds: { kind: "agent", field: "ref" }, config_schema: { type: "object", properties: { ref: { type: "string" }, role: { anyOf: [{ type: "string" }, { type: "null" }], default: null }, delegate_when: { anyOf: [{ type: "string" }, { type: "null" }], default: null }, settings: { anyOf: [{ type: "object" }, { type: "null" }], default: null } } }, static_ports: { inputs: [{ name: "i1", label: "받음" }, { name: "i2", label: "자료" }], outputs: [{ name: "o1", label: "냄" }] } },
  { id: "t-asset", version: 1, title: "자산", role: "r-asset", executable: false, binds: { kind: "resource", field: "asset_ref" }, config_schema: { type: "object", properties: { asset_ref: { type: "string" } } }, static_ports: { inputs: [], outputs: [{ name: "provide" }] }, ui_hints: { shape: "chip" } },
  { id: "t-human", version: 1, title: "사람", role: "r-human", executable: true, config_schema: { type: "object", properties: { check: { anyOf: [{ $ref: "#/$defs/Check" }, { type: "null" }], default: null, title: "점검" } }, $defs: { Check: { type: "object", title: "점검 설정", properties: { options: { type: "array", minItems: 1, items: { $ref: "#/$defs/Opt" }, title: "선택지" } }, required: ["options"] }, Opt: { type: "object", properties: { id: { type: "string" }, label: { type: "string", default: "" } }, required: ["id"] } } }, static_ports: { inputs: [{ name: "hears" }], outputs: [{ name: "says" }] } },
] as unknown as NodeTypeDescriptor[];

export const edgeTypes = [
  { id: "e-in", version: 1, title: "들어감", scheduling: "entry", connects: { source: ["r-human"], target: ["r-actor"] }, default_ports: { source: "says", target: "i1" }, config_schema: { type: "object", properties: {} } },
  { id: "e-out", version: 1, title: "나감", scheduling: "exit", connects: { source: ["r-actor"], target: ["r-human"] }, default_ports: { source: "o1", target: "hears" }, config_schema: { type: "object", properties: { final: { type: "boolean", default: true, title: "최종" }, label: { anyOf: [{ type: "string" }, { type: "null" }], default: null, title: "이름" } } } },
  { id: "e-attach", version: 1, title: "붙임", scheduling: "none", connects: { source: ["r-asset"], target: ["r-actor"] }, default_ports: { source: "provide", target: "i2" }, config_schema: { type: "object", properties: { mode: { anyOf: [{ type: "string" }, { type: "null" }], enum: ["add", "replace", "remove"], default: null, title: "방식" } } } },
] as unknown as EdgeTypeDescriptor[];

export const resourceTypes = [
  { id: "rt-doc", version: 1, title: "문서종류", description: "문서", content: { editor: "markdown", media_types: ["text/markdown", "text/plain"] }, config_schema: { type: "object", properties: { heading: { type: "string", title: "머리글" } } }, ui_hints: { icon: "문" } },
  { id: "rt-cfg", version: 1, title: "설정종류", config_schema: { type: "object", properties: { cmd: { type: "string", title: "명령" } } }, ui_hints: { icon: "설" } },
] as unknown as ResourceTypeDescriptor[];

/** 서버가 주는 저장 원문 모양: 지정한 키만 있다. */
export const agents = [
  { kind: "agent", id: "ag1", name: "첫째 에이전트", role: "역할1", description: "설명1", system_prompt: "지침" },
  { kind: "agent", id: "ag2", name: "둘째 에이전트" },
] as unknown as Agent[];

/** 사용자(사람) → 행위자 입구 연결이 있고, 답변 연결은 없는 팀 구성(검증이 "답변 없음"을 제안으로 알린다). */
export function sampleGraph(): Graph {
  return {
    kind: "graph", id: "tm1", name: "임의 팀", description: "팀 설명",
    nodes: [
      { id: "h1", type: "t-human", label: "나", position: { x: 0, y: 0 } },
      { id: "a1", type: "t-actor", label: "일꾼", config: { ref: "ag1" }, position: { x: 300, y: 0 } },
    ],
    edges: [{ id: "x1", kind: "e-in", source: { node: "h1", port: "says" }, target: { node: "a1", port: "i1" } }],
  } as unknown as Graph;
}

export const replySuggestion = {
  severity: "warning", code: "c.no-reply", message: "답변으로 이어지는 연결이 없습니다", node_id: "a1",
  suggestions: [{ id: "s1", label: "일꾼 → 나 답변으로 연결", patch: { add_edges: [{ id: "x2", kind: "e-out", source: { node: "a1", port: "o1" }, target: { node: "h1", port: "hears" } }] } }],
};
