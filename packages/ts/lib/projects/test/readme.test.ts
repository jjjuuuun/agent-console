import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { createCurrentProjectStore, defaultScopeFor, filterByScope, scopeBadge, badgeLabel } from "@agent-console/projects";

const store = createCurrentProjectStore({ location: { getSearch: () => "?project=app", setSearch: () => {} } });
const items = [{ id: "a", project: "app" }, { id: "b", project: null }, { id: "c", project: "other" }];

const current = store.get();
const visible = filterByScope(items, current).map((x) => x.id);
const scopeForNew = defaultScopeFor("resource", current, { new_definition_scope: { agent: "shared" } });
const badge = badgeLabel(scopeBadge("other", current)!);
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(current).toBe("app");
  expect(visible).toEqual(["a", "b"]);
  expect(scopeForNew).toBe("app");
  expect(badge).toBe("다른 프로젝트: other");
});
