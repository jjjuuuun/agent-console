import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { categoryColorSlot, categoryColorVar } from "@agent-console/graph-editor";

// 노드 분류(category) 문자열 -> 분류색 슬롯. 같은 문자열은 언제나 같은 색이다.
const slot = categoryColorSlot("review");
const cssVar = categoryColorVar("review");
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(cssVar).toBe(`var(--ac-cat-${slot})`);
  expect(categoryColorSlot("")).toBe("neutral");
});
