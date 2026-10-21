import { describe, expect, it } from "vitest";
import type { Graph } from "@agent-console/contracts";
import { compactGraph, newAttachment } from "./serialize";
import { withSubjectParticle } from "./format";

describe("저장 직렬화", () => {
  it("노드·연결과 config 최상위의 null 키를 지우고, 값이 있는 키와 명시 설정은 둔다", () => {
    const g = {
      id: "g", name: "g",
      nodes: [{ id: "u", type: "t", label: null, config: { role: null, delegate_when: null, settings: null, keep: false, settings2: { a: null } } }, { id: "v", type: "t", config: { review: null } }],
      edges: [{ id: "e", source: { node: "u", port: "o" }, target: { node: "v", port: "i" }, kind: "k", config: { label: null, order: null, final: true } }],
    } as unknown as Graph;
    const out = compactGraph(g) as unknown as { nodes: { config?: Record<string, unknown>; label?: unknown }[]; edges: { config: Record<string, unknown> }[] };
    expect(out.nodes[0]!.config).toEqual({ keep: false, settings2: { a: null } });
    expect("label" in out.nodes[0]!).toBe(false);
    expect("config" in out.nodes[1]!).toBe(false);
    expect(out.edges[0]!.config).toEqual({ final: true });
    expect((g.nodes![0] as { config: unknown }).config).toHaveProperty("role");
  });

  it("바뀐 곳이 없으면 같은 객체", () => {
    const g = { id: "g", name: "g", nodes: [{ id: "u", type: "t" }], edges: [] } as unknown as Graph;
    expect(compactGraph(g)).toBe(g);
  });

  it("새 첨부는 서버 기본 방식이면 mode를 적지 않는다", () => {
    expect(newAttachment("r")).toEqual({ ref: "r" });
    expect(newAttachment("r", "add")).toEqual({ ref: "r" });
    expect(newAttachment("r", "replace")).toEqual({ ref: "r", mode: "replace" });
  });
});

describe("주격 조사", () => {
  it("받침에 따라 이/가", () => {
    expect(withSubjectParticle("도우미")).toBe("도우미가");
    expect(withSubjectParticle("검토")).toBe("검토가");
    expect(withSubjectParticle("리더 에이전트")).toBe("리더 에이전트가");
    expect(withSubjectParticle("백엔드 팀원")).toBe("백엔드 팀원이");
    expect(withSubjectParticle("n1")).toBe("n1이(가)");
  });
});
