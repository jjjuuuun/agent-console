/**
 * 작업 탭 행 단축키(screen-sdd §7.7)의 기본 표(데이터). 설정 `ui.keybindings`가 키를 덮어쓴다.
 * 표는 "동작 이름 → 키"만 가진다. 동작이 무엇을 하는지는 `useTaskShortcuts`에 넘기는 핸들러 몫이다.
 * 단일 문자 키(`S`·`R`·`O`)는 공용 처리기가 입력창 안에서는 막는다.
 */
import { useShortcuts, type ShortcutDef } from "@agent-console/ui";

/** 단축키 범위(화면 id). 다른 화면의 같은 키와 겹치지 않는다. */
export const TASK_SHORTCUT_SCOPE = "specs.tasks";

export const TASK_SHORTCUT_DEFS = [
  { action: "status", id: "specs.task.status", keys: "s", titleKey: "shortcuts.sddTaskStatus" },
  { action: "run", id: "specs.task.run", keys: "r", titleKey: "shortcuts.sddTaskRun" },
  { action: "open", id: "specs.task.open", keys: "o", titleKey: "shortcuts.sddTaskOpen" },
  { action: "menu", id: "specs.task.menu", keys: "Shift+F10", titleKey: "shortcuts.sddTaskMenu" },
] as const;

export type TaskShortcutAction = (typeof TASK_SHORTCUT_DEFS)[number]["action"];

/** 표의 동작마다 핸들러가 있는 것만 등록한다(실행 연동이 꺼졌으면 `run`을 주지 않는다). */
export function buildTaskShortcuts(handlers: Partial<Record<TaskShortcutAction, () => void>>): ShortcutDef[] {
  const defs: ShortcutDef[] = [];
  for (const d of TASK_SHORTCUT_DEFS) {
    const run = handlers[d.action];
    if (run !== undefined) defs.push({ id: d.id, scope: TASK_SHORTCUT_SCOPE, keys: d.keys, titleKey: d.titleKey, run });
  }
  return defs;
}

export function useTaskShortcuts(handlers: Partial<Record<TaskShortcutAction, () => void>>): void {
  useShortcuts(buildTaskShortcuts(handlers));
}
