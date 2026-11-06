/**
 * 문서 탭 단축키(screen-sdd §6.7)의 기본 표(데이터). 설정 `ui.keybindings`가 키를 덮어쓴다(`Ctrl+S` 저장은 편집기 자체 키라 이 표에 없다).
 * 표는 "동작 이름 → 키"만 가진다. 동작이 무엇을 하는지는 `useDocShortcuts`에 넘기는 핸들러 몫이다.
 * 수식키 조합이라 편집기에 포커스가 있어도 동작한다. IME 조합 중에는 공용 처리기가 무시한다.
 */
import { useShortcuts, type ShortcutDef } from "@agent-console/ui";

/** 단축키 범위(화면 id). 다른 화면의 같은 키와 겹치지 않는다. */
export const DOC_SHORTCUT_SCOPE = "specs.documents";

export const DOC_SHORTCUT_DEFS = [
  { action: "modeEdit", id: "specs.doc.mode.edit", keys: "Alt+E", titleKey: "shortcuts.sddDocModeEdit" },
  { action: "modePreview", id: "specs.doc.mode.preview", keys: "Alt+P", titleKey: "shortcuts.sddDocModePreview" },
  { action: "modeSplit", id: "specs.doc.mode.split", keys: "Alt+B", titleKey: "shortcuts.sddDocModeSplit" },
  { action: "prevDoc", id: "specs.doc.prev", keys: "Ctrl+Alt+ArrowUp", titleKey: "shortcuts.sddDocPrev" },
  { action: "nextDoc", id: "specs.doc.next", keys: "Ctrl+Alt+ArrowDown", titleKey: "shortcuts.sddDocNext" },
  { action: "gotoLine", id: "specs.doc.goto", keys: "Ctrl+G", titleKey: "shortcuts.sddDocGoto" },
] as const;

export type DocShortcutAction = (typeof DOC_SHORTCUT_DEFS)[number]["action"];

/** 표의 동작마다 핸들러가 있는 것만 등록한다. */
export function buildDocShortcuts(handlers: Partial<Record<DocShortcutAction, () => void>>): ShortcutDef[] {
  const defs: ShortcutDef[] = [];
  for (const d of DOC_SHORTCUT_DEFS) {
    const run = handlers[d.action];
    if (run !== undefined) defs.push({ id: d.id, scope: DOC_SHORTCUT_SCOPE, keys: d.keys, titleKey: d.titleKey, modifierRequired: true, run });
  }
  return defs;
}

export function useDocShortcuts(handlers: Partial<Record<DocShortcutAction, () => void>>): void {
  useShortcuts(buildDocShortcuts(handlers));
}
