import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Button, formatBadgeCount } from "@agent-console/ui";

const html = renderToStaticMarkup(createElement(Button, null, "저장"));
const badge = formatBadgeCount(120);
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(html).toContain("저장");
  expect(badge).toBe("99+");
});
