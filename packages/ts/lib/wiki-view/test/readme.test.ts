import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { linkifySource } from "@agent-console/wiki-view";

const content = "가나 😀 [[다라]] 끝";
// 서버가 준 링크 범위(UTF-16): content.slice(start, end) === "[[다라]]"
const link = { start: 6, end: 12, raw: "[[다라]]", kind: "wikilink", rule_id: "r", label: "다라", status: "ok", resolved: "da" };
const text = linkifySource(content, [link]);
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(content.slice(link.start, link.end)).toBe(link.raw);
  expect(text).toBe("가나 😀 [다라](ac-wiki:6) 끝");
});
