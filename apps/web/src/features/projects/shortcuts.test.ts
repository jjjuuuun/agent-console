import { describe, expect, it } from "vitest";
import { computeEffectiveKeys, type ShortcutDef } from "@agent-console/ui";
import { DEFAULT_ROUTES, gotoShortcuts } from "../../shell/routeConfig";
import { PROJECT_SHORTCUT_DEFS } from "./shortcuts";

/** 셸이 고정으로 가진 전역 단축키(Shell.tsx의 defaults). 새 전역 키가 생기면 여기에도 더한다. */
const SHELL_FIXED: Omit<ShortcutDef, "run">[] = [
  { id: "palette.open", scope: "global", keys: "Mod+K", titleKey: "x", modifierRequired: true },
  { id: "pending.jump", scope: "global", keys: "Alt+J", titleKey: "x", modifierRequired: true },
  { id: "sidebar.toggle", scope: "global", keys: "Mod+Shift+B", titleKey: "x", modifierRequired: true },
  { id: "help.open", scope: "global", keys: "?", titleKey: "x" },
];

describe("프로젝트 단축키 데이터", () => {
  it("기본 키는 Alt+Shift+P다", () => {
    expect(PROJECT_SHORTCUT_DEFS.map((d) => d.keys)).toEqual(["Alt+Shift+P"]);
  });

  it("셸의 전역 키·g 이동 키와 겹치지 않는다(충돌 검사)", () => {
    const goto = gotoShortcuts(DEFAULT_ROUTES, () => {});
    const defs = [...SHELL_FIXED, ...goto.map((d) => ({ id: d.id, scope: d.scope, keys: d.keys, titleKey: d.titleKey })), ...PROJECT_SHORTCUT_DEFS.map((d) => ({ ...d, scope: "global", modifierRequired: true }))];
    const effective = computeEffectiveKeys(defs, {}, "other");
    expect(effective.filter((e) => e.conflict !== undefined)).toEqual([]);
  });

  it("설정이 같은 키를 다른 동작에 주면 충돌로 드러난다(검사가 동작한다는 확인)", () => {
    const effective = computeEffectiveKeys([...SHELL_FIXED, ...PROJECT_SHORTCUT_DEFS.map((d) => ({ ...d, scope: "global", modifierRequired: true }))], { "palette.open": "Alt+Shift+P" }, "other");
    expect(effective.find((e) => e.id === "project.switch")?.conflict).toBe("palette.open");
  });
});
