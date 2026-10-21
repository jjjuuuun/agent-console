import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { isErrorEvent, sortEvents, splitSearchParams, toTaxonomyView } from "@agent-console/log-view";

// 오류 표시는 분류 체계의 tone="danger" 항목만 근거다(이름 비교 없음).
const taxonomy = toTaxonomyView({ categories: { "x-fail": { tone: "danger" } } });
const failing = isErrorEvent({ category: "x-fail" }, taxonomy);
// 재생 순서는 (time, seq) 오름차순.
const order = sortEvents([{ seq: 2, time: 5 }, { seq: 1, time: 9 }]).map((e) => e.seq);
// 화면 전용 URL 파라미터(through·lane·view·range·tab)는 서버 필터에서 빠진다.
const { filter, screen } = splitSearchParams("q=abc&through=7");
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(failing).toBe(true);
  expect(order).toEqual([2, 1]);
  expect(filter).toEqual({ q: "abc" });
  expect(screen).toEqual({ through: ["7"] });
});
