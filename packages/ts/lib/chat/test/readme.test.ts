import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Composer } from "@agent-console/chat";

const html = renderToStaticMarkup(createElement(Composer, { value: "안녕", onChange: () => {}, onSend: () => {} }));
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(html).toContain("안녕");
});
