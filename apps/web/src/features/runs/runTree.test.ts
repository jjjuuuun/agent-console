import { describe, expect, it } from "vitest";
import type { Run } from "@agent-console/contracts";
import { activeDescendants, ancestorChain, directChildren, failedChildCount, siblingIndex, splitSubscriptions } from "./runTree";

const run = (id: string, extra: Partial<Run> = {}): Run => ({ id, graph_id: "g", graph_version: "v", status: "completed", input: {}, origin: "chat", created_at: 1, ...extra });

describe("자식 Run 트리 계산", () => {
  const root = run("root");
  const c1 = run("c1", { parent_run_id: "root", root_run_id: "root", parent_node_id: "t", created_at: 2 });
  const c2 = run("c2", { parent_run_id: "root", root_run_id: "root", parent_node_id: "t", created_at: 3, status: "running" });
  const g1 = run("g1", { parent_run_id: "c2", root_run_id: "root", parent_node_id: "u", created_at: 4, status: "waiting" });

  it("체인은 루트부터 현재까지, 끊기면 찾은 데까지", () => {
    expect(ancestorChain([root, c1], g1).map((r) => r.id)).toEqual(["g1"]);
    expect(ancestorChain([root, c1, c2, g1], g1).map((r) => r.id)).toEqual(["root", "c2", "g1"]);
    expect(ancestorChain([], root).map((r) => r.id)).toEqual(["root"]);
  });
  it("순환이 있어도 멈춘다", () => {
    const a = run("a", { parent_run_id: "b" });
    const b = run("b", { parent_run_id: "a" });
    expect(ancestorChain([a, b], a).length).toBeLessThanOrEqual(2);
  });
  it("직접 자식: 서버가 채운 목록 우선, 아니면 후손에서 부모가 같은 것(만든 순)", () => {
    expect(directChildren("root", [c2, c1], []).map((r) => r.id)).toEqual(["c1", "c2"]);
    expect(directChildren("root", null, [g1, c2, c1]).map((r) => r.id)).toEqual(["c1", "c2"]);
    expect(directChildren("root", [], [c1])).toEqual([]);
  });
  it("활성 후손은 자식·손자를 함께 센다", () => {
    expect(activeDescendants([c1, c2, g1], "root").map((r) => r.id)).toEqual(["c2", "g1"]);
    expect(activeDescendants([c1, c2, g1], "c2").map((r) => r.id)).toEqual(["g1"]);
  });
  it("실패한 자식 수, 같은 노드의 몇 번째 자식인지", () => {
    expect(failedChildCount([c1, run("c3", { status: "failed" })])).toBe(1);
    expect(siblingIndex([c1, c2], c2)).toEqual({ index: 1, total: 2 });
    expect(siblingIndex([c1], c1)).toEqual({ index: 0, total: 1 });
  });
  it("구독 상한: 앞에서부터 상한까지 구독하고 나머지는 폴링", () => {
    expect(splitSubscriptions(["a", "b", "c", "d", "e", "f", "g"], 5)).toEqual({ subscribe: ["a", "b", "c", "d", "e"], poll: ["f", "g"] });
    expect(splitSubscriptions(["a"], 5)).toEqual({ subscribe: ["a"], poll: [] });
  });
});
