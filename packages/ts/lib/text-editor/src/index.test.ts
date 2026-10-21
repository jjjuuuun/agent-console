import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PACKAGE_NAME } from "./index";

describe("@agent-console/text-editor", () => {
  it("단독으로 import할 수 있다", () => {
    expect(PACKAGE_NAME).toBe("@agent-console/text-editor");
  });
  it("다른 @agent-console 패키지를 import하지 않는다", () => {
    const dir = import.meta.dirname;
    for (const f of readdirSync(dir).filter((n) => /\.(ts|tsx)$/.test(n) && !n.includes(".test."))) {
      expect(readFileSync(join(dir, f), "utf-8"), f).not.toMatch(/from ["']@agent-console\//);
    }
  });
});
