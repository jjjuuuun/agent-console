import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { createCurrentProjectStore, logFilterFor, spaceParam } from "@agent-console/projects";

const store = createCurrentProjectStore({ location: { getSearch: () => "?project=app", setSearch: () => {} } });

const current = store.get();
const logFilter = logFilterFor(current).filter;
const query = spaceParam(current);
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(current).toBe("app");
  expect(logFilter).toEqual({ project: "app" });
  expect(query).toBe("app");
});
