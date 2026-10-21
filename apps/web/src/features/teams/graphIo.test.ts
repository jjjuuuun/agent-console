import { describe, expect, it, vi } from "vitest";
import type { Graph } from "@agent-console/contracts";
import { loadGraph, saveGraph } from "./graphIo";

const raw = { kind: "graph", id: "g", name: "팀", nodes: [{ id: "n", type: "t", label: "L", config: { keep: null } }] } as unknown as Graph;

describe("팀 구성 읽기·저장", () => {
  it("서버가 준 저장 원문을 그대로 쓴다(별도 버전 질의·기본값 제거 없음)", async () => {
    const rest = { getGraph: vi.fn(async () => ({ graph: raw, version_hash: "h1" })) };
    const got = await loadGraph(rest as never, "g");
    expect(got).toEqual({ value: raw, version_hash: "h1" });
    expect(got.value).not.toHaveProperty("edges");
  });

  it("저장은 If-Match로 보내고 보낸 문서를 기준으로 돌려준다", async () => {
    const rest = { updateGraph: vi.fn(async () => ({ graph: raw, version_hash: "h2" })) };
    const doc = { id: "g", name: "새" } as Graph;
    expect(await saveGraph(rest as never, doc, "h1")).toEqual({ value: doc, version_hash: "h2" });
    expect(rest.updateGraph).toHaveBeenCalledWith("g", doc, "h1");
  });
});
