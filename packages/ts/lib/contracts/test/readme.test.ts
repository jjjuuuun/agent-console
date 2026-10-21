import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { CONTRACTS_VERSION, getContractSchema } from "@agent-console/contracts";

const schema = getContractSchema("WorkspaceSettings"); // SchemaForm에 그대로 넘긴다
const version = CONTRACTS_VERSION;
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(schema).toHaveProperty("$defs");
  expect(version).toMatch(/^\d+\.\d+\.\d+/);
});
