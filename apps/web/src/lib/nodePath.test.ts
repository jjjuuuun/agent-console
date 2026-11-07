import { describe, expect, it } from "vitest";
import { resolveNodePath } from "./nodePath";

const has = (n: string) => n === "T" || n === "x/y";

describe("resolveNodePath", () => {
  it("그대로 있는 id는 그대로(id 안에 구분자가 있어도)", () => {
    expect(resolveNodePath("x/y", has)).toEqual({ nodeId: "x/y", rest: "" });
  });
  it("경로형 id는 첫 조각(팀 노드)과 나머지 경로로 푼다", () => {
    expect(resolveNodePath("T/a", has)).toEqual({ nodeId: "T", rest: "a" });
    expect(resolveNodePath("T/T/a", has)).toEqual({ nodeId: "T", rest: "T/a" });
  });
  it("첫 조각도 없으면 undefined", () => {
    expect(resolveNodePath("Q/a", has)).toBeUndefined();
    expect(resolveNodePath("zz", has)).toBeUndefined();
  });
});
