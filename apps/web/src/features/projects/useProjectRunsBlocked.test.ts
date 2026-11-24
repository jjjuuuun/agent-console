import { describe, expect, it } from "vitest";
import { findRunsBlocked } from "./useProjectRunsBlocked";

describe("findRunsBlocked: 서버 경고에서 프로젝트 실행 막힘 찾기", () => {
  it("feature_unavailable + 포트 runs.scopes 경고가 있으면 막힘과 서버 문구", () => {
    const w = [{ code: "storage.memory", message: "x" }, { code: "feature_unavailable", message: "연동 꺼짐", details: { module: "m", port: "runs.scopes" } }];
    expect(findRunsBlocked(w)).toEqual({ blocked: true, message: "연동 꺼짐" });
  });
  it("경고가 없거나 다른 포트면 막지 않는다", () => {
    expect(findRunsBlocked(undefined)).toEqual({ blocked: false, message: undefined });
    expect(findRunsBlocked([{ code: "feature_unavailable", message: "m", details: { port: "usage" } }]).blocked).toBe(false);
  });
});
