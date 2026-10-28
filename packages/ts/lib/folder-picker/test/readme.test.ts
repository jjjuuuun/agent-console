import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { deriveCheckState, middleEllipsis } from "@agent-console/folder-picker";

const short = middleEllipsis("/home/me/work/payments/services/api", 27);
const state = deriveCheckState("/srv/app", {
  kind: "checked",
  check: { input: "/srv/app", path: "/srv/app", exists: true, is_dir: true, readable: true, writable: true, can_create: false },
});
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(short).toBe("/home/me/work…/services/api");
  expect(state.id).toBe("ok");
  expect(state.submittable).toBe(true);
});
