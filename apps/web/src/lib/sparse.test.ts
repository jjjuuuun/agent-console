import { describe, expect, it } from "vitest";
import { withoutLayer } from "./sparse";

describe("withoutLayer", () => {
  it("한 층이 정한 잎만 뺀다", () => {
    const eff = { a: 1, group: { one: 2, two: 3 } };
    expect(withoutLayer(eff, { "/a": "up", "/group/one": "up", "/group/two": "low" }, "up")).toEqual({ group: { two: 3 } });
  });
});
