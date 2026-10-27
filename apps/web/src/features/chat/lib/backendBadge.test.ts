import { describe, expect, it } from "vitest";
import type { Agent, BackendDescriptor, NodeSpec } from "@agent-console/contracts";
import { badgeOfBackend, effectiveBackendId } from "./backendBadge";

const node = (config?: Record<string, unknown>): NodeSpec => ({ id: "n", type: "t", ...(config ? { config } : {}) }) as NodeSpec;

describe("effectiveBackendId", () => {
  it("노드 → 에이전트 → 팀 구성 → 공통 순서로 해석한다", () => {
    const agent = { id: "a", backend: "agent-b" } as Agent;
    expect(effectiveBackendId(agent, node({ backend: "node-b" }), "common-b", "team-b")).toBe("node-b");
    expect(effectiveBackendId(agent, node(), "common-b", "team-b")).toBe("agent-b");
    expect(effectiveBackendId(undefined, node(), "common-b", "team-b")).toBe("team-b");
    expect(effectiveBackendId(undefined, node(), "common-b", undefined)).toBe("common-b");
    expect(effectiveBackendId(undefined, node(), null)).toBeUndefined();
  });
  it("팀 층에만 백엔드가 있으면 그 백엔드의 칩이 붙는다", () => {
    const backends = new Map<string, BackendDescriptor>([["fake", { id: "fake", title: "체험", ui_hints: { badge: "체험" } } as BackendDescriptor]]);
    const id = effectiveBackendId({ id: "a" } as Agent, node(), undefined, "fake");
    expect(badgeOfBackend(backends, id)).toBe("체험");
  });
});
