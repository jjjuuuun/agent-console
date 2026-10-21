import { describe, expect, expectTypeOf, it } from "vitest";
import {
  CONTRACTS_VERSION,
  KNOWN_RUN_EVENT_TYPES,
  PACKAGE_NAME,
  WS_AUTH_CLOSE_CODES,
  WS_CLOSE_FORBIDDEN,
  WS_CLOSE_UNAUTHORIZED,
  contractSchemaNames,
  getContractSchema,
  isKnownRunEvent,
  type Graph,
  type RunEvent,
  type RunEventOf,
  type WsServerMessage,
} from "./index";

const baseEvent = { event_id: "e1", run_id: "r1", seq: 1, ts: 0, node_path: [] };

describe("@agent-console/contracts", () => {
  it("스모크: 패키지를 단독으로 import할 수 있다", () => {
    expect(PACKAGE_NAME).toBe("@agent-console/contracts");
    expect(CONTRACTS_VERSION).toMatch(/^\d+\.\d+\.\d+$/);
  });

  it("WS 인증 close 코드 상수가 계약에서 나온다", () => {
    expect(WS_CLOSE_UNAUTHORIZED).toBe(4401);
    expect(WS_CLOSE_FORBIDDEN).toBe(4403);
    expect(WS_AUTH_CLOSE_CODES).toEqual([4401, 4403]);
  });

  it("생성된 스키마에 Phase 1 모델이 모두 있다", () => {
    const names = contractSchemaNames();
    for (const name of ["Agent", "Graph", "NodeTypeDescriptor", "RunEvent", "WsServerMessage", "WorkspaceSettings", "Issue", "ErrorResponse"]) {
      expect(names).toContain(name);
    }
  });

  it("getContractSchema는 $defs를 포함한 독립 스키마를 돌려준다", () => {
    const schema = getContractSchema("WorkspaceSettings");
    // 모델 title은 설정 폼에 보이는 표시명이다(타입 이름은 $defs 키).
    expect(schema["title"]).toBe("워크스페이스 설정");
    expect(schema["$defs"]).toHaveProperty("AgentSettings");
    expect(schema["$defs"]).not.toHaveProperty("ConsoleSettings"); // 2R.20에서 삭제
    expect(() => getContractSchema("NoSuchModel")).toThrow();
  });

  it("isKnownRunEvent: 알려진 type만 좁힌다, 모르는 type은 일반 이벤트", () => {
    const known: RunEvent = { ...baseEvent, type: "agent.text_delta", payload: { text: "안녕" } };
    const unknown: RunEvent = { ...baseEvent, type: "plugin.custom", payload: {} };
    expect(isKnownRunEvent(known)).toBe(true);
    expect(isKnownRunEvent(unknown)).toBe(false);
    expect(KNOWN_RUN_EVENT_TYPES).toContain("node.waiting");
    if (isKnownRunEvent(known) && known.type === "agent.text_delta") {
      expectTypeOf(known.payload.text).toEqualTypeOf<string>();
    }
  });

  it("타입: 임의 노드 타입 id를 쓰는 그래프, 판별 유니온", () => {
    const graph: Graph = {
      id: "g",
      name: "그래프",
      nodes: [{ id: "n1", type: "anything-at-all", config: { foo: 1 } }],
      edges: [{ id: "e1", kind: "whatever", source: { node: "n1", port: "o" }, target: { node: "n1", port: "i" } }],
    };
    expect(graph.nodes?.[0]?.type).toBe("anything-at-all");
    expectTypeOf<RunEventOf<"agent.usage">["payload"]["usage"]["input_tokens"]>().toEqualTypeOf<number | null | undefined>();
    const msg: WsServerMessage = { type: "error", payload: { code: "bad_request", message: "m" } };
    expect(msg.type).toBe("error");
  });
});
