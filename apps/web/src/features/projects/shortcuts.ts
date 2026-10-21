import type { ShortcutDef } from "@agent-console/ui";

/**
 * 프로젝트 단축키 기본값(데이터). 설정 `ui.keybindings`가 덮어쓴다. 문구는 `messages.shortcuts`의 점 표기 키.
 * 키가 다른 전역 단축키와 겹치지 않는다는 것은 `shortcuts.test.ts`가 지킨다.
 */
export const PROJECT_SHORTCUT_DEFS = [
  { id: "project.switch", keys: "Alt+Shift+P", titleKey: "shortcuts.projectSwitch" },
] as const satisfies readonly Pick<ShortcutDef, "id" | "keys" | "titleKey">[];

export const PROJECT_SWITCH_SHORTCUT_ID = PROJECT_SHORTCUT_DEFS[0].id;
