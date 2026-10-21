import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { getDefaultValue } from "@agent-console/schema-form";

const schema = { type: "object", properties: { name: { type: "string", default: "새 이름" } } };
const value = getDefaultValue(schema);
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(value).toEqual({ name: "새 이름" });
});
