import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { formatDuration } from "@agent-console/trace-view";

const text = formatDuration(125, { s: "초", m: "분", h: "시간" });
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(text).toBe("2분 5초");
});
