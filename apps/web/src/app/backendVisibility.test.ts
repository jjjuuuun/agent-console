import { describe, expect, it } from "vitest";
import { isHiddenBackend, visibleBackends } from "./backendVisibility";

describe("backendVisibility", () => {
  it("ui_hints.hidden이 true인 것만 숨긴다", () => {
    const list = [{ id: "a", ui_hints: { hidden: true } }, { id: "b", ui_hints: { hidden: false } }, { id: "c" }, { id: "d", ui_hints: { badge: "x" } }];
    expect(isHiddenBackend(list[0]!)).toBe(true);
    expect(visibleBackends(list).map((d) => d.id)).toEqual(["b", "c", "d"]);
  });
});
