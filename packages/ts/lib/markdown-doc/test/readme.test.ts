import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { formatMessage, resolveMessages, statusTone } from "@agent-console/markdown-doc";

const chip = statusTone("s2", [{ id: "s2", label: "검토", tone: "info" }]);
const text = resolveMessages({ "editor.save": "올리기" });
const line = formatMessage(text["editor.issue.line"], { line: 7 });
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(chip).toEqual({ id: "s2", label: "검토", tone: "info", done: false });
  expect(text["editor.save"]).toBe("올리기");
  expect(line).toBe("7번째 줄");
});
