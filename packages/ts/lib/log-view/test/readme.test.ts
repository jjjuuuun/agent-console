import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { isErrorEvent, sortEvents, splitSearchParams, toTaxonomyView } from "@agent-console/log-view";

// An error is decided only by the taxonomy entries with tone="danger" (no name comparison).
const taxonomy = toTaxonomyView({ categories: { "x-fail": { tone: "danger" } } });
const failing = isErrorEvent({ category: "x-fail" }, taxonomy);
// Playback order is ascending by (time, seq).
const order = sortEvents([{ seq: 2, time: 5 }, { seq: 1, time: 9 }]).map((e) => e.seq);
// Screen-only URL parameters (through, lane, view, range, tab) are left out of the server filter.
const { filter, screen } = splitSearchParams("q=abc&through=7");
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(failing).toBe(true);
  expect(order).toEqual([2, 1]);
  expect(filter).toEqual({ q: "abc" });
  expect(screen).toEqual({ through: ["7"] });
});
