import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { byText, folderOf, groupItems, sortItems, withFolder, type GroupByDef } from "@agent-console/list-arrange";

interface Doc { name: string; attributes?: Record<string, unknown> }
const byFolder: GroupByDef<Doc> = { id: "folder", titleKey: "group.folder", tree: true, read: (d) => [folderOf(d.attributes) ?? ""] };
const docs: Doc[] = [{ name: "나", attributes: withFolder({}, "개발/백엔드") }, { name: "가" }];
const groups = groupItems(sortItems(docs, byText((d) => d.name)), byFolder);
const summary = groups.map((g) => `${g.key}:${g.count}`);
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(summary).toEqual(["개발:0", "개발/백엔드:1", `\u0000none:1`]);
});
