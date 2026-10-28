import { describe, expect, it } from "vitest";
import { parseScope } from "./ArchitecturePopoutScreen";

describe("분리 창 범위 인자", () => {
  it("JSON의 문자열·문자열 배열만 받고 모르는 모양은 버린다", () => {
    expect(parseScope(JSON.stringify({ session: "s1", thread: ["a", "b"], n: 3, bad: [1], o: { x: 1 } }))).toEqual({ session: "s1", thread: ["a", "b"] });
  });
  it("비었거나 깨졌거나 객체가 아니면 빈 범위", () => {
    expect(parseScope(null)).toEqual({});
    expect(parseScope("")).toEqual({});
    expect(parseScope("{깨짐")).toEqual({});
    expect(parseScope("[1]")).toEqual({});
  });
});
