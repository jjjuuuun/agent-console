import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { groupByStage, planToFlow, statusTone } from "@agent-console/sdd-view";
import { samplePlan, sampleStatuses, sampleTasks } from "@agent-console/sdd-view/testing";

const statuses = sampleStatuses();
const tasks = sampleTasks();
const groups = groupByStage(tasks, (s) => statuses.some((x) => x.id === s && x.done === true));
const chip = statusTone("s-done", statuses);
const flow = planToFlow(samplePlan(), tasks);
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(groups.map((g) => [g.key, g.done, g.total])).toEqual([["st1", 1, 2], ["st2", 0, 2], ["", 0, 1]]);
  expect(chip).toEqual({ id: "s-done", label: "끝", tone: "success", done: true });
  expect(flow.nodes).toHaveLength(5);
  expect(flow.edges.some((e) => e.critical)).toBe(true);
});
