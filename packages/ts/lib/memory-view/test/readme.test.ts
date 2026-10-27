import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { groupScopes, scopeLabel, visibleScopes } from "@agent-console/memory-view";
import { sampleKinds, sampleScopes } from "@agent-console/memory-view/testing";

const kinds = sampleKinds();
const scopes = sampleScopes();
const { visible, hidden } = visibleScopes(scopes, kinds, "P1", ["g1"]);
const tree = groupScopes(kinds, visible);
const label = scopeLabel({ kind: "desk", id: "g1" }, kinds[1], { graph_id: () => ({ status: "named", name: "개발팀" }) });
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(visible.length).toBe(4);
  expect(hidden.length).toBe(6);
  expect(tree.groups.map((g) => g.kind)).toEqual(["ledger", "desk", "cabinet", "pair", "weekly"]);
  expect(label.text).toBe("개발팀");
});
