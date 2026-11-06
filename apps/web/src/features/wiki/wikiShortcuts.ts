/**
 * 위키 화면 단축키의 기본 표(데이터, screen-wiki §6.11). 설정 `ui.keybindings`가 키를 덮어쓴다.
 * 표는 "동작 이름 → 키"만 가진다. 동작이 무엇을 하는지는 `useWikiShortcuts`에 넘기는 핸들러 몫이다.
 * 단일 문자 키(`n`·`e`·`/`)는 입력칸·편집기 안에서는 동작하지 않는다(공용 단축키 처리기 규칙). 수식키 조합은 편집기 안에서도 동작한다.
 * 트리의 `F2`·`Delete`·방향키는 `PageTree`가 직접 다룬다(여기에 두면 같은 동작이 두 번 불린다).
 */
import { useShortcuts, type ShortcutDef } from "@agent-console/ui";

export const WIKI_SHORTCUT_SCOPE = "wiki";

export const WIKI_SHORTCUT_DEFS = [
  { action: "newPage", id: "wiki.new", keys: "n", titleKey: "shortcuts.wikiNew", modifier: false },
  { action: "search", id: "wiki.search", keys: "/", titleKey: "shortcuts.wikiSearch", modifier: false },
  { action: "edit", id: "wiki.edit", keys: "e", titleKey: "shortcuts.wikiEdit", modifier: false },
  { action: "modeEdit", id: "wiki.mode.edit", keys: "Alt+E", titleKey: "shortcuts.wikiModeEdit", modifier: true },
  { action: "modeView", id: "wiki.mode.view", keys: "Alt+P", titleKey: "shortcuts.wikiModeView", modifier: true },
  { action: "modeSplit", id: "wiki.mode.split", keys: "Alt+B", titleKey: "shortcuts.wikiModeSplit", modifier: true },
  { action: "panel", id: "wiki.panel", keys: "Alt+H", titleKey: "shortcuts.wikiPanel", modifier: true },
  { action: "tree", id: "wiki.tree", keys: "Alt+T", titleKey: "shortcuts.wikiTree", modifier: true },
  { action: "prevPage", id: "wiki.prev", keys: "Ctrl+Alt+ArrowUp", titleKey: "shortcuts.wikiPrev", modifier: true },
  { action: "nextPage", id: "wiki.next", keys: "Ctrl+Alt+ArrowDown", titleKey: "shortcuts.wikiNext", modifier: true },
  { action: "insertLink", id: "wiki.insertLink", keys: "Ctrl+Alt+L", titleKey: "shortcuts.wikiInsertLink", modifier: true },
] as const;

export type WikiShortcutAction = (typeof WIKI_SHORTCUT_DEFS)[number]["action"];

/** 표의 동작마다 핸들러가 있는 것만 등록한다. */
export function buildWikiShortcuts(handlers: Partial<Record<WikiShortcutAction, () => void>>): ShortcutDef[] {
  const defs: ShortcutDef[] = [];
  for (const d of WIKI_SHORTCUT_DEFS) {
    const run = handlers[d.action];
    if (run !== undefined) defs.push({ id: d.id, scope: WIKI_SHORTCUT_SCOPE, keys: d.keys, titleKey: d.titleKey, ...(d.modifier ? { modifierRequired: true } : {}), run });
  }
  return defs;
}

export function useWikiShortcuts(handlers: Partial<Record<WikiShortcutAction, () => void>>): void {
  useShortcuts(buildWikiShortcuts(handlers));
}
