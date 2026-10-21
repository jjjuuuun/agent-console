import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { jsonParseError } from "@agent-console/text-editor";

const broken = jsonParseError('{"a": ');
const fine = jsonParseError('{"a": 1}');
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(typeof broken).toBe("string");
  expect(fine).toBeUndefined();
});
