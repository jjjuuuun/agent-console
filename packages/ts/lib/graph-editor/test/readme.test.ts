import { expect, test } from "vitest";

// The ```ts readme block in the README "Minimal usage" section must match the marked range below (`pnpm pkg-lint` checks it).
// readme:start
import { categoryColorSlot, categoryColorVar } from "@agent-console/graph-editor";

// Node category string -> category color slot. The same string always gets the same color.
const slot = categoryColorSlot("review");
const cssVar = categoryColorVar("review");
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(cssVar).toBe(`var(--ac-cat-${slot})`);
  expect(categoryColorSlot("")).toBe("neutral");
});
