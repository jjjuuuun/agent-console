import { computeEffectiveKeys } from "@agent-console/ui";
import { describe, expect, it } from "vitest";
import { buildTaskShortcuts, TASK_SHORTCUT_DEFS, TASK_SHORTCUT_SCOPE } from "./taskShortcuts";

describe("작업 탭 행 단축키 데이터 (6R.20i)", () => {
  it("S·R·O·Shift+F10이 표에 있고 같은 범위에서 겹치지 않는다", () => {
    expect(TASK_SHORTCUT_DEFS.map((d) => d.keys)).toEqual(["s", "r", "o", "Shift+F10"]);
    const effective = computeEffectiveKeys(TASK_SHORTCUT_DEFS.map((d) => ({ id: d.id, scope: TASK_SHORTCUT_SCOPE, keys: d.keys, titleKey: d.titleKey })));
    expect(effective.filter((e) => e.conflict !== undefined)).toEqual([]);
  });

  it("핸들러가 있는 동작만 등록한다(실행 연동이 없으면 R을 주지 않는다)", () => {
    const defs = buildTaskShortcuts({ status: () => undefined, open: () => undefined });
    expect(defs.map((d) => d.keys)).toEqual(["s", "o"]);
  });

  it("ui.keybindings가 키를 덮어쓰고 빈 문자열이면 끈다", () => {
    const base = TASK_SHORTCUT_DEFS.map((d) => ({ id: d.id, scope: TASK_SHORTCUT_SCOPE, keys: d.keys, titleKey: d.titleKey }));
    const effective = computeEffectiveKeys(base, { [TASK_SHORTCUT_DEFS[0].id]: "x", [TASK_SHORTCUT_DEFS[1].id]: "" });
    expect(effective.map((e) => e.keys)).toEqual(["x", "", "o", "Shift+F10"]);
  });
});
