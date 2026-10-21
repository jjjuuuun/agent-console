import type { MovePlan } from "@agent-console/contracts/projects";
import { describe, expect, test, vi } from "vitest";

import {
  createProjectsClient,
  isRequiredMove,
  mergeMovePlans,
  moveKey,
  moveTargetOfIssue,
  selectMoves,
  type ProjectsIo,
} from "@agent-console/projects";

const plan = (target: string, moves: MovePlan["moves"], warnings: MovePlan["warnings"] = []): MovePlan => ({
  target: { kind: "graph", id: target },
  to: null,
  moves,
  warnings,
});

describe("moves", () => {
  test("mergeMovePlans: 중복 제거, required 승격, 경고 한 번", () => {
    const w = { severity: "warning" as const, code: "project.cross_project", message: "m" };
    const a = plan("t1", [{ kind: "graph", id: "t1", required: true }, { kind: "agent", id: "x", required: false }], [w]);
    const b = plan("t2", [{ kind: "graph", id: "t2", required: true }, { kind: "agent", id: "x", required: true }], [w]);
    const merged = mergeMovePlans([a, b]);
    expect(merged?.target.id).toBe("t1");
    expect(merged?.moves?.map((m) => [m.id, m.required])).toEqual([["t1", true], ["x", true], ["t2", true]]);
    expect(merged?.warnings).toHaveLength(1);
    expect(mergeMovePlans([])).toBeNull();
  });
  test("selectMoves: 필수는 늘, 권장은 include에 든 것만(생략 = 전부)", () => {
    const p = plan("t", [{ kind: "graph", id: "t", required: true }, { kind: "agent", id: "x", required: false }, { kind: "resource", id: "r" }]);
    expect(selectMoves(p).moves).toHaveLength(3);
    expect(selectMoves(p, new Set()).moves?.map((m) => m.id)).toEqual(["t", "r"]);
    expect(selectMoves(p, new Set([moveKey({ kind: "agent", id: "x" })])).moves).toHaveLength(3);
    expect(isRequiredMove({ kind: "a", id: "b" })).toBe(true);
  });
  test("moveTargetOfIssue: 제안이 있는 이슈에서 대상 읽기", () => {
    const suggestions = [{ id: "project.move_to_shared" }];
    expect(moveTargetOfIssue({ suggestions, details: { kind: "agent", id: "a" } })).toEqual({ kind: "agent", id: "a" });
    expect(moveTargetOfIssue({ suggestions, details: { move: { kind: "resource", id: "r", to: null } } })).toEqual({ kind: "resource", id: "r" });
    expect(moveTargetOfIssue({ details: { kind: "agent", id: "a" } })).toBeNull();
    expect(moveTargetOfIssue({ suggestions })).toBeNull();
  });
});

describe("createProjectsClient", () => {
  function make() {
    const request = vi.fn().mockResolvedValue(undefined);
    const requestVersioned = vi.fn().mockResolvedValue({ value: {}, version_hash: "h" });
    const client = createProjectsClient({ request, requestVersioned } as ProjectsIo);
    return { client, request, requestVersioned };
  }
  test("목록·조회", async () => {
    const { client, request, requestVersioned } = make();
    await client.listProjects();
    await client.getProject("a/b");
    await client.getProjectVersioned("a");
    expect(request).toHaveBeenNthCalledWith(1, "GET", "/projects");
    expect(request).toHaveBeenNthCalledWith(2, "GET", "/projects/a%2Fb");
    expect(requestVersioned).toHaveBeenCalledWith("GET", "/projects/a");
  });
  test("만들기·고치기(If-Match는 주었을 때만)", async () => {
    const { client, requestVersioned } = make();
    await client.createProject({ id: "n", name: "n" });
    await client.updateProject("a", { name: "m" });
    await client.updateProject("a", { name: "m" }, "h1");
    expect(requestVersioned).toHaveBeenNthCalledWith(1, "POST", "/projects", { body: { id: "n", name: "n" } });
    expect(requestVersioned).toHaveBeenNthCalledWith(2, "PUT", "/projects/a", { body: { name: "m" } });
    expect(requestVersioned).toHaveBeenNthCalledWith(3, "PUT", "/projects/a", { body: { name: "m" }, headers: { "If-Match": "h1" } });
  });
  test("삭제: 모드 쿼리와 If-Match", async () => {
    const { client, request } = make();
    await client.deleteProject("a");
    await client.deleteProject("a", { mode: "delete_definitions", versionHash: "h" });
    expect(request).toHaveBeenNthCalledWith(1, "DELETE", "/projects/a", {});
    expect(request).toHaveBeenNthCalledWith(2, "DELETE", "/projects/a?mode=delete_definitions", { headers: { "If-Match": "h" } });
  });
  test("계획·옮기기·범위 이슈", async () => {
    const { client, request } = make();
    await client.getDeletePlan("a");
    await client.getMovePlan({ kind: "agent", id: "x", to: null });
    const p = plan("t", []);
    await client.applyMove(p);
    await client.listScopeIssues();
    expect(request.mock.calls.map((c) => [c[0], c[1]])).toEqual([
      ["POST", "/projects/a/delete-plan"],
      ["POST", "/projects/move-plan"],
      ["POST", "/projects/move"],
      ["POST", "/projects/scope-issues"],
    ]);
    expect(request.mock.calls[2]?.[2]).toEqual({ body: p });
  });
});
