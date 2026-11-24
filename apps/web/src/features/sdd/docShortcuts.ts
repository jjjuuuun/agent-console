/**
 * 문서 탭 단축키(screen-sdd §6.7)의 기본 표(데이터). 설정 `ui.keybindings`가 키를 덮어쓴다(`Ctrl+S` 저장은 아래 `useSaveShortcut`이 따로 맡는다: 편집기 안은 편집기가 먼저 처리하고, 목록·도구줄 같은 편집기 밖은 이 훅이 처리한다).
 * 표는 "동작 이름 → 키"만 가진다. 동작이 무엇을 하는지는 `useDocShortcuts`에 넘기는 핸들러 몫이다.
 * 수식키 조합이라 편집기에 포커스가 있어도 동작한다. IME 조합 중에는 공용 처리기가 무시한다.
 */
import { useEffect, useRef } from "react";
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

/** 저장 키 글자. Ctrl 또는 Cmd와 함께 눌린다(편집기 자체 처리와 같은 규칙). 브라우저의 "페이지 저장"과 같은 키다. */
export const SAVE_KEY = "s";
const MODAL_SELECTOR = '[role="dialog"][aria-modal="true"], dialog[open]';

/**
 * 화면이 떠 있는 동안 편집기 밖(문서 목록·도구줄·미리보기)에서도 `Ctrl+S`로 저장하고 브라우저 저장 창을 막는다.
 * 편집기가 이미 처리한 키(`defaultPrevented`)·IME 조합 중·키 반복·대화상자가 열려 있을 때는 무시한다(대화상자 안 키는 대화상자 몫).
 * 저장할 수 없는 상태여도 브라우저 저장 창은 막는다. 저장 가능 여부는 `onSave`가 판단한다.
 */
export function useSaveShortcut(onSave: () => void, enabled = true): void {
  const ref = useRef(onSave);
  useEffect(() => {
    ref.current = onSave;
  });
  useEffect(() => {
    if (!enabled) return;
    const listener = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.repeat || e.isComposing || e.keyCode === 229) return;
      if (!(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey || e.key.toLowerCase() !== SAVE_KEY) return;
      if (document.querySelector(MODAL_SELECTOR) !== null) return;
      e.preventDefault();
      ref.current();
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [enabled]);
}
