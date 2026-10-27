import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { checkLayout, edgePath, formatMetric, gridLayout } from "@agent-console/arch-view";
import { defaultProfileView } from "@agent-console/arch-view/testing";

const view = defaultProfileView();
const problems = checkLayout(view);
const rects = gridLayout(view);
const llm = formatMetric({ status: "not_collected", value: null });
const line = edgePath(null, rects["input"], rects["sdk"]);
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(problems).toEqual([]);
  expect(llm.text).toBe("–");
  expect(line).toEqual([[226, 130], [374, 130]]);
});
