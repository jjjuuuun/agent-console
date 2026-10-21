import { describe, expect, it } from "vitest";
import { PACKAGE_NAME } from "./index";

describe("@agent-console/ui", () => {
  it("스모크: 패키지를 단독으로 import할 수 있다", () => {
    expect(PACKAGE_NAME).toBe("@agent-console/ui");
  });
});
