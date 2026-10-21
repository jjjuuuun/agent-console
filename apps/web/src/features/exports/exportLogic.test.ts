import { describe, expect, it } from "vitest";
import { ApiError } from "@agent-console/api-client";
import {
  addItem,
  blockingIssues,
  buildRequest,
  checkSubdir,
  conflictPathsOf,
  exporterSupports,
  mapPlanError,
  overwriteCount,
  parseConflictPolicy,
  subdirErrorOf,
  summarizeFiles,
} from "./exportLogic";

describe("exportLogic", () => {
  it("충돌 처리 기본은 fail, 모르는 저장값도 fail", () => {
    expect(parseConflictPolicy(null)).toBe("fail");
    expect(parseConflictPolicy("zzz")).toBe("fail");
    expect(parseConflictPolicy("overwrite")).toBe("overwrite");
  });
  it("플랜 요약: 모르는 동작도 센다, 덮어쓰기 확인 개수 = 덮어씀 + 충돌", () => {
    const files = [
      { path: "a", size: 10, action: "create" as const },
      { path: "b", size: 20, action: "overwrite" as const },
      { path: "c", size: 5, action: "conflict" as const },
      { path: "d", size: 1, action: "weird" as never },
    ];
    expect(summarizeFiles(files)).toEqual({ count: 4, bytes: 36, byAction: { create: 1, overwrite: 1, conflict: 1, weird: 1 } });
    expect(overwriteCount(files)).toBe(2);
  });
  it("error 경고만 차단", () => {
    expect(blockingIssues([{ severity: "warning", code: "x.y", message: "m" }, { severity: "error", code: "x.z", message: "m" }])).toHaveLength(1);
    expect(blockingIssues(undefined)).toEqual([]);
  });
  it("형식이 지원하는 종류만 true(없으면 false)", () => {
    expect(exporterSupports({ kinds: ["k1"] }, "k1")).toBe(true);
    expect(exporterSupports({ kinds: ["k1"] }, "k2")).toBe(false);
    expect(exporterSupports(undefined, "k1")).toBe(false);
  });
  it("하위 폴더 즉시 검사", () => {
    expect(checkSubdir("")).toBeUndefined();
    expect(checkSubdir("a/b")).toBeUndefined();
    expect(checkSubdir("/abs")).toBe("absolute");
    expect(checkSubdir("C:\\x")).toBe("absolute");
    expect(checkSubdir("a/../b")).toBe("dotdot");
    expect(checkSubdir("a//b")).toBe("empty_segment");
    expect(checkSubdir("a/")).toBe("empty_segment");
    expect(checkSubdir("a:b")).toBe("forbidden_char");
    expect(checkSubdir("a?b")).toBe("forbidden_char");
  });
  it("요청: 루트가 있을 때만 root·subdir를 싣는다", () => {
    expect(buildRequest({ exporter: "e", items: [{ kind: "k", id: "i" }], options: { a: 1 } })).toEqual({ exporter: "e", items: [{ kind: "k", id: "i" }], options: { a: 1 } });
    expect(buildRequest({ exporter: "e", items: [], options: {}, root: "r", subdir: " s " })).toMatchObject({ root: "r", subdir: "s" });
  });
  it("422 issues를 옵션 폼 오류·항목 오류로 연결한다", () => {
    const err = new ApiError(422, {
      code: "validation_failed",
      message: "검증",
      details: { issues: [{ path: "/options/main_node", message: "없는 노드" }, { path: "/items/1/kind", message: "지원 안 함" }, { path: "", message: "기타" }] },
    });
    const m = mapPlanError(err);
    expect(m.options).toEqual([{ path: "/main_node", message: "없는 노드", severity: "error" }]);
    expect(m.items.get(1)).toBe("지원 안 함");
    expect(m.other).toEqual(["기타"]);
    expect(m.routable).toBe(true);
    expect(mapPlanError(new Error("x")).routable).toBe(false);
    expect(mapPlanError(new ApiError(500, { code: "x", message: "서버" })).other).toEqual(["서버"]);
  });
  it("쓰기 오류에서 subdir 메시지와 충돌 경로를 읽는다", () => {
    expect(subdirErrorOf(new ApiError(422, { code: "validation_failed", message: "m", details: { issues: [{ path: "/subdir", message: "링크 거부" }] } }))).toBe("링크 거부");
    expect(subdirErrorOf(new ApiError(409, { code: "already_exists", message: "m" }))).toBeUndefined();
    expect(conflictPathsOf(new ApiError(409, { code: "already_exists", message: "m", details: { paths: ["a.md", 3] } }))).toEqual(["a.md"]);
  });
  it("항목 추가는 중복을 막는다", () => {
    expect(addItem([{ kind: "k", id: "i" }], { kind: "k", id: "i" })).toHaveLength(1);
    expect(addItem([{ kind: "k", id: "i" }], { kind: "k", id: "j" })).toHaveLength(2);
  });
});
