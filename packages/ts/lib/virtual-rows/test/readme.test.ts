import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { useRef } from "react";
import { useVirtualRows } from "@agent-console/virtual-rows";

// Inside a list component: pass the scroll container ref, the row count, and the row height, then render only the visible rows.
export function useRows(count: number) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualRows({ count, rowHeight: 32, scrollRef });
  return { scrollRef, items: virtualizer.getVirtualItems(), totalSize: virtualizer.getTotalSize() };
}
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(typeof useRows).toBe("function");
});
