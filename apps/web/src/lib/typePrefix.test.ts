import { describe, expect, it } from "vitest";
import { joinTypePrefixes, matchesTypePrefix } from "./typePrefix";

describe("접두 필터(여러 접두)", () => {
  it("쉼표로 이은 접두 중 하나라도 맞으면 통과하고 빈 값은 모두 통과한다", () => {
    expect(joinTypePrefixes(["a.x", "a.y"])).toBe("a.x,a.y");
    expect(matchesTypePrefix("a.y", "a.x,a.y")).toBe(true);
    expect(matchesTypePrefix("a.z", "a.x,a.y")).toBe(false);
    expect(matchesTypePrefix("a.z", "")).toBe(true);
  });
});
